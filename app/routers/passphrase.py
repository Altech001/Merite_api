from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, NotificationType, UserLoginLog
from app.utils import get_current_user, get_password_hash, verify_password, create_access_token
from app.schemas import (
    PassphraseLoginRequest,
    GeneratePassphraseResponse,
    TokenResponse,
    UserAddressUpdate,
    UserResponse
)
from app.notification_service import send_notification
import hashlib
import secrets

# Try to import mnemonic, else fallback
try:
    from mnemonic import Mnemonic
    mnemo = Mnemonic("english")
    def generate_mnemonic():
        return mnemo.generate(strength=128)
except ImportError:
    # Simple fallback using a small pool of words for demonstration
    # In production, ensure 'mnemonic' package is installed
    FALLBACK_WORDS = [
        "abandon", "ability", "able", "about", "above", "absent", "absorb", "abstract", "absurd", "abuse",
        "access", "accident", "account", "accuse", "achieve", "acid", "acoustic", "acquire", "across", "act",
        "action", "actor", "actress", "actual", "adapt", "add", "addict", "address", "adjust", "admit",
        "adult", "advance", "advice", "aerobic", "affair", "afford", "afraid", "again", "age", "agent",
         "agree", "ahead", "aim", "air", "airport", "aisle", "alarm", "album", "alcohol", "alert"
    ]
    def generate_mnemonic():
        return " ".join(secrets.choice(FALLBACK_WORDS) for _ in range(12))

router = APIRouter(
    tags=["Passphrase & Wallet"],
    prefix="/passphrase"
)

def log_login(user_id: int, request: Request, db: Session, method: str):
    """
    Helper to log login events (duplicated simplified version from auth.py)
    """
    ip = request.client.host
    ua = request.headers.get("user-agent", "")[:250]
    log = UserLoginLog(
        user_id=user_id,
        ip_address=ip,
        user_agent=ua,
        login_method=method
    )
    db.add(log)
    db.commit()

@router.post("/generate", response_model=GeneratePassphraseResponse)
def generate_user_passphrase(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a new 12-word passphrase for the logged-in user.
    This should be shown to the user ONCE.
    """
    if current_user.passphrase_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passphrase already generated for this account."
        )

    # Generate 12 words
    passphrase = generate_mnemonic()
    
    # Securely hash the passphrase. 
    # Use SHA-256 pre-hashing to handle length limits of bcrypt, then bcrypt for storage.
    passphrase_digest = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()
    hashed_passphrase = get_password_hash(passphrase_digest)
    
    current_user.passphrase_hash = hashed_passphrase
    db.commit()
    
    # Optional: Send a notification that security info was updated
    send_notification(
        db=db,
        user_id=current_user.id,
        notification_type=NotificationType.ACCOUNT,
        title="Passphrase Created",
        message="A 12-word recovery passphrase has been generated for your account.",
        data={"action": "passphrase_generation"}
    )

    return GeneratePassphraseResponse(
        passphrase=passphrase,
        message="Please save these 12 words securely. They are the only way to recover your account or login via Phrase."
    )


@router.post("/login", response_model=TokenResponse)
def login_with_passphrase(
    login_req: PassphraseLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Login using Phone Number and the 12-word Passphrase.
    """
    user = db.query(User).filter(User.phone_number == login_req.phone_number).first()
    
    if not user or not user.passphrase_hash:
        # Don't reveal if user exists or not, but for passphrase we need checks
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or passphrase not set up."
        )

    # Verify
    input_digest = hashlib.sha256(login_req.passphrase.strip().encode("utf-8")).hexdigest()
    
    if not verify_password(input_digest, user.passphrase_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials."
        )

    if not user.is_active:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Log the login
    log_login(user.id, request, db, "passphrase")
    
    # Token
    access_token = create_access_token(
        data={"user_id": user.id, "phone": user.phone_number, "role": user.role.value}
    )
    
    # Send Notification as requested ("SHOW PASSPHRASE USED TO LOGGIN")
    send_notification(
        db=db,
        user_id=user.id,
        notification_type=NotificationType.SYSTEM, 
        title="Login Alert",
        message=f"Your account was accessed using your Passphrase.",
        data={"login_method": "passphrase", "ip": request.client.host}
    )

    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        role=user.role,
        is_new_user=False
    )

@router.get("/addresses", response_model=UserResponse)
def get_passphrase(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get Passphrase.
    """
    return current_user.passphrase_hash

@router.put("/addresses", response_model=UserResponse)
def update_wallet_addresses(
    update_req: UserAddressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update Celo and Sui addresses.
    """
    if update_req.celo_address is not None:
        current_user.celo_address = update_req.celo_address
    
    if update_req.sui_address is not None:
        current_user.sui_address = update_req.sui_address
        
    db.commit()
    db.refresh(current_user)
    
    return current_user
