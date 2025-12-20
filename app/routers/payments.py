from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, PaymentLink, Transaction, PaymentLinkStatus, TransactionType, TransactionStatus
from app.schemas import (
    PaymentLinkCreateRequest, PaymentLinkResponse, PaymentLinkPayRequest,
    PaymentLinkListResponse, MessageResponse
)
from app.utils import get_current_user, generate_link_code, generate_reference, get_current_user_with_api_key, calculate_loan_limit

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/links", response_model=PaymentLinkResponse)
def create_payment_link(
    request: PaymentLinkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    link_code = generate_link_code()
    expires_hours = request.expires_in_hours if request.expires_in_hours else 24
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    
    payment_link = PaymentLink(
        user_id=current_user.id,
        link_code=link_code,
        amount=request.amount,
        description=request.description,
        expires_at=expires_at
    )
    
    db.add(payment_link)
    db.commit()
    db.refresh(payment_link)
    
    response = PaymentLinkResponse.model_validate(payment_link)
    response.payment_url = f"/payments/pay/{link_code}"
    
    return response


@router.get("/links", response_model=PaymentLinkListResponse)
def get_my_payment_links(
    status_filter: Optional[PaymentLinkStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(PaymentLink).filter(PaymentLink.user_id == current_user.id)
    
    if status_filter:
        query = query.filter(PaymentLink.status == status_filter)
    
    payment_links = query.order_by(PaymentLink.created_at.desc()).all()
    
    response_links = []
    for link in payment_links:
        link_response = PaymentLinkResponse.model_validate(link)
        link_response.payment_url = f"/payments/pay/{link.link_code}"
        response_links.append(link_response)
    
    return PaymentLinkListResponse(
        payment_links=response_links,
        total_count=len(response_links)
    )


@router.get("/links/{link_code}", response_model=PaymentLinkResponse)
def get_payment_link(
    link_code: str,
    db: Session = Depends(get_db)
):
    payment_link = db.query(PaymentLink).filter(PaymentLink.link_code == link_code).first()
    
    if not payment_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment link not found"
        )
    
    if payment_link.expires_at and payment_link.expires_at < datetime.now(timezone.utc):
        if payment_link.status == PaymentLinkStatus.ACTIVE:
            payment_link.status = PaymentLinkStatus.EXPIRED
            db.commit()
    
    response = PaymentLinkResponse.model_validate(payment_link)
    response.payment_url = f"/payments/pay/{link_code}"
    
    return response


@router.post("/pay/{link_code}", response_model=MessageResponse)
def pay_payment_link(
    link_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    try:
        payment_link = db.query(PaymentLink).filter(
            PaymentLink.link_code == link_code
        ).with_for_update().first()
        
        if not payment_link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment link not found"
            )
        
        if payment_link.expires_at and payment_link.expires_at < datetime.now(timezone.utc):
            payment_link.status = PaymentLinkStatus.EXPIRED
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment link has expired"
            )
        
        if payment_link.status != PaymentLinkStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment link is {payment_link.status.value}"
            )
        
        if payment_link.user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot pay your own payment link"
            )
        
        payer = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        recipient = db.query(User).filter(User.id == payment_link.user_id).with_for_update().first()
        
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment recipient not found"
            )
        
        if payer.wallet_balance < payment_link.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance"
            )
        
        payer_balance_before = payer.wallet_balance
        payer_balance_after = payer_balance_before - payment_link.amount
        
        payer_transaction = Transaction(
            user_id=payer.id,
            transaction_type=TransactionType.TRANSFER_OUT,
            amount=payment_link.amount,
            balance_before=payer_balance_before,
            balance_after=payer_balance_after,
            status=TransactionStatus.COMPLETED,
            reference=generate_reference(),
            description=payment_link.description or f"Payment for link {link_code}",
            recipient_id=recipient.id,
            payment_link_id=payment_link.id
        )
        
        recipient_balance_before = recipient.wallet_balance
        recipient_balance_after = recipient_balance_before + payment_link.amount
        
        recipient_transaction = Transaction(
            user_id=recipient.id,
            transaction_type=TransactionType.PAYMENT_RECEIVED,
            amount=payment_link.amount,
            balance_before=recipient_balance_before,
            balance_after=recipient_balance_after,
            status=TransactionStatus.COMPLETED,
            reference=generate_reference(),
            description=payment_link.description or f"Payment received for link {link_code}",
            recipient_id=payer.id,
            payment_link_id=payment_link.id
        )
        
        payer.wallet_balance = payer_balance_after
        recipient.wallet_balance = recipient_balance_after
        payment_link.status = PaymentLinkStatus.PAID
        payment_link.paid_by_id = payer.id
        payment_link.paid_at = datetime.now(timezone.utc)
        
        db.add(payer_transaction)
        db.add(recipient_transaction)
        db.flush() # Ensure transactions are visible
        
        payer.loan_limit = calculate_loan_limit(payer, db) # Assuming calculate_loan_limit is defined elsewhere
        recipient.loan_limit = calculate_loan_limit(recipient, db) # Assuming calculate_loan_limit is defined elsewhere
        
        db.commit()
        
        return MessageResponse(
            message=f"Payment of {payment_link.amount} completed successfully",
            success=True
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment failed. Please try again."
        )


@router.delete("/links/{link_code}", response_model=MessageResponse)
def cancel_payment_link(
    link_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    payment_link = db.query(PaymentLink).filter(
        PaymentLink.link_code == link_code,
        PaymentLink.user_id == current_user.id
    ).first()
    
    if not payment_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment link not found"
        )
    
    if payment_link.status != PaymentLinkStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a {payment_link.status.value} payment link"
        )
    
    payment_link.status = PaymentLinkStatus.CANCELLED
    db.commit()
    
    return MessageResponse(
        message="Payment link cancelled successfully",
        success=True
    )
