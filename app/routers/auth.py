
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from fastapi import Request
from app.models import User, OTPRecord, OTPRateLimit, UserRole, UserLoginLog
from app.schemas import PhoneNumberRequest, OTPVerifyRequest, TokenResponse, OTPResponse, PasswordLoginRequest, SetPasswordRequest, MessageResponse, ApiKeyResponse
from app.utils import generate_otp, create_access_token, send_otp_sms, verify_password, get_password_hash, generate_account_number, generate_api_key, check_lockout, update_rate_limit, get_utc_now, get_current_user
from app.config import OTP_MAX_ATTEMPTS, DEFAULT_LOAN_LIMIT, DEFAULT_LOAN_PERCENT
from user_agents import parse
from datetime import timedelta

router = APIRouter(
    tags=["Authentication"],
    prefix="/auth"
)

@router.post("/generate-api-key", response_model=ApiKeyResponse)
def generate_user_api_key(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    api_key = generate_api_key()
    current_user.api_key = api_key
    db.commit()
    
    return ApiKeyResponse(api_key=api_key)


@router.post("/request-otp", response_model=OTPResponse)
def request_otp(request: PhoneNumberRequest, db: Session = Depends(get_db)):
    phone_number = request.phone_number.strip()
    
    check_lockout(phone_number, db)
    
    otp_code = generate_otp(length=4)
    expires_at = get_utc_now() + timedelta(minutes=10)
    
    otp_record = OTPRecord(
        phone_number=phone_number,
        otp_code=otp_code,
        expires_at=expires_at
    )
    
    db.add(otp_record)
    db.commit()
    
    send_otp_sms(phone_number, otp_code)
    
    return OTPResponse(
        message="OTP sent successfully",
        otp_code=otp_code if True else None # In production, don't return OTP
    )


def log_user_login(user_id: int, request: Request, db: Session, method: str):
    ua_string = request.headers.get("user-agent") or ""
    user_agent = parse(ua_string)
    
    # Format: "Browser on OS - RawUA"
    formatted_ua = f"{user_agent.browser.family} on {user_agent.os.family}"
    if ua_string:
         formatted_ua += f" - {ua_string}"
    
    # Truncate to fit in DB
    if len(formatted_ua) > 255:
        formatted_ua = formatted_ua[:252] + "..."

    log = UserLoginLog(
        user_id=user_id,
        ip_address=request.client.host,
        user_agent=formatted_ua,
        login_method=method
    )
    db.add(log)
    db.commit()


@router.post("/login", response_model=TokenResponse)
def login_with_password(
    login_request: PasswordLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.account_number == login_request.account_number).first()
    
    if not user or not user.hashed_password or not verify_password(login_request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid account number or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
        
    log_user_login(user.id, request, db, "password")
    
    access_token = create_access_token(data={"user_id": user.id, "phone": user.phone_number, "role": user.role.value})
    
    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        role=user.role,
        is_new_user=False
    )


@router.post("/set-password", response_model=MessageResponse)
def set_password(
    password_request: SetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    current_user.hashed_password = get_password_hash(password_request.password)
    db.commit()
    
    return MessageResponse(message="Password set successfully")


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(request: OTPVerifyRequest, req: Request, db: Session = Depends(get_db)):
    phone_number = request.phone_number.strip()
    otp_code = request.otp_code.strip()
    
    check_lockout(phone_number, db)
    
    otp_record = db.query(OTPRecord).filter(
        OTPRecord.phone_number == phone_number,
        OTPRecord.is_used == False,
        OTPRecord.expires_at > get_utc_now()
    ).order_by(OTPRecord.created_at.desc()).first()
    
    if not otp_record:
        update_rate_limit(phone_number, db, failed=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid OTP found. Please request a new one."
        )
    
    otp_record.attempts = (otp_record.attempts or 0) + 1
    
    if otp_record.attempts > OTP_MAX_ATTEMPTS:
        otp_record.is_used = True
        db.commit()
        update_rate_limit(phone_number, db, failed=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many verification attempts. Please request a new OTP."
        )
    
    if otp_record.otp_code != otp_code:
        db.commit()
        update_rate_limit(phone_number, db, failed=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP"
        )
    
    otp_record.is_used = True
    db.commit()
    
    update_rate_limit(phone_number, db, failed=False)
    
    user = db.query(User).filter(User.phone_number == phone_number).first()
    is_new_user = False
    
    if not user:
        # Check if this is the first user
        is_first_user = db.query(User).count() == 0
        
        # Generate unique account number
        while True:
            account_number = generate_account_number()
            if not db.query(User).filter(User.account_number == account_number).first():
                break
        
        # Generate unique guest code
        import secrets
        while True:
            guest_code = "G-" + secrets.token_hex(4).upper() # e.g. G-1A2B3C4D
            if not db.query(User).filter(User.guest_code == guest_code).first():
                break
        
        user = User(
            phone_number=phone_number,
            account_number=account_number,
            wallet_balance=0.00,
            loan_limit=DEFAULT_LOAN_LIMIT,
            loan_percent=DEFAULT_LOAN_PERCENT,
            is_verified=True,
            guest_code=guest_code,
            role=UserRole.ADMIN if is_first_user else UserRole.USER
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        is_new_user = True
    else:
        if not user.account_number:
             while True:
                account_number = generate_account_number()
                if not db.query(User).filter(User.account_number == account_number).first():
                    user.account_number = account_number
                    break
        user.is_verified = True
        db.commit()
    
    log_user_login(user.id, req, db, "otp")
    
    access_token = create_access_token(data={"user_id": user.id, "phone": user.phone_number, "role": user.role.value})
    
    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        role=user.role,
        is_new_user=is_new_user
    )


@router.post("/refresh-token", response_model=TokenResponse)
def refresh_token(
    req: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    log_user_login(current_user.id, req, db, "refresh_token")
    access_token = create_access_token(data={"user_id": current_user.id, "phone": current_user.phone_number, "role": current_user.role.value})
    
    return TokenResponse(
        access_token=access_token,
        user_id=current_user.id,
        role=current_user.role,
        is_new_user=False
    )


