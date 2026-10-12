from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Category, Product


def list_categories_with_counts(db: Session):
    # Every category with its number of ACTIVE products, sorted by name.
    # The inactive-product test is inside the join, so categories with no products still show 0.
    query = (
        select(Category, func.count(Product.id))
        .outerjoin(Product, (Product.category_id == Category.id) & (Product.is_active.is_(True)))
        .group_by(Category.id)
        .order_by(Category.name)
    )
    return list(db.execute(query).all())


def get_category_by_id(db: Session, category_id: int):
    # Find one category by id, or None
    return db.get(Category, category_id)


def get_category_by_slug(db: Session, slug: str):
    # Find one category by slug, or None
    return db.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()


def create_category(db: Session, name: str, slug: str, description: str | None):
    # Add a new category and send the INSERT to the database (the service commits)
    category = Category(name=name, slug=slug, description=description)
    db.add(category)
    db.flush()
    return category


def count_products_in_category(db: Session, category_id: int):
    # How many products (active or not) use this category
    query = select(func.count()).select_from(Product).where(Product.category_id == category_id)
    return db.execute(query).scalar_one()


def delete_category(db: Session, category: Category):
    # Delete the category and send the DELETE to the database (the service commits)
    db.delete(category)
    db.flush()
