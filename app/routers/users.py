from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, KYCStatus, CollectiveData, Transaction, TransactionType, TransactionStatus, CoinMiningSession
from app.schemas import UserUpdate, UserResponse, MessageResponse, CollectiveDataUploadRequest, ProfileUrlUpdate, BankDetailsUpdate, EarningsUpdate, GuestCodeUpdate, CoinsUpdate, GuestCodeRedeemRequest, MiningStatusResponse
from app.utils import get_current_user, get_current_user_with_api_key

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user_with_api_key)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_user_profile(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    update_data = user_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    # Check if all required fields are present to mark as pending review if needed
    required_kyc_fields = ['first_name', 'last_name', 'date_of_birth', 'address', 'id_type', 'id_number']
    all_kyc_complete = all(getattr(current_user, field) is not None for field in required_kyc_fields)
    
    # If previously rejected and now updated, set back to pending? 
    # For now, just leave it as is. Admin will review.
    
    db.commit()
    db.refresh(current_user)
    
    return current_user


from fastapi import File, UploadFile
import shutil
import os

@router.post("/kyc-document", response_model=MessageResponse)
def upload_kyc_document(
    document_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    upload_dir = "uploads/kyc"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_extension = file.filename.split(".")[-1]
    file_name = f"user_{current_user.id}_{document_type}.{file_extension}"
    file_path = os.path.join(upload_dir, file_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    current_user.kyc_document_type = document_type
    current_user.kyc_document_url = file_path
    
    # If all fields are present and doc uploaded, ensure status is PENDING (if not verified)
    if current_user.kyc_status != KYCStatus.VERIFIED:
        current_user.kyc_status = KYCStatus.PENDING
        
    db.commit()
    
    return MessageResponse(message="KYC document uploaded successfully")


@router.get("/kyc-status", response_model=dict)
def get_kyc_status(current_user: User = Depends(get_current_user_with_api_key)):
    required_fields = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
        'date_of_birth': current_user.date_of_birth,
        'address': current_user.address,
        'id_type': current_user.id_type,
        'id_number': current_user.id_number
    }
    
    missing_fields = [field for field, value in required_fields.items() if value is None]
    
    return {
        "kyc_status": current_user.kyc_status.value,
        "is_complete": len(missing_fields) == 0,
        "missing_fields": missing_fields,
        "fields_submitted": {k: v is not None for k, v in required_fields.items()}
    }


@router.post("/collective-data", response_model=MessageResponse)
def upload_collective_data(
    request: CollectiveDataUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    collective_data = CollectiveData(
        user_id=current_user.id,
        data=request.data
    )
    db.add(collective_data)
    db.commit()
    
    return MessageResponse(message="Data uploaded successfully")


@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


# --- Specific Field Updates ---

@router.patch("/me/profile-url", response_model=UserResponse)
def update_profile_url(
    update: ProfileUrlUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    current_user.profile_url = update.profile_url
    db.commit()
    db.refresh(current_user)
    return current_user


@router.patch("/me/bank-details", response_model=UserResponse)
def update_bank_details(
    update: BankDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    current_user.bank_account = update.bank_account
    current_user.bank_name = update.bank_name
    db.commit()
    db.refresh(current_user)
    return current_user


@router.patch("/me/earnings", response_model=UserResponse)
def update_earnings(
    update: EarningsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    if update.commission_earned is not None:
        current_user.commission_earned = update.commission_earned
    if update.referral_amount is not None:
        current_user.referral_amount = update.referral_amount
    db.commit()
    db.refresh(current_user)
    return current_user


@router.patch("/me/guest-code", response_model=UserResponse)
def update_guest_code(
    update: GuestCodeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    # Check uniqueness if necessary
    if update.guest_code:
        existing = db.query(User).filter(User.guest_code == update.guest_code, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Guest code already taken")
            
    current_user.guest_code = update.guest_code
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/coins/mine", response_model=MiningStatusResponse)
def start_mining(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Start a 24-hour coin mining session.
    If a previous session finished, it is claimed.
    """
    now = datetime.now(timezone.utc)
    
    # Check for existing active session
    active_session = db.query(CoinMiningSession).filter(
        CoinMiningSession.user_id == current_user.id,
        CoinMiningSession.is_active == True
    ).order_by(CoinMiningSession.created_at.desc()).first()
    
    # Check if we need to claim previous session
    if active_session:
        # Check if 24h passed
        # session.end_time checks
        # Assuming database stores naive or timezone aware. 
        # For simplicity, if database is postgres via sqlalchemy, usually native python datetime works.
        
        # If active session is still running
        if active_session.end_time > now:
             # Calculate current progress for display
             elapsed = (now - active_session.start_time).total_seconds()
             current_mined = elapsed * active_session.rate_per_second
             
             return MiningStatusResponse(
                is_mining=True,
                start_time=active_session.start_time,
                end_time=active_session.end_time,
                current_mined=current_mined,
                rate_per_second=active_session.rate_per_second,
                total_coins_balance=current_user.coins_accumulated or 0.0,
                remaining_seconds=int((active_session.end_time - now).total_seconds())
             )
        else:
            # Session finished! Claim it.
            # Calculate total for full duration (end_time - start_time)
            duration = (active_session.end_time - active_session.start_time).total_seconds()
            total_earned = duration * active_session.rate_per_second
            
            # Add to user balance
            current_user.coins_accumulated = (current_user.coins_accumulated or 0.0) + total_earned
            active_session.total_mined_in_session = total_earned
            active_session.is_active = False # Mark finished
            active_session.is_claimed = True
            
            # Don't return here, continue to start NEW session below based on "TAP ONCE" logic?
            # Or should we just claim and make them tap again?
            # "Tap / Post once" implies starting. If I tap and it was finished, I start a new one.
            db.commit()
    
    # Start NEW Session
    
    # Calculate Rate: Base + Activity Bonus
    # Base rate: 0.01 coins/sec (~864/day)
    base_rate = 0.01 
    
    # Bonus from investments (mock logic: 0.005 per active investment)
    # This encourages "USER APP ACTIVITIES LIKE INVESTING"
    investment_count = len([i for i in current_user.investments if i.is_active])
    rate = base_rate + (investment_count * 0.005)
    
    end_time = now + timedelta(hours=24)
    
    new_session = CoinMiningSession(
        user_id=current_user.id,
        start_time=now,
        end_time=end_time,
        rate_per_second=rate,
        is_active=True
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    return MiningStatusResponse(
        is_mining=True,
        start_time=new_session.start_time,
        end_time=new_session.end_time,
        current_mined=0.0,
        rate_per_second=rate,
        total_coins_balance=current_user.coins_accumulated or 0.0,
        remaining_seconds=24 * 3600
    )


@router.get("/coins/status", response_model=MiningStatusResponse)
def get_mining_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    now = datetime.now(timezone.utc)
    
    active_session = db.query(CoinMiningSession).filter(
        CoinMiningSession.user_id == current_user.id,
        CoinMiningSession.is_active == True
    ).order_by(CoinMiningSession.created_at.desc()).first()
    
    if not active_session:
        return MiningStatusResponse(
            is_mining=False,
            total_coins_balance=current_user.coins_accumulated or 0.0
        )
        
    # Check if expired
    if active_session.end_time < now:
         # It's finished but not claimed yet via the POST endpoint
         # We show max amount
         duration = (active_session.end_time - active_session.start_time).total_seconds()
         final_amount = duration * active_session.rate_per_second
         
         return MiningStatusResponse(
            is_mining=False, # Technically finished mining
            start_time=active_session.start_time,
            end_time=active_session.end_time,
            current_mined=final_amount,
            rate_per_second=active_session.rate_per_second,
            total_coins_balance=current_user.coins_accumulated or 0.0,
            remaining_seconds=0
        )
    
    # Ongoing
    elapsed = (now - active_session.start_time).total_seconds()
    current_mined = elapsed * active_session.rate_per_second
    
    return MiningStatusResponse(
        is_mining=True,
        start_time=active_session.start_time,
        end_time=active_session.end_time,
        current_mined=current_mined,
        rate_per_second=active_session.rate_per_second,
        total_coins_balance=current_user.coins_accumulated or 0.0,
        remaining_seconds=int((active_session.end_time - now).total_seconds())
    )


@router.delete("/me", response_model=MessageResponse)
def deactivate_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Deactivate the current user's account.
    The user will not be able to login or access details.
    """
    current_user.is_active = False
    db.commit()
    return MessageResponse(message="Account deactivated successfully")


@router.post("/redeem-guest-code", response_model=MessageResponse)
def redeem_guest_code(
    request: GuestCodeRedeemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Redeem a guest code to receive a one-time welcome bonus (300 UGX).
    A user can only redeem a code once.
    """
    if current_user.has_redeemed_guest_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="You have already redeemed your welcome bonus."
        )
            
    # Verify code exists
    code_owner = db.query(User).filter(User.guest_code == request.code).first()
    if not code_owner:
         raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Invalid guest code."
        )
        
    # Apply bonus
    BONUS_AMOUNT = 300.0
    current_user.wallet_balance += BONUS_AMOUNT
    current_user.has_redeemed_guest_code = True
    
    # Create Transaction Log
    transaction = Transaction(
        user_id=current_user.id,
        transaction_type=TransactionType.DEPOSIT,
        amount=BONUS_AMOUNT,
        balance_before=current_user.wallet_balance - BONUS_AMOUNT,
        balance_after=current_user.wallet_balance,
        status=TransactionStatus.COMPLETED,
        reference=f"BONUS-{current_user.id}-{request.code[:8]}", # Truncate code to avoid length issues
        description=f"Guest Code Redemption: {request.code}"
    )
    db.add(transaction)
    
    db.commit()
    
    return MessageResponse(message=f"Success! {BONUS_AMOUNT} UGX added to your wallet.")
