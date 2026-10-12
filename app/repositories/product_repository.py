from sqlalchemy import func, select, update
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
    search_text: str | None,
    min_price: int | None,
    max_price: int | None,
    only_in_stock: bool,
    sort: str,
):
    # Build the list of WHERE conditions once. It is used for both the page and the total.
    conditions = []
    if only_active:
        conditions.append(Product.is_active.is_(True))
    if category_id is not None:
        conditions.append(Product.category_id == category_id)
    if seller_id is not None:
        conditions.append(Product.seller_id == seller_id)
    if min_price is not None:
        conditions.append(Product.price >= min_price)
    if max_price is not None:
        conditions.append(Product.price <= max_price)
    if only_in_stock:
        conditions.append(Product.stock > 0)

    # Full-text search on the name and description. websearch_to_tsquery never raises a syntax error.
    search_query = None
    if search_text is not None:
        search_query = func.websearch_to_tsquery("english", search_text)
        conditions.append(Product.search_vector.op("@@")(search_query))

    # Pick the order. Every order ends with id descending, so pages are stable.
    if sort == "relevance" and search_query is not None:
        order_columns = [func.ts_rank(Product.search_vector, search_query).desc(), Product.id.desc()]
    elif sort == "price_asc":
        order_columns = [Product.price.asc(), Product.id.desc()]
    elif sort == "price_desc":
        order_columns = [Product.price.desc(), Product.id.desc()]
    elif sort == "name_asc":
        order_columns = [Product.name.asc(), Product.id.desc()]
    else:
        order_columns = [Product.created_at.desc(), Product.id.desc()]

    # One page of products
    page_query = (
        select(Product)
        .options(joinedload(Product.category), joinedload(Product.seller))
        .where(*conditions)
        .order_by(*order_columns)
        .offset(offset)
        .limit(limit)
    )
    products = list(db.execute(page_query).scalars().all())

    # How many products match the same conditions (all pages)
    count_query = select(func.count()).select_from(Product).where(*conditions)
    total = db.execute(count_query).scalar_one()

    return products, total


def create_product(db: Session, values: dict):
    # Add a new product and send the INSERT to the database (the service commits)
    product = Product(**values)
    db.add(product)
    db.flush()
    return product


def lock_products(db: Session, product_ids: list[int]):
    # Lock many product rows with ONE query (SELECT ... WHERE id IN (...) ORDER BY id FOR UPDATE).
    # Always ascending id order, so two transactions with overlapping products can never deadlock.
    # No joins, because Postgres refuses FOR UPDATE on the outer side of a join.
    # populate_existing makes sure the locked (newest) values replace anything already loaded in the session.
    query = (
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(db.execute(query).scalars().all())


def increase_stock(db: Session, product_id: int, quantity: int):
    # One atomic increment (UPDATE products SET stock = stock + quantity WHERE id = ...).
    # The database adds the numbers, so the app never reads the old stock first.
    query = update(Product).where(Product.id == product_id).values(stock=Product.stock + quantity)
    db.execute(query)
