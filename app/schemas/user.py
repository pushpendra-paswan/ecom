from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    # Remove spaces around every text value before it is checked
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr = Field(max_length=255)
    # bcrypt only uses the first 72 bytes of a password
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=200)
    # Only these two roles can be chosen. Admins come from the seed.
    role: Literal["customer", "seller"] = "customer"


class LoginRequest(BaseModel):
    # Wrong values are a 401 in the service. These limits only stop huge inputs (a password is 72 bytes at most).
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    # Only the name can be changed
    full_name: str = Field(min_length=1, max_length=200)


class UserResponse(BaseModel):
    # Read the values straight from the User model. There is no password_hash field here.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
