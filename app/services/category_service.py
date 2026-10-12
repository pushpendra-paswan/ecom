import re

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories import category_repository
from app.schemas.category import CategoryRequest


def list_categories(db: Session):
    # Read every category with its number of active products
    rows = category_repository.list_categories_with_counts(db)

    # Build the response items
    items = []
    for category, product_count in rows:
        items.append(
            {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "description": category.description,
                "product_count": product_count,
            }
        )
    return items


def create_category(db: Session, request: CategoryRequest):
    # Make the slug: lowercase, spaces and underscores become hyphens,
    # other characters are removed, repeated hyphens collapse, and edge hyphens are trimmed
    slug = request.name.lower()
    slug = re.sub(r"[\s_]", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if slug == "":
        raise HTTPException(status_code=422, detail="Name must contain letters or digits")

    # Insert straight away and let the unique constraints catch duplicates
    try:
        category = category_repository.create_category(db, request.name, slug, request.description)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category name or slug already exists")

    return category


def update_category(db: Session, category_id: int, request: CategoryRequest):
    # Find the category
    category = category_repository.get_category_by_id(db, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    # Make the new slug from the new name (same rule as create)
    slug = request.name.lower()
    slug = re.sub(r"[\s_]", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if slug == "":
        raise HTTPException(status_code=422, detail="Name must contain letters or digits")

    # Save the new values and let the unique constraints catch duplicates
    category.name = request.name
    category.slug = slug
    category.description = request.description
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category name or slug already exists")

    return category


def delete_category(db: Session, category_id: int):
    # Find the category
    category = category_repository.get_category_by_id(db, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    # A category that is used by any product (active or not) cannot be deleted
    product_count = category_repository.count_products_in_category(db, category.id)
    if product_count > 0:
        raise HTTPException(status_code=409, detail="Category has products")

    # Delete it. The foreign key still protects us if a product was added at the same moment.
    try:
        category_repository.delete_category(db, category)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category has products")
