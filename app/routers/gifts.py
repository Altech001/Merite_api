from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import json
from typing import List, Optional

from app.database import get_db
from app.models import User, Gift, UserGift, GiftType, GiftStatus, UserGiftStatus, UserRole, UserInvest, Loan, LoanStatus, NotificationType
from app.schemas import GiftCreateRequest, GiftResponse, GiftClaimRequest, UserGiftResponse
from app.utils import get_current_user_with_api_key
from app.notification_service import send_notification
# Reuse this logic for airtime sending if applicable
from app.routers.offers import send_airtime_sdk

router = APIRouter(prefix="/gifts", tags=["Gifts & Rewards"])


def check_gift_eligibility(user: User, requirements_json: str, db: Session) -> bool:
    """
    Check if user meets requirements.
    Requirements format: {"min_wallet": 30000, "min_invest": 1, "active_days": 10, "no_loan": true}
    """
    if not requirements_json:
        return True # No requirements
        
    try:
        reqs = json.loads(requirements_json)
    except:
        return True # Malformed JSON = Pass? Or Fail? Let's say Pass for now or fix on insert.
        
    # 1. Wallet Balance
    if "min_wallet" in reqs:
        if user.wallet_balance < reqs["min_wallet"]:
            return False
            
    # 2. Investments (Count of active investments)
    if "min_invest" in reqs:
        active_invests = db.query(UserInvest).filter(UserInvest.user_id == user.id, UserInvest.is_active == True).count()
        if active_invests < reqs["min_invest"]:
            return False
            
    # 3. No Active Loan
    if "no_loan" in reqs and reqs["no_loan"] == True:
        has_loan = db.query(Loan).filter(
            Loan.user_id == user.id, 
            Loan.status.in_([LoanStatus.PENDING, LoanStatus.APPROVED, LoanStatus.ACTIVE, LoanStatus.DEFAULTED])
        ).first()
        if has_loan:
            return False
            
    # 4. Active Days
    if "active_days" in reqs:
        # Simple check: (Now - CreatedAt) days >= active_days
        days_since_join = (datetime.utcnow() - user.created_at.replace(tzinfo=None)).days
        if days_since_join < reqs["active_days"]:
            return False
            
    return True


# --- ADMIN ENDPOINTS ---

@router.post("/", response_model=GiftResponse)
def create_gift(
    gift: GiftCreateRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """Admin only: Create a new gift."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    new_gift = Gift(
        title=gift.title,
        description=gift.description,
        gift_type=gift.gift_type,
        amount=gift.amount,
        requirements=gift.requirements,
        status=GiftStatus.ACTIVE
    )
    db.add(new_gift)
    db.commit()
    db.refresh(new_gift)
    return new_gift

@router.get("/admin/all", response_model=List[GiftResponse])
def list_all_gifts_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """Admin only: List all gifts regardless of status."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    return db.query(Gift).all()


# --- USER ENDPOINTS ---

@router.get("/", response_model=List[GiftResponse])
def list_available_gifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """List gifts user is ELIGIBLE for."""
    active_gifts = db.query(Gift).filter(Gift.status == GiftStatus.ACTIVE).all()
    
    eligible_gifts = []
    for gift in active_gifts:
        # Check if already claimed? "Can claim one at time" might mean "Can't claim same gift twice" or "Can't have multiple active claims".
        # Assuming "One-time claim per gift ID".
        already_claimed = db.query(UserGift).filter(
            UserGift.user_id == current_user.id,
            UserGift.gift_id == gift.id,
            UserGift.status == UserGiftStatus.CLAIMED
        ).first()
        
        if not already_claimed:
            # Check eligibility
            if check_gift_eligibility(current_user, gift.requirements, db):
                eligible_gifts.append(gift)
                
    return eligible_gifts


@router.post("/{gift_id}/claim", response_model=UserGiftResponse)
def claim_gift(
    gift_id: int,
    claim_req: GiftClaimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """Claim a specific gift."""
    gift = db.query(Gift).filter(Gift.id == gift_id, Gift.status == GiftStatus.ACTIVE).first()
    if not gift:
        raise HTTPException(status_code=404, detail="Gift not found or inactive")
        
    # Check if already claimed
    existing_claim = db.query(UserGift).filter(
        UserGift.user_id == current_user.id,
        UserGift.gift_id == gift.id
    ).first()
    
    if existing_claim and existing_claim.status == UserGiftStatus.CLAIMED:
         raise HTTPException(status_code=400, detail="You have already claimed this gift")
         
    # Check eligibility again (security)
    if not check_gift_eligibility(current_user, gift.requirements, db):
        raise HTTPException(status_code=400, detail="You do not meet the requirements for this gift")
        
    # Process Claim
    user_gift = UserGift(
        user_id=current_user.id,
        gift_id=gift.id,
        status=UserGiftStatus.PENDING,
        recipient_phone=claim_req.recipient_phone or current_user.phone_number
    )
    db.add(user_gift)
    db.commit()
    
    try:
        if gift.gift_type == GiftType.WALLET:
            # Add to wallet
            current_user.wallet_balance += gift.amount
            user_gift.status = UserGiftStatus.CLAIMED
            
            # Log notification
            send_notification(
                db, current_user.id, NotificationType.ACCOUNT, 
                "Gift Claimed", f"You received {gift.amount:,.2f} in your wallet!"
            )
            
        elif gift.gift_type in [GiftType.AIRTIME, GiftType.DATA]:
            # Use Offer Logic to Send Airtime
            # Note: Offer logic deduces from wallet. We don't want to deduct here, we want to just SEND.
            # So we call send_airtime_sdk directly, not the purchase_airtime endpoint.
            
            target_phone = claim_req.recipient_phone if claim_req.recipient_phone else current_user.phone_number
            recipients = [{"phoneNumber": target_phone, "amount": gift.amount}]
            
            try:
                resp = send_airtime_sdk(recipients)
                if resp.get('numSent', 0) > 0:
                    user_gift.status = UserGiftStatus.CLAIMED
                    send_notification(
                        db, current_user.id, NotificationType.ACCOUNT, 
                        "Gift Sent", f"Your gift of {gift.amount} airtime has been sent."
                    )
                else:
                    user_gift.status = UserGiftStatus.FAILED
                    # Don't fail the HTTP request, just mark failed. Or retry logic?
                    
            except Exception as e:
                print(f"Gift Send Error: {e}")
                user_gift.status = UserGiftStatus.FAILED
                
        db.commit()
        db.refresh(user_gift)
        return user_gift
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process gift: {str(e)}")
