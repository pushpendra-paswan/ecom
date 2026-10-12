from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_id(db: Session, user_id: int):
    # Find one user by id, or None
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str):
    # Find one user by email, or None
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def create_user(db: Session, email: str, password_hash: str, full_name: str, role: str):
    # Add a new user and send the INSERT to the database (the service commits)
    user = User(email=email, password_hash=password_hash, full_name=full_name, role=role)
    db.add(user)
    db.flush()
    return user


def list_users(db: Session, offset: int, limit: int):
    # One page of users, oldest first
    query = select(User).order_by(User.id).offset(offset).limit(limit)
    return list(db.execute(query).scalars().all())


def count_users(db: Session):
    # How many users exist in total
    return db.execute(select(func.count()).select_from(User)).scalar_one()
