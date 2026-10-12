from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.user import Address


def list_addresses(db: Session, user_id: int):
    # All addresses of one user, oldest first
    query = select(Address).where(Address.user_id == user_id).order_by(Address.id)
    return list(db.execute(query).scalars().all())


def get_address(db: Session, user_id: int, address_id: int):
    # Find an address only if it belongs to this user, otherwise None
    query = select(Address).where(Address.id == address_id, Address.user_id == user_id)
    return db.execute(query).scalar_one_or_none()


def count_addresses(db: Session, user_id: int):
    # How many addresses this user has
    query = select(func.count()).select_from(Address).where(Address.user_id == user_id)
    return db.execute(query).scalar_one()


def create_address(db: Session, user_id: int, values: dict):
    # Add a new address and send the INSERT to the database (the service commits)
    address = Address(user_id=user_id, **values)
    db.add(address)
    db.flush()
    return address


def clear_default_flags(db: Session, user_id: int, except_address_id: int | None):
    # Set is_default to false on all of the user's addresses, except the given one
    statement = update(Address).where(Address.user_id == user_id)
    if except_address_id is not None:
        statement = statement.where(Address.id != except_address_id)
    db.execute(statement.values(is_default=False))


def delete_address(db: Session, address: Address):
    # Remove the address (the service commits)
    db.delete(address)
    db.flush()
