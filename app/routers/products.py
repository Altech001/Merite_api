from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Product, UserSubscription, ProductStatus, KYCStatus
from app.schemas import ProductResponse, UserSubscriptionResponse, MessageResponse, UserResponse
from app.utils import get_current_user, get_current_user_with_api_key

router = APIRouter(prefix="/products", tags=["Products"])

# ... (existing code)

@router.get("/", response_model=List[ProductResponse])
def get_available_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    return db.query(Product).filter(Product.is_active == True).all()


@router.post("/{product_id}/subscribe", response_model=UserSubscriptionResponse)
def subscribe_to_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    existing_sub = db.query(UserSubscription).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.product_id == product_id
    ).first()
    
    if existing_sub:
        if existing_sub.status == ProductStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already subscribed to this product"
            )
        elif existing_sub.status == ProductStatus.PENDING:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription request is already pending"
            )
    
    # Check wallet balance if product has a price
    if product.price > 0 and current_user.wallet_balance < product.price:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient wallet balance for subscription"
        )

    # Deduct balance if price > 0 (Assuming immediate payment, though approval is needed. 
    # Maybe hold funds? For simplicity, we'll just check balance now and deduct on approval or just assume 'bill later' / 'prepaid')
    # The requirement says "ITS HAS TO BE ACTIVED BY THE ADMIN". 
    # Let's just create the request. Payment logic can be added if needed.
    
    subscription = UserSubscription(
        user_id=current_user.id,
        product_id=product_id,
        status=ProductStatus.PENDING
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    
    return subscription


@router.get("/my-subscriptions", response_model=List[UserSubscriptionResponse])
def get_my_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    return db.query(UserSubscription).filter(UserSubscription.user_id == current_user.id).all()


# --- Product Specific Endpoints ---

def check_subscription(user: User, product_name: str, db: Session):
    product = db.query(Product).filter(Product.name == product_name).first()
    if not product:
         raise HTTPException(status_code=404, detail=f"Product {product_name} not configured")
         
    sub = db.query(UserSubscription).filter(
        UserSubscription.user_id == user.id,
        UserSubscription.product_id == product.id,
        UserSubscription.status == ProductStatus.ACTIVE
    ).first()
    
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Active subscription to '{product_name}' required"
        )


@router.get("/kyc-lookup/{phone_number}", response_model=UserResponse)
def kyc_lookup(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    check_subscription(current_user, "KYC Lookup", db)
    
    target_user = db.query(User).filter(User.phone_number == phone_number).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return target_user


@router.post("/sms/bulk", response_model=MessageResponse)
def send_bulk_sms(
    message: str,
    recipients: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    check_subscription(current_user, "Bulk SMS", db)
    
    # Logic to send SMS would go here
    return MessageResponse(message=f"Sent {len(recipients)} messages")


@router.post("/collections/request", response_model=MessageResponse)
def request_collection(
    amount: float,
    payer_phone: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    check_subscription(current_user, "Collections", db)
    
    # Logic for collection request
    return MessageResponse(message=f"Collection request sent to {payer_phone} for {amount}")


@router.get("/statements/download", response_model=MessageResponse)
def download_statement(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    check_subscription(current_user, "Statements", db)
    
    # Logic to generate PDF/CSV
    return MessageResponse(message="Statement generated and sent to email (simulated)")
