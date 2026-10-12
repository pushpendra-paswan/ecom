from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.address import AddressRequest, AddressResponse
from app.schemas.user import UpdateProfileRequest, UserResponse
from app.services import address_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.update_profile(db, current_user, request)


@router.get("/me/addresses", response_model=list[AddressResponse])
def list_my_addresses(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return address_service.list_addresses(db, current_user)


@router.post("/me/addresses", response_model=AddressResponse, status_code=201)
def create_my_address(
    request: AddressRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return address_service.create_address(db, current_user, request)


@router.put("/me/addresses/{address_id}", response_model=AddressResponse)
def update_my_address(
    request: AddressRequest,
    address_id: int = Path(ge=1, le=2147483647),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return address_service.update_address(db, current_user, address_id, request)


@router.delete("/me/addresses/{address_id}", status_code=204)
def delete_my_address(
    address_id: int = Path(ge=1, le=2147483647),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    address_service.delete_address(db, current_user, address_id)
    return Response(status_code=204)
