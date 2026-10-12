from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class ProductSellerResponse(BaseModel):
    # Only the id and the name. Never the email or any other private field.
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class ProductResponse(BaseModel):
    # Read the values straight from the Product model (price is in paise)
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    price: int
    stock: int
    image_url: str | None
    is_active: bool
    created_at: datetime
    category: ProductCategoryResponse
    seller: ProductSellerResponse


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int


class CreateProductRequest(BaseModel):
    # Remove spaces around every text value before it is checked
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    # Price in paise: at most 10,000,000 (Rs 1,00,000). Stock: at most 1,000,000.
    price: int = Field(gt=0, le=10_000_000)
    stock: int = Field(ge=0, le=1_000_000)
    category_id: int = Field(ge=1, le=2147483647)
    # Either a full http(s) URL or a file under static/images/
    image_url: str | None = Field(default=None, pattern=r"^(https?://|/static/images/)", max_length=500)
    is_active: bool = True


class UpdateProductRequest(BaseModel):
    # Remove spaces around every text value before it is checked
    model_config = ConfigDict(str_strip_whitespace=True)

    # Every field is optional. The default None only means "not sent": the service uses
    # only the sent fields, and a field that is sent as null is rejected (except image_url,
    # where null removes the image).
    name: str = Field(default=None, min_length=1, max_length=200)
    description: str = Field(default=None, min_length=1, max_length=5000)
    price: int = Field(default=None, gt=0, le=10_000_000)
    stock: int = Field(default=None, ge=0, le=1_000_000)
    category_id: int = Field(default=None, ge=1, le=2147483647)
    image_url: str | None = Field(default=None, pattern=r"^(https?://|/static/images/)", max_length=500)
    is_active: bool = Field(default=None)
