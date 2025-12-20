import os
from dotenv import load_dotenv

load_dotenv()



DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_QiSXVl69kdmu@ep-autumn-night-a87nhh2d-pooler.eastus2.azure.neon.tech/neondb?sslmode=require&channel_binding=require",
)

SECRET_KEY = os.getenv("SESSION_SECRET", "2744648219833817")
if not SECRET_KEY:
    raise ValueError("SESSION_SECRET environment variable must be set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

OTP_EXPIRE_MINUTES = 10
OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = 5
OTP_RATE_LIMIT_MINUTES = 1
OTP_LOCKOUT_MINUTES = 30

SIMULATION_MODE = os.getenv("SIMULATION_MODE", "true").lower() == "true"

DEFAULT_LOAN_LIMIT = 50.00
DEFAULT_LOAN_PERCENT = 15.0
INITIAL_WALLET_BALANCE = 0.00

# Africa's Talking Config (Replace with environment variables in production)
AFRICASTALKING_USERNAME = os.getenv("AFRICASTALKING_USERNAME", "sandbox")
# Using the key provided in the user's snippet
AFRICASTALKING_API_KEY = os.getenv("AFRICASTALKING_API_KEY")
AFRICASTALKING_CURRENCY_CODE = "UGX"
