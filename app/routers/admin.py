from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db import get_db
from app.models.user import User
from app.schemas.order import (
    AdminOrderDetailResponse,
    AdminOrderListResponse,
    UpdateOrderStatusRequest,
    UpdateOrderStatusResponse,
)
from app.schemas.user import UserListResponse
from app.services import order_lifecycle_service, order_service, user_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return user_service.list_users(db, page, page_size)


@router.get("/orders", response_model=AdminOrderListResponse)
def list_orders(
    status: Literal["pending_payment", "paid", "shipped", "delivered", "cancelled"] | None = Query(None),
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return order_service.list_admin_orders(db, status, page, page_size)


@router.get("/orders/{order_id}", response_model=AdminOrderDetailResponse)
def read_order(
    order_id: int = Path(ge=1, le=2147483647),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return order_service.get_admin_order(db, order_id)


@router.patch("/orders/{order_id}/status", response_model=UpdateOrderStatusResponse)
def update_order_status(
    request: UpdateOrderStatusRequest,
    order_id: int = Path(ge=1, le=2147483647),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return order_lifecycle_service.update_order_status(db, admin, order_id, request.status)
