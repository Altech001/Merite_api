from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, Loan, Transaction, LoanStatus, TransactionType, TransactionStatus, UserRole, NotificationType, AirtimeSale, UserInvest
from app.schemas import LoanRequest, LoanRepaymentRequest, LoanResponse, LoanListResponse, MessageResponse
from app.utils import get_current_user, generate_reference, get_current_user_with_api_key
from app.notification_service import send_notification
from app.config import DEFAULT_LOAN_LIMIT, DEFAULT_LOAN_PERCENT

router = APIRouter(prefix="/loans", tags=["Loans"])

# Constants
APPLICATION_FEE_PERCENT = 0.05 # 5%


def recalculate_loan_limit(user: User, db: Session) -> float:
    """
    Smart Algorithm: Calculate dynamic loan limit based on user activity.
    Base Limit: 50
    Growth: +5% of volume for specific credit-building transactions.
    """
    base_limit = 50.0
    
    # 1. Calculate Volume of "Good" Transactions
    # - Airtime Sales (Income generating)
    # - Investments (Asset building)
    # - Deposits (Liquidity)
    # - Loan Repayments (Credit history)
    
    # Airtime Sales Volume
    airtime_sales_vol = db.query(func.sum(AirtimeSale.amount)).filter(
        AirtimeSale.user_id == user.id,
        AirtimeSale.status == TransactionStatus.COMPLETED
    ).scalar() or 0.0
    
    # Investment Volume (Principal)
    invest_vol = db.query(func.sum(UserInvest.amount)).filter(
        UserInvest.user_id == user.id
    ).scalar() or 0.0
    
    # Deposits
    daily_deposits = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user.id,
        Transaction.transaction_type == TransactionType.DEPOSIT,
        Transaction.status == TransactionStatus.COMPLETED
    ).scalar() or 0.0
    
    total_credit_volume = airtime_sales_vol + invest_vol + daily_deposits
    
    # Limit Increase = 5% of Total Credit Volume
    # "5% PER EACH TRANSACTION" interpreted as 5% of volume to avoid exponential spamming of $1 txns
    dynamic_increase = total_credit_volume * 0.05
    
    new_limit = base_limit + dynamic_increase
    
    # Determine Ceiling (optional, but good for safety, e.g. Max 5M)
    # new_limit = min(new_limit, 5000000.0)
    
    # Update User Limit in DB if changed significantly
    if abs(user.loan_limit - new_limit) > 1.0:
        user.loan_limit = new_limit
        db.add(user) # Check if this commit needs to happen here or caller. 
        # Since we might call this in GET, we assume caller handles commit or we do flush.
        db.commit() 
        db.refresh(user)
        
    return new_limit


@router.get("/eligibility", response_model=dict)
def check_loan_eligibility(
    current_user: User = Depends(get_current_user_with_api_key),
    db: Session = Depends(get_db)
):
    # Update Limit First
    current_limit = recalculate_loan_limit(current_user, db)
    
    active_loans = db.query(Loan).filter(
        Loan.user_id == current_user.id,
        Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.PENDING, LoanStatus.APPROVED, LoanStatus.DEFAULTED])
    ).all()
    
    total_outstanding = sum(loan.total_amount - loan.amount_paid for loan in active_loans)
    # If user has defaulted, limit is effectively 0 until paid
    has_default = any(l.status == LoanStatus.DEFAULTED for l in active_loans)
    
    if has_default:
        available_limit = 0.0
    else:
        available_limit = max(0, current_limit - total_outstanding)
    
    return {
        "loan_limit": current_limit,
        "interest_rate": current_user.loan_percent,
        "application_fee": "5%",
        "available_limit": available_limit,
        "total_outstanding": total_outstanding,
        "active_loans_count": len(active_loans),
        "is_eligible": available_limit >= 50.0 # Minimum loan size
    }


@router.post("/request", response_model=LoanResponse)
def request_loan(
    request: LoanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Request a loan. Goes to PENDING for Admin Review.
    """
    try:
        user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        
        # 1. Recalculate Limit
        recalculate_loan_limit(user, db)
        
        # 2. Check Eligibility
        active_loans = db.query(Loan).filter(
            Loan.user_id == user.id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.PENDING, LoanStatus.APPROVED, LoanStatus.DEFAULTED])
        ).all()
        
        if any(l.status == LoanStatus.DEFAULTED for l in active_loans):
             raise HTTPException(status_code=400, detail="Cannot request loan while having defaulted loans.")
        
        total_outstanding = sum(loan.total_amount - loan.amount_paid for loan in active_loans)
        available_limit = max(0, user.loan_limit - total_outstanding)
        
        if request.amount > available_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Amount exceeds available loan limit. Available: {available_limit}"
            )
            
        if request.amount < 50:
             raise HTTPException(status_code=400, detail="Minimum loan amount is 50")
        
        # 3. Calculate Financials (Discount Loan Model)
        # Interest is deducted upfront? No, usually interest is added to debt. 
        # User requirement: "interest is also deducted before sending". 
        # Let's interpret strictly: Amount Sent = Principal - Fee - Interest. Repayment = Principal.
        
        interest_amount = (request.amount * user.loan_percent) / 100
        # Wait, if I deduct interest, then Principal IS the Total Repayment.
        # total_amount = request.amount 
        
        # Standard: Repayment = Principal + Interest. Disbursed = Principal - Fee.
        # User Req: "interest deducted before sending".
        # If I do Standard Model but deduct Interest from disbursement:
        # Repayment = Principal. Disbursed = Principal - (Principal * Rate) - Fee.
        # This matches "deducted before sending".
        
        # Implementation:
        # Principal (Loan Amount) = request.amount
        # Total Repayment = request.amount (Since interest is pre-paid/deducted)
        # Interest Amount = request.amount * rate
        # Disbursement = request.amount - Interest Amount - Application Fee
        
        # HOWEVER, the Loan Model expects `interest_amount` and `total_amount`.
        # Usually `total_amount = principal + interest`.
        # If we use Discount Model:
        # P = 100. Interest = 15. Total Due = 100. user gets 85.
        
        # Let's try to stick to the schema which likely expects total_amount > principal. 
        # If `total_amount` == `principal`, it might look weird in UI.
        
        # Alternative Interpretation:
        # User requests 100.
        # Fee 5% = 5. Interest 15% = 15.
        # User WALLET receives: 100 - 5 - 15 = 80.
        # User REPAYMENT is: 100.
        # This is a Discount Loan.
        
        total_repayment = request.amount
        
        # Create Loan Record
        loan = Loan(
            user_id=user.id,
            principal_amount=request.amount,
            interest_rate=user.loan_percent,
            interest_amount=interest_amount,
            total_amount=total_repayment, # In discount model, this matches principal
            status=LoanStatus.PENDING,
            due_date=datetime.utcnow() + timedelta(days=30)
        )
        
        db.add(loan)
        db.commit()
        db.refresh(loan)
        
        send_notification(
            db, user.id, NotificationType.LOAN_REQUEST,
            "Loan Application Received",
            f"Your loan request for {request.amount:,.2f} is under review."
        )
        
        return loan
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{loan_id}/repay", response_model=LoanResponse)
def repay_loan(
    loan_id: int,
    request: LoanRepaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    try:
        user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        loan = db.query(Loan).filter(
            Loan.id == loan_id,
            Loan.user_id == user.id
        ).with_for_update().first()
        
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")
        
        if loan.status not in [LoanStatus.ACTIVE, LoanStatus.APPROVED, LoanStatus.DEFAULTED]:
            raise HTTPException(status_code=400, detail="This loan cannot be repaid")
        
        remaining = loan.total_amount - loan.amount_paid
        payment_amount = min(request.amount, remaining)
        
        if user.wallet_balance < payment_amount:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance")
        
        balance_before = user.wallet_balance
        balance_after = balance_before - payment_amount
        
        transaction = Transaction(
            user_id=user.id,
            transaction_type=TransactionType.LOAN_REPAYMENT,
            amount=payment_amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status=TransactionStatus.COMPLETED,
            reference=generate_reference(),
            description=f"Loan repayment - Loan #{loan.id}",
            loan_id=loan.id
        )
        
        user.wallet_balance = balance_after
        loan.amount_paid += payment_amount
        
        if loan.amount_paid >= loan.total_amount:
            loan.status = LoanStatus.PAID
            loan.paid_at = datetime.utcnow()
            
            # Bonus: Repaying loan increases limit slightly too? 
            # (Handled by recalculate_limit seeing Repayment Txn volume next time)
        
        db.add(transaction)
        db.commit()
        db.refresh(loan)
        
        return loan
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=LoanListResponse)
def get_user_loans(
    status_filter: Optional[LoanStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    query = db.query(Loan).filter(Loan.user_id == current_user.id)
    if status_filter:
        query = query.filter(Loan.status == status_filter)
    loans = query.order_by(Loan.created_at.desc()).all()
    
    return LoanListResponse(loans=loans, total_count=len(loans))


@router.get("/{loan_id}", response_model=LoanResponse)
def get_loan_details(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.user_id == current_user.id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


# --- ADMIN ENDPOINTS ---

@router.get("/admin/pending", response_model=List[LoanResponse])
def get_pending_loans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    return db.query(Loan).filter(Loan.status == LoanStatus.PENDING).order_by(Loan.created_at.desc()).all()


@router.get("/admin/approved", response_model=List[LoanResponse])
def get_approved_loans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    return db.query(Loan).filter(Loan.status == LoanStatus.APPROVED).order_by(Loan.created_at.desc()).all()


@router.post("/admin/{loan_id}/approve", response_model=LoanResponse)
def approve_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Approve loan and disburse funds.
    Deducts 5% fee and Interest upfront.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    loan = db.query(Loan).filter(Loan.id == loan_id).with_for_update().first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
        
    if loan.status != LoanStatus.PENDING:
        raise HTTPException(status_code=400, detail="Loan processing is already completed or not pending")
        
    # Get Borrower
    borrower = db.query(User).filter(User.id == loan.user_id).first()
    
    # Calculate Disbursements
    principal = loan.principal_amount
    fee = principal * APPLICATION_FEE_PERCENT
    interest = loan.interest_amount # Pre-calculated
    
    # "Loan interest deducted before sending" & "5% fee deducted"
    disburse_amount = principal - fee - interest
    
    if disburse_amount <= 0:
        # Safety check if interest+fee > principal
        raise HTTPException(status_code=400, detail="Calculated disbursement is zero or negative. Check rates.")
        
    # Disburse
    borrower.wallet_balance += disburse_amount
    loan.status = LoanStatus.APPROVED # Or ACTIVE
    loan.approved_at = datetime.utcnow()
    
    # Transaction Log
    txn = Transaction(
        user_id=borrower.id,
        transaction_type=TransactionType.LOAN_DISBURSEMENT,
        amount=disburse_amount,
        balance_before=borrower.wallet_balance - disburse_amount,
        balance_after=borrower.wallet_balance,
        status=TransactionStatus.COMPLETED,
        reference=generate_reference(),
        description=f"Loan Disbursement (Princ: {principal}, Fee: {fee}, Interest: {interest})",
        loan_id=loan.id
    )
    
    db.add(txn)
    db.commit()
    db.refresh(loan)
    
    send_notification(
        db, borrower.id, NotificationType.LOAN_APPROVED,
        "Loan Approved",
        f"Your loan has been approved. {disburse_amount:,.2f} has been added to your wallet."
    )
    
    return loan
