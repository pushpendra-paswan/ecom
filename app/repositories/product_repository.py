from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Product


def get_product_by_id(db: Session, product_id: int):
    # Find one product (with its category and seller), or None
    query = (
        select(Product)
        .options(joinedload(Product.category), joinedload(Product.seller))
        .where(Product.id == product_id)
    )
    return db.execute(query).scalar_one_or_none()


def list_products(
    db: Session,
    offset: int,
    limit: int,
    only_active: bool,
    category_id: int | None,
    seller_id: int | None,
):
    # One page of products, newest first. The filters are only used when they are given.
    query = (
        select(Product)
        .options(joinedload(Product.category), joinedload(Product.seller))
        .order_by(Product.created_at.desc(), Product.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if only_active:
        query = query.where(Product.is_active.is_(True))
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if seller_id is not None:
        query = query.where(Product.seller_id == seller_id)
    return list(db.execute(query).scalars().all())


def count_products(
    db: Session, only_active: bool, category_id: int | None, seller_id: int | None
):
    # How many products match the same filters as list_products
    query = select(func.count()).select_from(Product)
    if only_active:
        query = query.where(Product.is_active.is_(True))
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if seller_id is not None:
        query = query.where(Product.seller_id == seller_id)
    return db.execute(query).scalar_one()


def create_product(db: Session, values: dict):
    # Add a new product and send the INSERT to the database (the service commits)
    product = Product(**values)
    db.add(product)
    db.flush()
    return product
