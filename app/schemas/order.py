from datetime import datetime

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    # The only thing the client sends. The upper limit is the database integer limit.
    address_id: int = Field(ge=1, le=2147483647)


class CheckoutResponse(BaseModel):
    order_id: int
    checkout_url: str
    total_amount: int


class OrderListItemResponse(BaseModel):
    product_id: int
    product_name: str
    unit_price: int
    quantity: int


class OrderListEntryResponse(BaseModel):
    id: int
    status: str
    total_amount: int
    created_at: datetime
    item_count: int
    items: list[OrderListItemResponse]


class OrderListResponse(BaseModel):
    items: list[OrderListEntryResponse]
    total: int
    page: int
    page_size: int


class ShippingAddressResponse(BaseModel):
    full_name: str
    phone: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country: str


class OrderDetailItemResponse(BaseModel):
    product_id: int
    product_name: str
    unit_price: int
    quantity: int
    line_total: int


class OrderPaymentResponse(BaseModel):
    # No Stripe ids here, on purpose
    status: str
    amount: int
    currency: str


class OrderDetailResponse(BaseModel):
    id: int
    status: str
    total_amount: int
    created_at: datetime
    shipping_address: ShippingAddressResponse
    items: list[OrderDetailItemResponse]
    payment: OrderPaymentResponse | None
