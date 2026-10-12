from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AddressRequest(BaseModel):
    # Used for both create (POST) and update (PUT)
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=20)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=12)
    country: str = Field(default="India", min_length=1, max_length=100)
    is_default: bool = False


class AddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    phone: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool
    created_at: datetime
