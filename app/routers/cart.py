from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.core.dependencies import require_customer
from app.db import get_db
from app.models.user import User
from app.schemas.cart import (
    AddCartItemRequest,
    CartChangeResponse,
    CartCountResponse,
    CartResponse,
    UpdateCartItemRequest,
)
from app.services import cart_service

# There is no cart id in any URL: the cart is found from the logged-in customer
router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartResponse)
def read_cart(customer: User = Depends(require_customer), db: Session = Depends(get_db)):
    return cart_service.get_cart(db, customer)


@router.get("/count", response_model=CartCountResponse)
def read_cart_count(customer: User = Depends(require_customer), db: Session = Depends(get_db)):
    return cart_service.get_cart_count(db, customer)


@router.post("/items", response_model=CartChangeResponse)
def add_cart_item(
    request: AddCartItemRequest,
    customer: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return cart_service.add_item(db, customer, request.product_id, request.quantity)


@router.patch("/items/{product_id}", response_model=CartChangeResponse)
def update_cart_item(
    request: UpdateCartItemRequest,
    product_id: int = Path(ge=1, le=2147483647),
    customer: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return cart_service.update_item(db, customer, product_id, request.quantity)


@router.delete("/items/{product_id}", status_code=204)
def remove_cart_item(
    product_id: int = Path(ge=1, le=2147483647),
    customer: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    cart_service.remove_item(db, customer, product_id)
    return Response(status_code=204)


@router.delete("", status_code=204)
def clear_cart(customer: User = Depends(require_customer), db: Session = Depends(get_db)):
    cart_service.clear_cart(db, customer)
    return Response(status_code=204)
