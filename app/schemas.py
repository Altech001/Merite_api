from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models import KYCStatus, TransactionType, TransactionStatus, LoanStatus, PaymentLinkStatus, UserRole, ProductStatus, InvestPeriod, NotificationType, GiftType, GiftStatus, UserGiftStatus


class PhoneNumberRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)


class PasswordLoginRequest(BaseModel):
    account_number: str
    password: str


class SetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6)


class OTPVerifyRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)
    otp_code: str = Field(..., min_length=4, max_length=10)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: UserRole
    is_new_user: bool = False


class OTPResponse(BaseModel):
    message: str
    otp_code: Optional[str] = None
    expires_in_minutes: int = 10


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    phone_number: str
    account_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    email: Optional[str] = None
    celo_address: Optional[str] = None
    sui_address: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    kyc_status: KYCStatus
    kyc_document_type: Optional[str] = None
    kyc_document_url: Optional[str] = None
    role: UserRole
    wallet_balance: float
    loan_limit: float
    loan_percent: float
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    # New fields
    profile_url: Optional[str] = None
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None
    commission_earned: Optional[float] = 0.0
    referral_amount: Optional[float] = 0.0
    guest_code: Optional[str] = None
    coins_accumulated: Optional[float] = 0.0

    class Config:
        from_attributes = True


class ProfileUrlUpdate(BaseModel):
    profile_url: str

class BankDetailsUpdate(BaseModel):
    bank_account: str
    bank_name: str

class EarningsUpdate(BaseModel):
    commission_earned: Optional[float] = None
    referral_amount: Optional[float] = None

class GuestCodeUpdate(BaseModel):
    guest_code: str

class CoinsUpdate(BaseModel):
    coins_accumulated: float

class GuestCodeRedeemRequest(BaseModel):
    code: str

class MiningStatusResponse(BaseModel):
    is_mining: bool
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    current_mined: float = 0.0
    rate_per_second: float = 0.0
    total_coins_balance: float
    remaining_seconds: int = 0


class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: float
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserSubscriptionResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    status: ProductStatus
    product: ProductResponse
    created_at: datetime

    class Config:
        from_attributes = True



class WalletDepositRequest(BaseModel):
    amount: float = Field(..., gt=0)


class WalletWithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0)



class WalletResponse(BaseModel):
    wallet_balance: float
    message: str


class SendMoneyRequest(BaseModel):
    recipient_phone: str = Field(..., min_length=10, max_length=20)
    amount: float = Field(..., gt=0)
    description: Optional[str] = None


class TransactionResponse(BaseModel):
    id: int
    transaction_type: TransactionType
    amount: float
    balance_before: float
    balance_after: float
    status: TransactionStatus
    reference: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total_count: int
    page: int
    page_size: int


class LoanRequest(BaseModel):
    amount: float = Field(..., gt=0)


class LoanRepaymentRequest(BaseModel):
    amount: float = Field(..., gt=0)


class LoanResponse(BaseModel):
    id: int
    principal_amount: float
    interest_rate: float
    interest_amount: float
    total_amount: float
    amount_paid: float
    status: LoanStatus
    due_date: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LoanListResponse(BaseModel):
    loans: List[LoanResponse]
    total_count: int


class PaymentLinkCreateRequest(BaseModel):
    amount: float = Field(..., gt=0)
    description: Optional[str] = None
    expires_in_hours: Optional[int] = Field(default=24, ge=1, le=720)


class PaymentLinkResponse(BaseModel):
    id: int
    link_code: str
    amount: float
    description: Optional[str] = None
    status: PaymentLinkStatus
    expires_at: Optional[datetime] = None
    created_at: datetime
    payment_url: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentLinkPayRequest(BaseModel):
    link_code: str


class PaymentLinkListResponse(BaseModel):
    payment_links: List[PaymentLinkResponse]
    total_count: int


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class CollectiveDataUploadRequest(BaseModel):
    data: str # JSON string



class ApiKeyResponse(BaseModel):
    api_key: str

class InvestRequest(BaseModel):
    amount: float = Field(..., gt=0)
    period: InvestPeriod

class InvestResponse(BaseModel):
    id: int
    amount: float
    interest_rate: float
    period: InvestPeriod
    accumulated_interest: float
    last_accrual_update: datetime
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class InvestListResponse(BaseModel):
    investments: List[InvestResponse]
    total_count: int


# Notification Schemas
class NotificationResponse(BaseModel):
    id: int
    notification_type: NotificationType
    title: str
    message: str
    data: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total_count: int
    unread_count: int
    page: int
    page_size: int


class NotificationUpdateRequest(BaseModel):
    is_read: bool = True


class NotificationBulkUpdateRequest(BaseModel):
    notification_ids: Optional[List[int]] = None  # None means all
    is_read: bool = True


class WebSocketMessage(BaseModel):
    type: str  # "notification", "ping", "pong", "subscribe", "unsubscribe"
    data: Optional[dict] = None


class PassphraseLoginRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)
    passphrase: str = Field(..., description="12-word mnemonic phrase")

class GeneratePassphraseResponse(BaseModel):
    passphrase: str = Field(..., description="12-word mnemonic phrase")
    message: str = "Please save this passphrase securely. It will not be shown again."

class UserAddressUpdate(BaseModel):
    celo_address: Optional[str] = None
    sui_address: Optional[str] = None


class GiftCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    gift_type: GiftType
    amount: float = Field(..., gt=0)
    requirements: Optional[str] = None # JSON string

class GiftResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    gift_type: GiftType
    amount: float
    requirements: Optional[str] = None
    status: GiftStatus
    created_at: datetime
    
    class Config:
        from_attributes = True

class GiftClaimRequest(BaseModel):
    recipient_phone: Optional[str] = None # Required if gift_type is AIRTIME/DATA

class UserGiftResponse(BaseModel):
    id: int
    gift_id: int
    status: UserGiftStatus
    claimed_at: datetime
    gift: Optional[GiftResponse] = None
    
    class Config:
        from_attributes = True


class SellAirtimeRequest(BaseModel):
    recipient_phone: str = Field(..., min_length=10, max_length=20)
    amount: float = Field(..., gt=0)

class SellAirtimeResponse(BaseModel):
    id: int
    amount: float
    commission: float
    status: TransactionStatus
    recipient_phone: str
    created_at: datetime
    message: str = "Airtime sold successfully."
    
    class Config:
        from_attributes = True

