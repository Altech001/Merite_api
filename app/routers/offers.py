from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Any
import africastalking
import json

from app.database import get_db
from app.models import User, Transaction, TransactionType, TransactionStatus, NotificationType
from app.utils import get_current_user_with_api_key, generate_reference
from app.notification_service import send_notification
from app.config import (
    AFRICASTALKING_USERNAME,
    AFRICASTALKING_API_KEY,
    AFRICASTALKING_CURRENCY_CODE
)

# Initialize SDK
try:
    africastalking.initialize(AFRICASTALKING_USERNAME, AFRICASTALKING_API_KEY)
    airtime_service = africastalking.Airtime
except Exception as e:
    print(f"Failed to initialize Africa's Talking SDK: {e}")
    airtime_service = None

router = APIRouter(prefix="/offers", tags=["Offers & Airtime"])

# --- Schemas ---
class AirtimeRecipient(BaseModel):
    phoneNumber: str
    amount: float

class AirtimeRequest(BaseModel):
    recipients: List[AirtimeRecipient]

class AirtimeResponse(BaseModel):
    errorMessage: str
    numSent: int
    totalAmount: str
    totalDiscount: str
    responses: List[dict]

class AirtimeValidationCallback(BaseModel):
    transactionId: str
    phoneNumber: str
    sourceIpAddress: str
    currencyCode: str
    amount: float

class AirtimeStatusCallback(BaseModel):
    phoneNumber: str
    description: str
    status: str
    requestId: str
    discount: str
    value: str


def send_airtime_sdk(recipients: List[dict]) -> dict:
    """
    Sends request using Africa's Talking Python SDK.
    Note: The SDK usually handles one recipient at a time in some versions, 
    but the .send() method supports multiple.
    """
    if not airtime_service:
         raise Exception("Africa's Talking SDK not initialized")

    formatted_recipients = []
    for r in recipients:
         formatted_recipients.append({
             "phoneNumber": r['phoneNumber'],
             "amount": f"{AFRICASTALKING_CURRENCY_CODE} {r['amount']}",
             "currencyCode": AFRICASTALKING_CURRENCY_CODE
         })

    if len(formatted_recipients) == 1:
        # Single mode
        r = recipients[0]
        return airtime_service.send(
            phone_number=r['phoneNumber'],
            amount=str(r['amount']),
            currency_code=AFRICASTALKING_CURRENCY_CODE
        )
    else:
        return airtime_service.send(recipients=formatted_recipients)


@router.post("/airtime/purchase", response_model=AirtimeResponse)
def purchase_airtime(
    request: AirtimeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Buy airtime using Africa's Talking SDK.
    """
    
    # 1. Total Cost
    total_cost = sum(r.amount for r in request.recipients)
    
    if total_cost <= 0:
        raise HTTPException(status_code=400, detail="Total amount must be greater than zero")

    # 2. Wallet Deduction
    user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
    
    if user.wallet_balance < total_cost:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")
        
    balance_before = user.wallet_balance
    balance_after = balance_before - total_cost
    
    transaction = Transaction(
        user_id=user.id,
        transaction_type=TransactionType.PAYMENT_RECEIVED, 
        amount=total_cost,
        balance_before=balance_before,
        balance_after=balance_after,
        status=TransactionStatus.PENDING,
        reference=generate_reference(),
        description=f"Airtime Purchase for {len(request.recipients)} recipient(s)"
    )
    
    user.wallet_balance = balance_after
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    # 3. SDK Call
    try:
        recipient_list = [{"phoneNumber": r.phoneNumber, "amount": r.amount} for r in request.recipients]
        
        # Synchronous SDK call
        provider_response = send_airtime_sdk(recipient_list)
        
        # 4. Handle Response
        if provider_response.get('numSent', 0) > 0:
             transaction.status = TransactionStatus.COMPLETED
             transaction.description += f" [Sent: {provider_response.get('numSent')}]"
             
             send_notification(
                db=db,
                user_id=user.id,
                notification_type=NotificationType.TRANSACTION,
                title="Airtime Sent",
                message=f"Airtime of {total_cost} {AFRICASTALKING_CURRENCY_CODE} sent successfully.",
                data={"provider_response": str(provider_response)} # Cast to string just in case
             )
        else:
             transaction.status = TransactionStatus.FAILED
             transaction.description += f" [Error: {provider_response.get('errorMessage')}]"
             # Refund
             user.wallet_balance += total_cost
             transaction.balance_after += total_cost
             transaction.description += " [REFUNDED]"
             
        db.commit()
        return provider_response

    except Exception as e:
        transaction.status = TransactionStatus.FAILED
        transaction.description += f" [Exception: {str(e)}]"
        user.wallet_balance += total_cost
        db.commit()
        # Raise HTTP 500 but meaningful
        raise HTTPException(status_code=500, detail=f"Airtime processing failed: {str(e)}")


@router.post("/airtime/callback/validation")
async def airtime_validation_callback(payload: AirtimeValidationCallback):
    return {"status": "Validated"}


@router.post("/airtime/callback/status")
async def airtime_status_callback(payload: AirtimeStatusCallback):
    print(f"[Airtime Status] {payload}")
    return {"status": "Received"}
