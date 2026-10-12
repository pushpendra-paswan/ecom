from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import category_repository, product_repository
from app.schemas.product import CreateProductRequest, UpdateProductRequest


def list_public_products(
    db: Session,
    page: int,
    page_size: int,
    category_slug: str | None,
    search_text: str | None,
    min_price: int | None,
    max_price: int | None,
    in_stock: bool,
    sort: str | None,
):
    # Remove spaces around the search text. Empty text means "no search".
    # A NUL character cannot be stored or searched in Postgres text, so it is removed too.
    if search_text is not None:
        search_text = search_text.replace("\x00", "").strip()
        if search_text == "":
            search_text = None

    # The lowest price cannot be above the highest price
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price cannot be greater than max_price")

    # Sorting by relevance only makes sense when there is a search
    if sort == "relevance" and search_text is None:
        raise HTTPException(status_code=422, detail="sort=relevance needs a search text (q)")

    # Pick the default sort: relevance for a search, newest otherwise
    if sort is None:
        if search_text is not None:
            sort = "relevance"
        else:
            sort = "newest"

    # Turn the category slug (if any) into a category id. An unknown slug is a 404.
    category_id = None
    if category_slug is not None:
        category = category_repository.get_category_by_slug(db, category_slug)
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")
        category_id = category.id

    # Work out how many rows to skip for this page
    offset = (page - 1) * page_size

    # Read the page and the total (active products only)
    products, total = product_repository.list_products(
        db, offset, page_size, True, category_id, None, search_text, min_price, max_price, in_stock, sort
    )

    return {"items": products, "total": total, "page": page, "page_size": page_size}


def get_public_product(db: Session, product_id: int):
    # A missing product and an inactive product look the same
    product = product_repository.get_product_by_id(db, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


def list_seller_products(db: Session, current_user: User, page: int, page_size: int):
    # Work out how many rows to skip for this page
    offset = (page - 1) * page_size

    # Read this seller's own products, active or not
    products, total = product_repository.list_products(
        db, offset, page_size, False, None, current_user.id, None, None, None, False, "newest"
    )

    return {"items": products, "total": total, "page": page, "page_size": page_size}


def create_product(db: Session, current_user: User, request: CreateProductRequest):
    # The category must exist
    category = category_repository.get_category_by_id(db, request.category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category does not exist")

    # The seller is always the logged-in user, never something from the request body
    values = request.model_dump()
    values["seller_id"] = current_user.id

    # Save the product
    product = product_repository.create_product(db, values)
    db.commit()

    # Read it again so the category and seller are loaded for the response
    return product_repository.get_product_by_id(db, product.id)


def update_product(db: Session, current_user: User, product_id: int, request: UpdateProductRequest):
    # Only sellers and admins may change products
    if current_user.role not in ("seller", "admin"):
        raise HTTPException(status_code=403, detail="Seller or admin access required")

    # Find the product
    product = product_repository.get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # A seller may only change their own products. Someone else's product looks like "not found".
    if current_user.role == "seller" and product.seller_id != current_user.id:
        raise HTTPException(status_code=404, detail="Product not found")

    # Use only the fields that were sent (seller_id is not part of the request at all)
    changes = request.model_dump(exclude_unset=True)

    # A new category must exist
    if "category_id" in changes:
        category = category_repository.get_category_by_id(db, changes["category_id"])
        if category is None:
            raise HTTPException(status_code=400, detail="Category does not exist")
        product.category = category
        del changes["category_id"]

    # Apply the other changes and save
    for field_name, value in changes.items():
        setattr(product, field_name, value)
    db.commit()

    return product


def deactivate_product(db: Session, current_user: User, product_id: int):
    # Only sellers and admins may change products
    if current_user.role not in ("seller", "admin"):
        raise HTTPException(status_code=403, detail="Seller or admin access required")

    # Find the product
    product = product_repository.get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # A seller may only change their own products. Someone else's product looks like "not found".
    if current_user.role == "seller" and product.seller_id != current_user.id:
        raise HTTPException(status_code=404, detail="Product not found")

    # Soft delete: the row stays, it is only hidden (already inactive is fine)
    product.is_active = False
    db.commit()
