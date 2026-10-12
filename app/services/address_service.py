from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import address_repository
from app.schemas.address import AddressRequest


def list_addresses(db: Session, current_user: User):
    # Only the addresses of the logged-in user
    return address_repository.list_addresses(db, current_user.id)


def create_address(db: Session, current_user: User, request: AddressRequest):
    # The first address of a user always becomes the default
    existing_count = address_repository.count_addresses(db, current_user.id)
    values = request.model_dump()
    if existing_count == 0:
        values["is_default"] = True

    # A new default address replaces the old default, in the same transaction
    if values["is_default"]:
        address_repository.clear_default_flags(db, current_user.id, None)

    # Save the address
    address = address_repository.create_address(db, current_user.id, values)
    db.commit()

    return address


def update_address(db: Session, current_user: User, address_id: int, request: AddressRequest):
    # Find the address among this user's addresses. Someone else's address looks like "not found".
    address = address_repository.get_address(db, current_user.id, address_id)
    if address is None:
        raise HTTPException(status_code=404, detail="Address not found")

    # Making this address the default removes the flag from all the others
    if request.is_default:
        address_repository.clear_default_flags(db, current_user.id, address.id)

    # Replace every field with the new values
    address.full_name = request.full_name
    address.phone = request.phone
    address.line1 = request.line1
    address.line2 = request.line2
    address.city = request.city
    address.state = request.state
    address.postal_code = request.postal_code
    address.country = request.country
    address.is_default = request.is_default
    db.commit()

    return address


def delete_address(db: Session, current_user: User, address_id: int):
    # Find the address among this user's addresses. Someone else's address looks like "not found".
    address = address_repository.get_address(db, current_user.id, address_id)
    if address is None:
        raise HTTPException(status_code=404, detail="Address not found")

    # Delete it. No other address becomes the default.
    address_repository.delete_address(db, address)
    db.commit()
