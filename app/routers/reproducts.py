from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
import httpx
from pydantic import BaseModel
from app.utils import get_current_user_with_api_key
from app.models import User

router = APIRouter(prefix="/relworx", tags=["Relworx Products"])

# Relworx API Configuration
RELWORX_BASE_URL = "https://payments.relworx.com/api"
RELWORX_API_KEY = "e433bd68eb07bd.xrLw-5cGWhmAHuzdoojuvA"
RELWORX_ACCEPT_HEADER = "application/vnd.relworx.v2"


# Pydantic Models for Response
class RelworxProduct(BaseModel):
    name: str
    code: str
    category: str
    has_price_list: bool
    has_choice_list: bool
    billable: bool


class RelworxProductsResponse(BaseModel):
    success: bool
    products: List[RelworxProduct]


class ProductsFilterResponse(BaseModel):
    success: bool
    category: Optional[str] = None
    count: int
    products: List[RelworxProduct]


# Helper function to fetch products from Relworx API
async def fetch_relworx_products():
    """Fetch products from Relworx API"""
    headers = {
        "Accept": RELWORX_ACCEPT_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RELWORX_API_KEY}"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{RELWORX_BASE_URL}/products", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Relworx API error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Relworx API: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}"
            )


@router.get("/products", response_model=RelworxProductsResponse)
async def get_all_products(
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all available products from Relworx API
    
    Returns all products including:
    - Bank Transfers
    - TV Subscriptions
    - Airtime
    - Internet Bundles
    - Utilities
    - And more
    """
    data = await fetch_relworx_products()
    return data


@router.get("/products/category/{category}", response_model=ProductsFilterResponse)
async def get_products_by_category(
    category: str,
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get products filtered by category
    
    Available categories:
    - BANK_TRANSFERS
    - TV
    - AIRTIME
    - INTERNET
    - UTILITIES
    - OTHERS
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    # Filter products by category (case-insensitive)
    filtered_products = [
        product for product in data.get("products", [])
        if product.get("category", "").upper() == category.upper()
    ]
    
    return ProductsFilterResponse(
        success=True,
        category=category.upper(),
        count=len(filtered_products),
        products=filtered_products
    )


@router.get("/products/bank-transfers", response_model=ProductsFilterResponse)
async def get_bank_transfer_products(
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all bank transfer products only
    
    Returns all Ugandan bank transfer options including:
    - Stanbic Bank Uganda
    - DFCU Bank Uganda
    - Standard Chartered Bank Uganda
    - Centenary Bank Uganda
    - And many more...
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    # Filter only bank transfer products
    bank_transfers = [
        product for product in data.get("products", [])
        if product.get("category") == "BANK_TRANSFERS"
    ]
    
    return ProductsFilterResponse(
        success=True,
        category="BANK_TRANSFERS",
        count=len(bank_transfers),
        products=bank_transfers
    )


@router.get("/products/tv", response_model=ProductsFilterResponse)
async def get_tv_products(
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all TV subscription products
    
    Returns TV subscriptions including:
    - DSTV - Multichoice
    - GOtv - Multichoice
    - Startimes
    - AZAM TV
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    tv_products = [
        product for product in data.get("products", [])
        if product.get("category") == "TV"
    ]
    
    return ProductsFilterResponse(
        success=True,
        category="TV",
        count=len(tv_products),
        products=tv_products
    )


@router.get("/products/utilities", response_model=ProductsFilterResponse)
async def get_utility_products(
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all utility products
    
    Returns utility products including:
    - UEDCL Light (Umeme Pre-paid)
    - National Water
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    utility_products = [
        product for product in data.get("products", [])
        if product.get("category") == "UTILITIES"
    ]
    
    return ProductsFilterResponse(
        success=True,
        category="UTILITIES",
        count=len(utility_products),
        products=utility_products
    )


@router.get("/products/airtime", response_model=ProductsFilterResponse)
async def get_airtime_products(
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all airtime products
    
    Returns airtime products for:
    - MTN Uganda
    - Airtel Uganda
    - Uganda Telecom
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    airtime_products = [
        product for product in data.get("products", [])
        if product.get("category") == "AIRTIME"
    ]
    
    return ProductsFilterResponse(
        success=True,
        category="AIRTIME",
        count=len(airtime_products),
        products=airtime_products
    )


@router.get("/products/internet", response_model=ProductsFilterResponse)
async def get_internet_products(
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all internet bundle products
    
    Returns internet bundles for:
    - MTN Uganda
    - Airtel Uganda
    - Roke Telecom
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    internet_products = [
        product for product in data.get("products", [])
        if product.get("category") == "INTERNET"
    ]
    
    return ProductsFilterResponse(
        success=True,
        category="INTERNET",
        count=len(internet_products),
        products=internet_products
    )


@router.get("/products/search")
async def search_products(
    query: str,
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Search products by name or code
    
    Query parameter:
    - query: Search term to filter products by name or code
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    # Search in name and code (case-insensitive)
    search_results = [
        product for product in data.get("products", [])
        if query.lower() in product.get("name", "").lower() 
        or query.lower() in product.get("code", "").lower()
    ]
    
    return {
        "success": True,
        "query": query,
        "count": len(search_results),
        "products": search_results
    }


@router.get("/products/price-list/{product_code}")
async def get_product_price_list(
    product_code: str,
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get price list/packages for a specific product
    
    Useful for products with 'has_price_list': true
    Examples:
    - MTN_UG_INTERNET (Data bundles)
    - DSTV (TV Packages)
    - GOTV (TV Packages)
    - AZAM_TV
    """
    headers = {
        "Accept": RELWORX_ACCEPT_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RELWORX_API_KEY}"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Query param 'code' is used in the upstream API
            response = await client.get(
                f"{RELWORX_BASE_URL}/products/price-list", 
                headers=headers,
                params={"code": product_code}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Relworx API error: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching price list: {str(e)}"
            )


@router.get("/products/voice-bundles", response_model=ProductsFilterResponse)
async def get_voice_bundles(
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all voice bundle products (Minutes/Talktime)
    
    Returns voice bundles for:
    - MTN Uganda Voice Bundles
    - Airtel Uganda Voice Bundles
    """
    data = await fetch_relworx_products()
    
    if not data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products from Relworx"
        )
    
    # Voice bundles are typically in 'OTHERS' or identified by name/code
    voice_bundles = [
        product for product in data.get("products", [])
        if "VOICE" in product.get("code", "").upper() or "VOICE" in product.get("name", "").upper()
    ]
    
    return ProductsFilterResponse(
        success=True,
        category="VOICE_BUNDLES",
        count=len(voice_bundles),
        products=voice_bundles
    )


@router.get("/products/choice-list/{product_code}")
async def get_product_choice_list(
    product_code: str,
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get choice list for a specific product
    
    Useful for products with 'has_choice_list': true
    Examples:
    - NATIONAL_WATER (Areas/Zones)
    """
    headers = {
        "Accept": RELWORX_ACCEPT_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RELWORX_API_KEY}"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Query param 'code' is used in the upstream API
            response = await client.get(
                f"{RELWORX_BASE_URL}/products/choice-list", 
                headers=headers,
                params={"code": product_code}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Relworx API error: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching choice list: {str(e)}"
            )


# --- Product Validation ---

# Add uuid for reference generation
import uuid

# Sample Account No from user request - typically this should be in config/env
RELWORX_ACCOUNT_NO = "REL35677DCA1D" 

class ValidationRequest(BaseModel):
    account_no: Optional[str] = None  # Optional: defaults to server config
    reference: Optional[str] = None    # Optional: auto-generated if missing
    msisdn: str                        # Product receiver account/phone/meter number
    amount: float
    product_code: str
    contact_phone: str                 # Phone to receive SMS
    location_id: Optional[str] = None  # Required for NATIONAL_WATER


@router.post("/products/validate")
async def validate_product(
    request: ValidationRequest,
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Validate a product before purchase.
    
    Checks if the account/meter number is valid for the given product.
    - msisdn: The receiver's account/meter/phone number
    - amount: Purchase amount
    - product_code: The product code (e.g., UMEME_PRE_PAID, NATIONAL_WATER)
    - contact_phone: Phone number to receive confirmation SMS
    - location_id: Required specifically for NATIONAL_WATER (from choice-list)
    """
    
    # 1. Prepare payload
    # Use provided account_no or default to the constant
    account_no = request.account_no or RELWORX_ACCOUNT_NO
    
    # Generate reference if not provided (UUID)
    reference = request.reference or str(uuid.uuid4()).replace('-', '')
    
    payload = {
        "account_no": account_no,
        "reference": reference,
        "msisdn": request.msisdn,
        "amount": request.amount,
        "product_code": request.product_code,
        "contact_phone": request.contact_phone
    }
    
    if request.location_id:
        payload["location_id"] = request.location_id
        
    headers = {
        "Accept": RELWORX_ACCEPT_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RELWORX_API_KEY}"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{RELWORX_BASE_URL}/products/validate", 
                json=payload,
                headers=headers
            )
            
            # If 4xx/5xx, Relay the error message from Relworx detailed if possible
            if response.is_error:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("message", error_detail)
                except:
                    pass
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Validation failed: {error_detail}"
                )
                
            return response.json()
            
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Relworx API error: {e.response.text}"
            )
        except httpx.RequestError as e:
             raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Relworx API: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error during validation: {str(e)}"
            )


# --- Product Purchase ---

class PurchaseRequest(BaseModel):
    account_no: Optional[str] = None  # Optional: defaults to server config
    validation_reference: str          # Required from validation step


@router.post("/products/purchase")
async def purchase_product(
    request: PurchaseRequest,
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Purchase a product using a validation reference.
    
    This finalizes the transaction. 
    Funds will be deducted from the business account.
    
    - validation_reference: The 'reference' returned/used in the validation step.
    """
    
    # Use provided account_no or default to the constant
    account_no = request.account_no or RELWORX_ACCOUNT_NO
    
    payload = {
        "account_no": account_no,
        "validation_reference": request.validation_reference
    }
    
    headers = {
        "Accept": RELWORX_ACCEPT_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RELWORX_API_KEY}"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client: # Increased timeout for purchase
        try:
            response = await client.post(
                f"{RELWORX_BASE_URL}/products/purchase", 
                json=payload,
                headers=headers
            )
            
            if response.is_error:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("message", error_detail)
                except:
                    pass
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Purchase failed: {error_detail}"
                )
                
            return response.json()
            
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Relworx API error: {e.response.text}"
            )
        except httpx.RequestError as e:
             raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Relworx API: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error during purchase: {str(e)}"
            )
