from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    PAYMENT_RECEIVED = "payment_received"
    LOAN_DISBURSEMENT = "loan_disbursement"
    LOAN_REPAYMENT = "loan_repayment"
    INVEST_DEPOSIT = "invest_deposit"
    INVEST_CASHOUT = "invest_cashout"

class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GiftType(str, enum.Enum):
    AIRTIME = "airtime"
    DATA = "data"
    WALLET = "wallet"

class GiftStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"

class UserGiftStatus(str, enum.Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    FAILED = "failed"

class LoanStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    ACTIVE = "active"
    PAID = "paid"
    REJECTED = "rejected"
    DEFAULTED = "defaulted"

class PaymentLinkStatus(str, enum.Enum):
    ACTIVE = "active"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"

class ProductStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    account_number = Column(String(20), unique=True, index=True, nullable=True)
    api_key = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    id_type = Column(String(50), nullable=True)
    id_number = Column(String(100), nullable=True)
    kyc_document_type = Column(String(50), nullable=True)
    kyc_document_url = Column(String(255), nullable=True)
    kyc_status = Column(SQLEnum(KYCStatus), default=KYCStatus.PENDING)
    role = Column(SQLEnum(UserRole), default=UserRole.USER)
    wallet_balance = Column(Float, default=0.00)
    loan_limit = Column(Float, default=50000.00)
    loan_percent = Column(Float, default=15.0)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Security and Wallet
    passphrase_hash = Column(String(255), nullable=True)
    celo_address = Column(String(255), nullable=True)
    sui_address = Column(String(255), nullable=True)

    transactions = relationship("Transaction", back_populates="user", foreign_keys="Transaction.user_id")
    loans = relationship("Loan", back_populates="user", foreign_keys="Loan.user_id")
    payment_links = relationship("PaymentLink", back_populates="user", foreign_keys="PaymentLink.user_id")
    otp_records = relationship("OTPRecord", back_populates="user")
    login_logs = relationship("UserLoginLog", back_populates="user")
    subscriptions = relationship("UserSubscription", back_populates="user")
    investments = relationship("UserInvest", back_populates="user")
    claimed_gifts = relationship("UserGift", back_populates="user")
    airtime_sales = relationship("AirtimeSale", back_populates="user")


class UserLoginLog(Base):
    __tablename__ = "user_login_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    login_method = Column(String(50), nullable=True) # "otp" or "password"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="login_logs")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, default=0.00)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subscriptions = relationship("UserSubscription", back_populates="product")


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    status = Column(SQLEnum(ProductStatus), default=ProductStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="subscriptions")
    product = relationship("Product", back_populates="subscriptions")


class OTPRecord(Base):
    __tablename__ = "otp_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    phone_number = Column(String(20), nullable=False, index=True)
    otp_code = Column(String(10), nullable=False)
    is_used = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="otp_records")


class OTPRateLimit(Base):
    __tablename__ = "otp_rate_limits"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    request_count = Column(Integer, default=0)
    failed_attempts = Column(Integer, default=0)
    last_request_at = Column(DateTime(timezone=True), server_default=func.now())
    locked_until = Column(DateTime(timezone=True), nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    balance_before = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    reference = Column(String(100), unique=True, index=True)
    description = Column(Text, nullable=True)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payment_link_id = Column(Integer, ForeignKey("payment_links.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="transactions", foreign_keys=[user_id])
    recipient = relationship("User", foreign_keys=[recipient_id])
    payment_link = relationship("PaymentLink", back_populates="transactions")
    loan = relationship("Loan", back_populates="transactions")


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    principal_amount = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    interest_amount = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0.00)
    status = Column(SQLEnum(LoanStatus), default=LoanStatus.PENDING)
    due_date = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="loans")
    transactions = relationship("Transaction", back_populates="loan")


class PaymentLink(Base):
    __tablename__ = "payment_links"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    link_code = Column(String(50), unique=True, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(PaymentLinkStatus), default=PaymentLinkStatus.ACTIVE)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    paid_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="payment_links", foreign_keys=[user_id])
    paid_by = relationship("User", foreign_keys=[paid_by_id])
    transactions = relationship("Transaction", back_populates="payment_link")
    

class CollectiveData(Base):
    __tablename__ = "collective_data"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    data = Column(Text, nullable=False) # Storing JSON as Text for simplicity in SQLite/Postgres compatibility without specific JSON type imports
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="collective_data")


# Update User model to include relationship
User.collective_data = relationship("CollectiveData", back_populates="user")

class InvestPeriod(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    TEST_5_MIN = "test_5_min"

class UserInvest(Base):
    __tablename__ = "user_invests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False) # Principal
    interest_rate = Column(Float, nullable=False)
    period = Column(SQLEnum(InvestPeriod), nullable=False)
    accumulated_interest = Column(Float, default=0.0)
    last_accrual_update = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="investments")


class Gift(Base):
    __tablename__ = "gifts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    gift_type = Column(SQLEnum(GiftType), nullable=False)
    amount = Column(Float, nullable=False) # Amount of airtime/data/money
    
    # Requirements (JSON stored as Text)
    # e.g. {"min_wallet": 30000, "min_invest": 1, "active_days": 10, "no_loan": true}
    requirements = Column(Text, nullable=True) 
    
    status = Column(SQLEnum(GiftStatus), default=GiftStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user_claims = relationship("UserGift", back_populates="gift")


class UserGift(Base):
    __tablename__ = "user_gifts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    gift_id = Column(Integer, ForeignKey("gifts.id"), nullable=False)
    recipient_phone = Column(String(20), nullable=True) # If airtime/data
    status = Column(SQLEnum(UserGiftStatus), default=UserGiftStatus.PENDING)
    claimed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="claimed_gifts")
    gift = relationship("Gift", back_populates="user_claims")


class AirtimeSale(Base):
    __tablename__ = "airtime_sales"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    commission = Column(Float, nullable=False) # The 2% earned
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="airtime_sales")


class ExportRequest(Base):
    __tablename__ = "export_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, default="scheduled")  # scheduled, processing, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    file_path = Column(String, nullable=True)

    user = relationship("User", back_populates="export_requests")


# Update User model to include relationship
User.export_requests = relationship("ExportRequest", back_populates="user")


class NotificationType(str, enum.Enum):
    TRANSACTION = "transaction"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    LOAN_REQUEST = "loan_request"
    LOAN_APPROVED = "loan_approved"
    LOAN_REJECTED = "loan_rejected"
    LOAN_REPAYMENT = "loan_repayment"
    PAYMENT_LINK = "payment_link"
    PAYMENT_RECEIVED = "payment_received"
    INVESTMENT = "investment"
    ACCOUNT = "account"
    SYSTEM = "system"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    notification_type = Column(SQLEnum(NotificationType), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(Text, nullable=True)  # JSON data for additional context
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="notifications")


# Update User model to include notifications relationship
User.notifications = relationship("Notification", back_populates="user", order_by="desc(Notification.created_at)")