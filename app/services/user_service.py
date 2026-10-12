from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import user_repository
from app.schemas.user import UpdateProfileRequest


def update_profile(db: Session, current_user: User, request: UpdateProfileRequest):
    # Change the name and save it
    current_user.full_name = request.full_name
    db.commit()
    return current_user


def list_users(db: Session, page: int, page_size: int):
    # Work out how many rows to skip for this page
    offset = (page - 1) * page_size

    # Read the page and the total number of users
    users = user_repository.list_users(db, offset, page_size)
    total = user_repository.count_users(db)

    return {"items": users, "total": total, "page": page, "page_size": page_size}
