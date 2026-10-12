from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_seller
from app.db import get_db
from app.models.user import User
from app.schemas.order import (
    SellerOrderDetailResponse,
    SellerOrderListResponse,
    UpdateOrderStatusRequest,
    UpdateOrderStatusResponse,
)
from app.services import order_lifecycle_service, order_service

# Its own file because of the /seller/orders prefix. Every endpoint is for sellers only.
router = APIRouter(prefix="/seller/orders", tags=["seller orders"])


@router.get("", response_model=SellerOrderListResponse)
def list_orders(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    return order_service.list_seller_orders(db, seller, page, page_size)


@router.get("/{order_id}", response_model=SellerOrderDetailResponse)
def read_order(
    order_id: int = Path(ge=1, le=2147483647),
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    return order_service.get_seller_order(db, seller, order_id)


@router.patch("/{order_id}/status", response_model=UpdateOrderStatusResponse)
def update_order_status(
    request: UpdateOrderStatusRequest,
    order_id: int = Path(ge=1, le=2147483647),
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    return order_lifecycle_service.update_order_status(db, seller, order_id, request.status)
