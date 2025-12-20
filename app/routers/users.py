from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, KYCStatus, CollectiveData
from app.schemas import UserUpdate, UserResponse, MessageResponse, CollectiveDataUploadRequest
from app.utils import get_current_user, get_current_user_with_api_key

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user_with_api_key)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_user_profile(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    update_data = user_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    # Check if all required fields are present to mark as pending review if needed
    required_kyc_fields = ['first_name', 'last_name', 'date_of_birth', 'address', 'id_type', 'id_number']
    all_kyc_complete = all(getattr(current_user, field) is not None for field in required_kyc_fields)
    
    # If previously rejected and now updated, set back to pending? 
    # For now, just leave it as is. Admin will review.
    
    db.commit()
    db.refresh(current_user)
    
    return current_user


from fastapi import File, UploadFile
import shutil
import os

@router.post("/kyc-document", response_model=MessageResponse)
def upload_kyc_document(
    document_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    upload_dir = "uploads/kyc"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_extension = file.filename.split(".")[-1]
    file_name = f"user_{current_user.id}_{document_type}.{file_extension}"
    file_path = os.path.join(upload_dir, file_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    current_user.kyc_document_type = document_type
    current_user.kyc_document_url = file_path
    
    # If all fields are present and doc uploaded, ensure status is PENDING (if not verified)
    if current_user.kyc_status != KYCStatus.VERIFIED:
        current_user.kyc_status = KYCStatus.PENDING
        
    db.commit()
    
    return MessageResponse(message="KYC document uploaded successfully")


@router.get("/kyc-status", response_model=dict)
def get_kyc_status(current_user: User = Depends(get_current_user_with_api_key)):
    required_fields = {
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
        'date_of_birth': current_user.date_of_birth,
        'address': current_user.address,
        'id_type': current_user.id_type,
        'id_number': current_user.id_number
    }
    
    missing_fields = [field for field, value in required_fields.items() if value is None]
    
    return {
        "kyc_status": current_user.kyc_status.value,
        "is_complete": len(missing_fields) == 0,
        "missing_fields": missing_fields,
        "fields_submitted": {k: v is not None for k, v in required_fields.items()}
    }


@router.post("/collective-data", response_model=MessageResponse)
def upload_collective_data(
    request: CollectiveDataUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    collective_data = CollectiveData(
        user_id=current_user.id,
        data=request.data
    )
    db.add(collective_data)
    db.commit()
    
    return MessageResponse(message="Data uploaded successfully")


@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user
