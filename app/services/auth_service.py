from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import user_repository
from app.schemas.user import LoginRequest, RegisterRequest

# A real bcrypt hash (same cost factor as real passwords, made once when the app starts). Login checks a
# password against it when the email does not exist, so unknown and known emails take the same time.
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt())


def register(db: Session, request: RegisterRequest):
    # Emails are stored in lowercase, so "A@x.com" and "a@x.com" are the same account
    email = request.email.strip().lower()

    # Reject an email that is already registered
    existing_user = user_repository.get_user_by_email(db, email)
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    # bcrypt only reads 72 bytes, so reject longer passwords (some characters use several bytes)
    if len(request.password.encode()) > 72:
        raise HTTPException(status_code=422, detail="Password must be at most 72 bytes long")

    # bcrypt stops reading at a NUL character, so everything after it would be ignored
    if "\x00" in request.password:
        raise HTTPException(status_code=422, detail="Password cannot contain a NUL character")

    # Hash the password with bcrypt (the plain password is never stored)
    password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

    # Create the user and save it in one transaction
    try:
        user = user_repository.create_user(
            db, email, password_hash, request.full_name, request.role
        )
        db.commit()
    except IntegrityError:
        # Someone registered the same email at the same moment
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")

    return user


def login(db: Session, request: LoginRequest):
    # Same cleanup as in register
    email = request.email.strip().lower()
    password_bytes = request.password.encode()

    # One message for "unknown email" and "wrong password", so emails cannot be guessed
    invalid_message = "Incorrect email or password"

    # bcrypt cannot handle more than 72 bytes, and no real password is that long (or has a NUL in it)
    if len(password_bytes) > 72 or b"\x00" in password_bytes:
        raise HTTPException(status_code=401, detail=invalid_message)

    # Look the user up
    user = user_repository.get_user_by_email(db, email)

    # Unknown email: still do one bcrypt check (against the dummy hash) so the response
    # takes as long as a real login
    if user is None:
        bcrypt.checkpw(password_bytes, DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=401, detail=invalid_message)

    # Check the password first
    password_is_correct = bcrypt.checkpw(password_bytes, user.password_hash.encode())
    if not password_is_correct:
        raise HTTPException(status_code=401, detail=invalid_message)

    # Only after the password is right, tell the user that the account is disabled
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Build the token: the user id as "sub" and an expiry time. The role is NOT in the token.
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    token_data = {"sub": str(user.id), "exp": expires_at}
    access_token = jwt.encode(token_data, settings.JWT_SECRET, algorithm="HS256")

    return {"access_token": access_token, "token_type": "bearer"}
