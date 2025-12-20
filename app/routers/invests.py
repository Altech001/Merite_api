from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from typing import List

from app.database import get_db
from app.models import User, UserInvest, InvestPeriod, Transaction, TransactionType, TransactionStatus
from app.schemas import InvestRequest, InvestResponse, InvestListResponse
from app.utils import get_current_user_with_api_key, generate_reference

router = APIRouter(
    prefix="/invests",
    tags=["invests"],
    responses={404: {"description": "Not found"}},
)

INTEREST_RATES = {
    InvestPeriod.DAILY: 0.03,
    InvestPeriod.WEEKLY: 0.04,
    InvestPeriod.MONTHLY: 0.05,
    InvestPeriod.YEARLY: 0.10,
    InvestPeriod.TEST_5_MIN: 0.03
}

PERIOD_DURATIONS = {
    InvestPeriod.DAILY: timedelta(days=1),
    InvestPeriod.WEEKLY: timedelta(weeks=1),
    InvestPeriod.MONTHLY: timedelta(days=30),
    InvestPeriod.YEARLY: timedelta(days=365),
    InvestPeriod.TEST_5_MIN: timedelta(minutes=5)
}

def update_investment_interest(investment: UserInvest, db: Session):
    if not investment.is_active:
        return

    now = datetime.now(timezone.utc)
    last_update = investment.last_accrual_update
    
    if not last_update:
        last_update = investment.created_at

    duration_delta = now - last_update
    duration_seconds = duration_delta.total_seconds()
    
    period_duration = PERIOD_DURATIONS[investment.period]
    period_seconds = period_duration.total_seconds()
    
    if period_seconds == 0:
        return

    # Calculate fraction of the period passed
    # Interest = Principal * Rate * (TimePassed / PeriodDuration)
    # This allows for continuous increment
    
    rate = investment.interest_rate
    interest_earned = investment.amount * rate * (duration_seconds / period_seconds)
    
    investment.accumulated_interest += interest_earned
    investment.last_accrual_update = now
    
    # We commit in the main route handler, but adding to session here ensures it's tracked
    db.add(investment)

@router.post("/", response_model=InvestResponse)
def create_investment(
    invest_in: InvestRequest,
    current_user: User = Depends(get_current_user_with_api_key),
    db: Session = Depends(get_db)
):
    """
    Create a new investment using funds from the user's wallet.
    """
    if invest_in.period not in INTEREST_RATES:
        raise HTTPException(status_code=400, detail="Invalid investment period")

    if current_user.wallet_balance < invest_in.amount:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    # Deduct from wallet
    current_user.wallet_balance -= invest_in.amount
    
    # Create Transaction Record
    transaction = Transaction(
        user_id=current_user.id,
        transaction_type=TransactionType.INVEST_DEPOSIT,
        amount=invest_in.amount,
        balance_before=current_user.wallet_balance + invest_in.amount,
        balance_after=current_user.wallet_balance,
        status=TransactionStatus.COMPLETED,
        reference=generate_reference(),
        description=f"Investment in {invest_in.period.value} plan"
    )
    db.add(transaction)
    
    # Create Investment
    investment = UserInvest(
        user_id=current_user.id,
        amount=invest_in.amount,
        interest_rate=INTEREST_RATES[invest_in.period],
        period=invest_in.period
    )
    db.add(investment)
    
    db.commit()
    db.refresh(investment)
    return investment

@router.post("/test/5min", response_model=InvestResponse)
def create_test_investment_5min(
    amount: float,
    current_user: User = Depends(get_current_user_with_api_key),
    db: Session = Depends(get_db)
):
    """
    Test Endpoint: Create a 5-minute investment at 3% rate.
    """
    if amount <= 0:
         raise HTTPException(status_code=400, detail="Amount must be positive")
         
    if current_user.wallet_balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    # Deduct from wallet
    current_user.wallet_balance -= amount
    
    # Create Transaction Record
    transaction = Transaction(
        user_id=current_user.id,
        transaction_type=TransactionType.INVEST_DEPOSIT,
        amount=amount,
        balance_before=current_user.wallet_balance + amount,
        balance_after=current_user.wallet_balance,
        status=TransactionStatus.COMPLETED,
        reference=generate_reference(),
        description=f"Test Investment 5 Minutes"
    )
    db.add(transaction)
    
    # Create Investment
    investment = UserInvest(
        user_id=current_user.id,
        amount=amount,
        interest_rate=INTEREST_RATES[InvestPeriod.TEST_5_MIN],
        period=InvestPeriod.TEST_5_MIN
    )
    db.add(investment)
    
    db.commit()
    db.refresh(investment)
    return investment

@router.get("/", response_model=InvestListResponse)
def get_my_investments(
    current_user: User = Depends(get_current_user_with_api_key),
    db: Session = Depends(get_db)
):
    """
    Get all investments for the current user and update their accrued interest.
    """
    investments = db.query(UserInvest).filter(
        UserInvest.user_id == current_user.id,
        UserInvest.is_active == True
    ).all()
    
    # Update interest for all active investments
    for inv in investments:
        update_investment_interest(inv, db)
    
    if investments:
        db.commit()
        # Refresh to get updated values
        for inv in investments:
            db.refresh(inv)
            
    return InvestListResponse(
        investments=investments,
        total_count=len(investments)
    )

@router.post("/{invest_id}/cashout", response_model=InvestResponse)
def cashout_investment(
    invest_id: int,
    current_user: User = Depends(get_current_user_with_api_key),
    db: Session = Depends(get_db)
):
    """
    Cashout an investment: Returns Principal + Accumulated Interest to Wallet.
    """
    investment = db.query(UserInvest).filter(
        UserInvest.id == invest_id,
        UserInvest.user_id == current_user.id,
        UserInvest.is_active == True
    ).first()
    
    if not investment:
        raise HTTPException(status_code=404, detail="Investment not found or already cashed out")
        
    # Final interest update
    update_investment_interest(investment, db)
    
    total_payout = investment.amount + investment.accumulated_interest
    
    # Add to wallet
    current_user.wallet_balance += total_payout
    
    # Create Transaction
    transaction = Transaction(
        user_id=current_user.id,
        transaction_type=TransactionType.INVEST_CASHOUT,
        amount=total_payout,
        balance_before=current_user.wallet_balance - total_payout,
        balance_after=current_user.wallet_balance,
        status=TransactionStatus.COMPLETED,
        reference=generate_reference(),
        description=f"Cashout Investment #{investment.id}"
    )
    db.add(transaction)
    
    # Mark as inactive
    investment.is_active = False
    db.add(investment)
    
    db.commit()
    db.refresh(investment)
    
    return investment
