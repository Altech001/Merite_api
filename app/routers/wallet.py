from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models import User, Transaction, TransactionType, TransactionStatus, NotificationType
from app.schemas import (
    WalletDepositRequest, WalletWithdrawRequest, WalletResponse, SendMoneyRequest,
    TransactionResponse, TransactionListResponse
)
from app.utils import get_current_user, generate_reference, calculate_loan_limit, get_current_user_with_api_key
from app.notification_service import send_notification

router = APIRouter(prefix="/wallet", tags=["Wallet"])

@router.get("/balance", response_model=WalletResponse)
def get_wallet_balance(
    current_user: User = Depends(get_current_user_with_api_key)
):
    return WalletResponse(
        wallet_balance=current_user.wallet_balance,
        message="Balance retrieved successfully"
    )


@router.post("/deposit", response_model=TransactionResponse)
def deposit_funds(
    request: WalletDepositRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    try:
        user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        
        balance_before = user.wallet_balance
        balance_after = balance_before + request.amount
        
        transaction = Transaction(
            user_id=user.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=request.amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status=TransactionStatus.COMPLETED,
            reference=generate_reference(),
            description="Wallet deposit (simulated)"
        )
        
        user.wallet_balance = balance_after
        
        db.add(transaction)
        db.flush() # Ensure transaction is visible for calculation
        
        user.loan_limit = calculate_loan_limit(user, db)
        
        db.commit()
        db.refresh(transaction)
        
        # Send notification
        send_notification(
            db=db,
            user_id=user.id,
            notification_type=NotificationType.DEPOSIT,
            title="Deposit Successful",
            message=f"You have successfully deposited {request.amount:,.2f} to your wallet.",
            data={"transaction_id": transaction.id, "amount": request.amount, "new_balance": balance_after}
        )
        
        return transaction
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction failed. Please try again."
        )
@router.post("/withdraw", response_model=TransactionResponse)
def withdraw_money(
    request: WalletWithdrawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    try:
        user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        
        if user.wallet_balance < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance"
            )
            
        # Deduct 3% fee
        fee = request.amount * 0.03
        total_deduction = request.amount
        net_withdrawal = request.amount - fee
        
        balance_before = user.wallet_balance
        balance_after = balance_before - total_deduction
        
        transaction = Transaction(
            user_id=user.id,
            transaction_type=TransactionType.WITHDRAWAL,
            amount=total_deduction,
            balance_before=balance_before,
            balance_after=balance_after,
            status=TransactionStatus.COMPLETED,
            reference=generate_reference(),
            description=f"Withdrawal: {total_deduction} | Fee: {fee} | Net: {net_withdrawal}"
        )
        
        user.wallet_balance = balance_after
        
        db.add(transaction)
        db.flush()
        
        db.commit()
        db.refresh(transaction)
        
        # Send notification
        send_notification(
            db=db,
            user_id=user.id,
            notification_type=NotificationType.WITHDRAWAL,
            title="Withdrawal Successful",
            message=f"You have withdrawn {total_deduction:,.2f} from your wallet. Fee: {fee:,.2f}",
            data={"transaction_id": transaction.id, "amount": total_deduction, "fee": fee, "net": net_withdrawal, "new_balance": balance_after}
        )
        
        return transaction
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Withdrawal failed. Please try again."
        )

@router.post("/send", response_model=TransactionResponse)
def send_money(
    request: SendMoneyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    try:
        sender = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        
        if sender.wallet_balance < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance"
            )
        
        recipient = db.query(User).filter(User.phone_number == request.recipient_phone).with_for_update().first()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient not found"
            )
        
        if recipient.id == sender.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot send money to yourself"
            )
        
        if sender.wallet_balance < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance"
            )
        
        sender_balance_before = sender.wallet_balance
        sender_balance_after = sender_balance_before - request.amount
        
        sender_transaction = Transaction(
            user_id=sender.id,
            transaction_type=TransactionType.TRANSFER_OUT,
            amount=request.amount,
            balance_before=sender_balance_before,
            balance_after=sender_balance_after,
            status=TransactionStatus.COMPLETED,
            reference=generate_reference(),
            description=request.description or f"Transfer to {recipient.phone_number}",
            recipient_id=recipient.id
        )
        
        recipient_balance_before = recipient.wallet_balance
        recipient_balance_after = recipient_balance_before + request.amount
        
        recipient_transaction = Transaction(
            user_id=recipient.id,
            transaction_type=TransactionType.TRANSFER_IN,
            amount=request.amount,
            balance_before=recipient_balance_before,
            balance_after=recipient_balance_after,
            status=TransactionStatus.COMPLETED,
            reference=generate_reference(),
            description=request.description or f"Transfer from {sender.phone_number}",
            recipient_id=sender.id
        )
        
        sender.wallet_balance = sender_balance_after
        recipient.wallet_balance = recipient_balance_after
        
        db.add(sender_transaction)
        db.add(recipient_transaction)
        db.flush() # Ensure transactions are visible
        
        sender.loan_limit = calculate_loan_limit(sender, db)
        recipient.loan_limit = calculate_loan_limit(recipient, db)
        
        db.commit()
        db.refresh(sender_transaction)
        
        # Send notification to sender
        send_notification(
            db=db,
            user_id=sender.id,
            notification_type=NotificationType.TRANSFER,
            title="Money Sent",
            message=f"You sent {request.amount:,.2f} to {recipient.phone_number}.",
            data={"transaction_id": sender_transaction.id, "amount": request.amount, "recipient": recipient.phone_number}
        )
        
        # Send notification to recipient
        send_notification(
            db=db,
            user_id=recipient.id,
            notification_type=NotificationType.TRANSFER,
            title="Money Received",
            message=f"You received {request.amount:,.2f} from {sender.phone_number}.",
            data={"transaction_id": recipient_transaction.id, "amount": request.amount, "sender": sender.phone_number}
        )
        
        return sender_transaction
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transfer failed. Please try again."
        )


@router.get("/transactions", response_model=TransactionListResponse)
def get_transactions(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    offset = (page - 1) * page_size
    
    total_count = db.query(Transaction).filter(
        Transaction.user_id == current_user.id
    ).count()
    
    transactions = db.query(Transaction).filter(
        Transaction.user_id == current_user.id
    ).order_by(Transaction.created_at.desc()).offset(offset).limit(page_size).all()
    
    return TransactionListResponse(
        transactions=transactions,
        total_count=total_count,
        page=page,
        page_size=page_size
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id
    ).first()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    
    return transaction

