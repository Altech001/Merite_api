from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from datetime import datetime
from app.models import User, KYCStatus, Loan, LoanStatus, Transaction, TransactionType, TransactionStatus, Product, UserSubscription, ProductStatus
from app.schemas import UserResponse, MessageResponse, LoanResponse, ProductResponse, UserSubscriptionResponse
from app.utils import get_current_admin, generate_reference
from pydantic import BaseModel, Field

router = APIRouter(
    tags=["Admin"],
    prefix="/admin"
)

@router.post("/loans/{loan_id}/approve", response_model=LoanResponse)
def approve_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found"
        )
    
    if loan.status != LoanStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve loan with status {loan.status.value}"
        )
    
    user = db.query(User).filter(User.id == loan.user_id).with_for_update().first()
    
    loan.status = LoanStatus.APPROVED
    loan.approved_at = datetime.utcnow()
    
    # Disburse funds
    balance_before = user.wallet_balance
    balance_after = balance_before + loan.principal_amount
    
    transaction = Transaction(
        user_id=user.id,
        transaction_type=TransactionType.LOAN_DISBURSEMENT,
        amount=loan.principal_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        status=TransactionStatus.COMPLETED,
        reference=generate_reference(),
        description=f"Loan disbursement - Loan #{loan.id}",
        loan_id=loan.id
    )
    
    user.wallet_balance = balance_after
    loan.status = LoanStatus.ACTIVE
    
    db.add(transaction)
    db.commit()
    db.refresh(loan)
    
    return loan


class ProductCreate(BaseModel):
    name: str
    description: str
    price: float = Field(..., ge=0)


@router.post("/products", response_model=ProductResponse)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    db_product = Product(
        name=product.name,
        description=product.description,
        price=product.price
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.get("/products", response_model=List[ProductResponse])
def list_products(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    return db.query(Product).all()


@router.post("/subscriptions/{subscription_id}/approve", response_model=UserSubscriptionResponse)
def approve_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    subscription = db.query(UserSubscription).filter(UserSubscription.id == subscription_id).first()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found"
        )
    
    if subscription.status != ProductStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve subscription with status {subscription.status.value}"
        )
    
    subscription.status = ProductStatus.ACTIVE
    db.commit()
    db.refresh(subscription)
    return subscription

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=List[UserResponse])
def get_all_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.get("/kyc", response_model=List[UserResponse])
def get_pending_kyc_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    users = db.query(User).filter(User.kyc_status == KYCStatus.PENDING).all()
    return users


@router.post("/kyc/{user_id}/approve", response_model=MessageResponse)
def approve_kyc(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.kyc_status = KYCStatus.VERIFIED
    user.is_verified = True  # Also set the boolean flag
    db.commit()
    
    return MessageResponse(message=f"KYC approved for user {user.phone_number}")


@router.post("/kyc/{user_id}/reject", response_model=MessageResponse)
def reject_kyc(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.kyc_status = KYCStatus.REJECTED
    db.commit()
    
    return MessageResponse(message=f"KYC rejected for user {user.phone_number}")
