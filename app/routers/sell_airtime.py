from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.database import get_db
from app.models import User, AirtimeSale, Transaction, TransactionType, TransactionStatus, NotificationType
from app.schemas import SellAirtimeRequest, SellAirtimeResponse
from app.utils import get_current_user_with_api_key, generate_reference
from app.notification_service import send_notification
from app.routers.offers import send_airtime_sdk
from app.config import AFRICASTALKING_CURRENCY_CODE

router = APIRouter(prefix="/airtime", tags=["Airtime Sales"])

COMMISSION_RATE = 0.02 # 2%

@router.post("/sell", response_model=SellAirtimeResponse)
def sell_airtime(
    req: SellAirtimeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Sell airtime to a recipient. 
    1. Deduct 'amount' from seller's wallet.
    2. Send airtime to recipient.
    3. Calculate 2% commission.
    4. Add commission back to seller's wallet.
    """
    
    # 1. Validate & Lock User
    user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
    
    if user.wallet_balance < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance to sell this amount")
        
    # 2. Deduct Principal
    balance_before_deduct = user.wallet_balance
    user.wallet_balance -= req.amount
    balance_after_deduct = user.wallet_balance
    
    # Log Deduction Transaction
    deduct_txn = Transaction(
        user_id=user.id,
        transaction_type=TransactionType.PAYMENT_RECEIVED, # Or a generic DEBIT type
        amount=req.amount,
        balance_before=balance_before_deduct,
        balance_after=balance_after_deduct,
        status=TransactionStatus.PENDING,
        reference=generate_reference(),
        description=f"Airtime Sale (Principal) to {req.recipient_phone}"
    )
    db.add(deduct_txn)
    
    # 3. Send Airtime
    try:
        recipients = [{"phoneNumber": req.recipient_phone, "amount": req.amount}]
        resp = send_airtime_sdk(recipients)
        
        if resp.get('numSent', 0) > 0:
            deduct_txn.status = TransactionStatus.COMPLETED
            
            # 4. Process Commission
            commission = req.amount * COMMISSION_RATE
            balance_before_comm = user.wallet_balance
            user.wallet_balance += commission
            balance_after_comm = user.wallet_balance
            
            # Log Commission Transaction
            comm_txn = Transaction(
                user_id=user.id,
                transaction_type=TransactionType.DEPOSIT, # Or COMMISSION type
                amount=commission,
                balance_before=balance_before_comm,
                balance_after=balance_after_comm,
                status=TransactionStatus.COMPLETED,
                reference=generate_reference(),
                description=f"Commission (2%) for Airtime Sale to {req.recipient_phone}"
            )
            db.add(comm_txn)
            
            # Log AirtimeSale Record (Specific Table)
            sale = AirtimeSale(
                user_id=user.id,
                recipient_phone=req.recipient_phone,
                amount=req.amount,
                commission=commission,
                status=TransactionStatus.COMPLETED
            )
            db.add(sale)
            
            # Notify
            send_notification(
                db, user.id, NotificationType.TRANSACTION,
                "Airtime Sold - Earnings Received",
                f"You sold {req.amount} airtime and earned {commission:,.2f} {AFRICASTALKING_CURRENCY_CODE}!"
            )
            
            db.commit()
            db.refresh(sale)
            return sale
            
        else:
            # Airtime Sending Failed
            deduct_txn.status = TransactionStatus.FAILED
            deduct_txn.description += f" [Error: {resp.get('errorMessage')}]"
            
            # Refund Deduction (Atomic Rollback essentially, but explicit here)
            user.wallet_balance += req.amount
            
            # Log Failure in Sales Table
            sale = AirtimeSale(
                user_id=user.id,
                recipient_phone=req.recipient_phone,
                amount=req.amount,
                commission=0,
                status=TransactionStatus.FAILED
            )
            db.add(sale)
            
            db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to send airtime: {resp.get('errorMessage')}")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"System error: {str(e)}")


@router.get("/history", response_model=List[SellAirtimeResponse])
def sales_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """View my airtime sales history."""
    return db.query(AirtimeSale).filter(AirtimeSale.user_id == current_user.id).order_by(AirtimeSale.created_at.desc()).all()
