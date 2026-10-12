from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_seller
from app.db import get_db
from app.models.user import User
from app.schemas.product import (
    CreateProductRequest,
    ProductListResponse,
    ProductResponse,
    UpdateProductRequest,
)
from app.services import product_service

# No prefix here, because this file has both /products and /seller/products
router = APIRouter(tags=["products"])


@router.get("/seller/products", response_model=ProductListResponse)
def list_my_products(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    return product_service.list_seller_products(db, seller, page, page_size)


@router.get("/seller/products/{product_id}", response_model=ProductResponse)
def read_my_product(
    product_id: int = Path(ge=1, le=2147483647),
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    return product_service.get_seller_product(db, seller, product_id)


@router.get("/products", response_model=ProductListResponse)
def list_products(
    q: str | None = Query(
        None,
        max_length=100,
        description="Search text for the name and description. Words are matched whole (with stems). "
        'Supports "quoted phrases", or, and -excluded words.',
    ),
    category: str | None = Query(None, max_length=100, description="Category slug. An unknown slug returns 404."),
    min_price: int | None = Query(
        None, ge=0, le=1_000_000_000, description="Lowest price in paise (inclusive, at most 1,000,000,000)"
    ),
    max_price: int | None = Query(
        None, ge=0, le=1_000_000_000, description="Highest price in paise (inclusive, at most 1,000,000,000)"
    ),
    in_stock: bool = Query(False, description="true shows only products with stock above 0"),
    sort: Literal["relevance", "newest", "price_asc", "price_desc", "name_asc"] | None = Query(
        None,
        description="Default is relevance when q is given, otherwise newest. relevance needs q.",
    ),
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return product_service.list_public_products(
        db, page, page_size, category, q, min_price, max_price, in_stock, sort
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
def read_product(product_id: int = Path(ge=1, le=2147483647), db: Session = Depends(get_db)):
    return product_service.get_public_product(db, product_id)


@router.post("/products", response_model=ProductResponse, status_code=201)
def create_product(
    request: CreateProductRequest,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    return product_service.create_product(db, seller, request)


@router.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(
    request: UpdateProductRequest,
    product_id: int = Path(ge=1, le=2147483647),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return product_service.update_product(db, current_user, product_id, request)


@router.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int = Path(ge=1, le=2147483647),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product_service.deactivate_product(db, current_user, product_id)
    return Response(status_code=204)
