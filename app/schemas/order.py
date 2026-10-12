from datetime import datetime
from typing import Literal

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


class CancelOrderResponse(BaseModel):
    order_id: int
    status: str
    payment_status: str


class UpdateOrderStatusRequest(BaseModel):
    # Only these two values are accepted. paid, cancelled, pending_payment and anything else give 422.
    status: Literal["shipped", "delivered"]


class UpdateOrderStatusResponse(BaseModel):
    order_id: int
    status: str


class SellerOrderEntryResponse(BaseModel):
    # Only this seller's own lines. No customer email, no Stripe ids.
    id: int
    status: str
    created_at: datetime
    items: list[OrderDetailItemResponse]
    seller_subtotal: int
    has_other_sellers: bool


class SellerOrderListResponse(BaseModel):
    items: list[SellerOrderEntryResponse]
    total: int
    page: int
    page_size: int


class SellerOrderDetailResponse(SellerOrderEntryResponse):
    # The seller needs the address to ship
    shipping_address: ShippingAddressResponse


class AdminOrderEntryResponse(BaseModel):
    id: int
    status: str
    created_at: datetime
    total_amount: int
    customer_email: str
    shipping_full_name: str
    item_count: int


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderEntryResponse]
    total: int
    page: int
    page_size: int


class AdminOrderDetailResponse(AdminOrderEntryResponse):
    # No Stripe ids here, on purpose
    user_id: int
    shipping_address: ShippingAddressResponse
    items: list[OrderDetailItemResponse]
    payment: OrderPaymentResponse | None
