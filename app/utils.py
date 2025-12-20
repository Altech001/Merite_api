import random
import string
import uuid
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, OTP_LENGTH, OTP_RATE_LIMIT_MINUTES, OTP_LOCKOUT_MINUTES, OTP_MAX_ATTEMPTS
from app.database import get_db
from app.models import User, UserRole, Transaction, TransactionStatus, OTPRateLimit

security = HTTPBearer(auto_error=False)


def generate_api_key() -> str:
    return f"mk_{secrets.token_urlsafe(32)}"


def get_current_user_with_api_key(
    x_api_key: Optional[str] = Header(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if x_api_key:
        user = db.query(User).filter(User.api_key == x_api_key).first()
        if not user:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key",
            )
        if not user.is_active:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        return user
        
    if credentials:
        return get_current_user(credentials, db)
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def generate_otp(length: int = OTP_LENGTH) -> str:
    return ''.join(random.choices(string.digits, k=length))


def generate_reference() -> str:
    return f"TXN-{uuid.uuid4().hex[:12].upper()}"


def generate_link_code() -> str:
    return f"PAY-{uuid.uuid4().hex[:10].upper()}"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user


def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action"
        )
    return current_user


def calculate_loan_limit(user: User, db: Session) -> float:
    # Calculate total transaction volume (completed)
    total_volume = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user.id,
        Transaction.status == TransactionStatus.COMPLETED
    ).scalar() or 0.0
    
    # Simple algorithm
    if total_volume >= 100000:
        return 1000000.0
    elif total_volume >= 50000:
        return 500000.0
    elif total_volume >= 10000:
        return 100000.0
    elif total_volume >= 1000:
        return 60000.0
    else:
        return 50000.0


def verify_password(plain_password, hashed_password):
    # Ensure bytes
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_password, hashed_password)


def get_password_hash(password):
    if isinstance(password, str):
        password = password.encode('utf-8')
    return bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')


def generate_account_number() -> str:
    # Generate a 9-digit account number starting with 'ME'
    suffix = ''.join(random.choices(string.digits, k=7))
    return f"ME{suffix}"


def get_utc_now():
    return datetime.utcnow()


def check_lockout(phone_number: str, db: Session):
    rate_limit = db.query(OTPRateLimit).filter(OTPRateLimit.phone_number == phone_number).first()
    if rate_limit and rate_limit.locked_until:
        if rate_limit.locked_until > get_utc_now():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked. Try again later."
            )
        else:
            # Lockout expired
            rate_limit.locked_until = None
            rate_limit.failed_attempts = 0
            db.commit()


def update_rate_limit(phone_number: str, db: Session, failed: bool = False):
    rate_limit = db.query(OTPRateLimit).filter(OTPRateLimit.phone_number == phone_number).first()
    
    if not rate_limit:
        rate_limit = OTPRateLimit(phone_number=phone_number)
        db.add(rate_limit)
        db.commit()
    
    now = get_utc_now()
    
    if failed:
        rate_limit.failed_attempts += 1
        if rate_limit.failed_attempts >= OTP_MAX_ATTEMPTS:
            rate_limit.locked_until = now + timedelta(minutes=OTP_LOCKOUT_MINUTES)
    else:
        # Reset on success
        rate_limit.failed_attempts = 0
        rate_limit.locked_until = None
    
    rate_limit.last_request_at = now
    db.commit()


def send_otp_sms(phone_number: str, otp_code: str) -> bool:
    print(f"[SIMULATION] Sending OTP {otp_code} to {phone_number}")
    return True
