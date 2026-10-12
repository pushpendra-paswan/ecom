from pydantic import BaseModel, Field


class AddCartItemRequest(BaseModel):
    # The upper limit of product_id is the database integer limit (a bigger number would be a 500)
    product_id: int = Field(ge=1, le=2147483647)
    # 10 is MAX_QUANTITY_PER_PRODUCT in cart_service.py
    quantity: int = Field(default=1, ge=1, le=10)


class UpdateCartItemRequest(BaseModel):
    # Sets the quantity to exactly this value. To remove a line, use DELETE.
    quantity: int = Field(ge=1, le=10)


class CartItemResponse(BaseModel):
    product_id: int
    name: str
    image_url: str | None
    unit_price: int
    stock: int
    is_active: bool
    quantity: int
    line_total: int
    available: bool
    problem: str | None


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    item_count: int
    subtotal: int
    has_problems: bool


class CartChangeResponse(BaseModel):
    # Returned by POST and PATCH /cart/items
    product_id: int
    quantity: int
    item_count: int


class CartCountResponse(BaseModel):
    item_count: int
