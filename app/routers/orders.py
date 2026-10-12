from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_customer
from app.db import get_db
from app.models.user import User
from app.schemas.order import (
    CheckoutRequest,
    CancelOrderResponse,
    CheckoutResponse,
    OrderDetailResponse,
    OrderListResponse,
)
from app.services import checkout_service, order_lifecycle_service, order_service

# Customers use these endpoints for their own orders. Cancel is also open to admins (any order).
router = APIRouter(prefix="/orders", tags=["orders"])


# Plain "def" endpoints: the database and Stripe calls block, so FastAPI runs them in a thread
@router.post("/checkout", response_model=CheckoutResponse, status_code=201)
def checkout(
    request: CheckoutRequest,
    customer: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return checkout_service.checkout(db, customer, request.address_id)


@router.get("", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return order_service.list_orders(db, customer, page, page_size)


@router.get("/{order_id}", response_model=OrderDetailResponse)
def read_order(
    order_id: int = Path(ge=1, le=2147483647),
    customer: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return order_service.get_order(db, customer, order_id)


@router.post("/{order_id}/cancel", response_model=CancelOrderResponse)
def cancel_order(
    order_id: int = Path(ge=1, le=2147483647),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # The role check (customer or admin) is in the service, as in the product endpoints
    return order_lifecycle_service.cancel_order(db, current_user, order_id)
