import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.repositories import user_repository

# auto_error=False lets us return our own 401 when the header is missing
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    # The same 401 is used for every kind of failure
    unauthorized = HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # No "Authorization: Bearer <token>" header
    if credentials is None:
        raise unauthorized

    # Check the signature and the expiry time. "sub" and "exp" must be present.
    try:
        token_data = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(token_data["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized

    # Load the user from the database. Role and active status always come from here, never from the token.
    user = user_repository.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    return user


def require_customer(current_user=Depends(get_current_user)):
    # Only customers may pass
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Customer access required")
    return current_user


def require_seller(current_user=Depends(get_current_user)):
    # Only sellers may pass
    if current_user.role != "seller":
        raise HTTPException(status_code=403, detail="Seller access required")
    return current_user


def require_admin(current_user=Depends(get_current_user)):
    # Only admins may pass
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
