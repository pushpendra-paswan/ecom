from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import Product
from app.models.order import Order, OrderItem, Payment
from app.models.user import User


def create_order(db: Session, values: dict):
    # Add a new order and send the INSERT to the database (the service commits)
    order = Order(**values)
    db.add(order)
    db.flush()
    return order


def create_order_items(db: Session, order_id: int, items: list[dict]):
    # Add all the lines of an order (the service commits)
    order_items = []
    for item in items:
        order_item = OrderItem(order_id=order_id, **item)
        db.add(order_item)
        order_items.append(order_item)
    db.flush()
    return order_items


def create_payment(db: Session, values: dict):
    # Add the payment row of an order (the service commits)
    payment = Payment(**values)
    db.add(payment)
    db.flush()
    return payment


def list_orders(db: Session, user_id: int, offset: int, limit: int):
    # One page of this user's orders, newest first (id descending breaks ties).
    # selectinload fetches the items of all orders on the page with ONE extra query.
    page_query = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    )
    orders = list(db.execute(page_query).scalars().all())

    # How many orders this user has in total
    count_query = select(func.count()).select_from(Order).where(Order.user_id == user_id)
    total = db.execute(count_query).scalar_one()

    return orders, total


def get_order(db: Session, user_id: int, order_id: int):
    # Find an order with its items and payment, only if it belongs to this user, otherwise None
    query = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.payment))
        .where(Order.id == order_id, Order.user_id == user_id)
    )
    return db.execute(query).scalar_one_or_none()


def lock_order(db: Session, order_id: int, user_id: int | None = None):
    # Find an order and lock its row (SELECT ... FOR UPDATE), or None if it does not exist.
    # Anyone else who wants to change this order waits until our transaction ends.
    # With a user_id, only that user's order is found (someone else's order is never even locked).
    # populate_existing makes sure the freshly locked values replace anything already loaded.
    query = select(Order).where(Order.id == order_id)
    if user_id is not None:
        query = query.where(Order.user_id == user_id)
    query = query.with_for_update().execution_options(populate_existing=True)
    return db.execute(query).scalar_one_or_none()


def get_payment_by_session_id(db: Session, stripe_checkout_session_id: str):
    # Find the payment of a Stripe Checkout Session, or None
    query = select(Payment).where(Payment.stripe_checkout_session_id == stripe_checkout_session_id)
    return db.execute(query).scalar_one_or_none()


def get_payment_by_order_id(db: Session, order_id: int):
    # Find the payment of an order (there is at most one), or None
    query = select(Payment).where(Payment.order_id == order_id)
    return db.execute(query).scalar_one_or_none()


def mark_payment_refunded(db: Session, payment_id: int, stripe_refund_id: str | None):
    # Set the payment to refunded and save the refund id (one atomic UPDATE, the service commits).
    # A payment that is already refunded is left alone, so a second call can never erase the refund id.
    query = (
        update(Payment)
        .where(Payment.id == payment_id, Payment.status != "refunded")
        .values(status="refunded", stripe_refund_id=stripe_refund_id)
    )
    db.execute(query)


def list_item_seller_ids(db: Session, order_id: int):
    # The seller of every line of an order (one entry per line)
    query = (
        select(Product.seller_id)
        .select_from(OrderItem)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order_id)
    )
    return list(db.execute(query).scalars().all())


def list_orders_for_seller(db: Session, seller_id: int, offset: int, limit: int):
    # One page of the orders a seller may see: the payment succeeded or was refunded (so abandoned
    # and unpaid checkouts never appear) and at least one line is this seller's (an EXISTS condition).
    conditions = [
        Payment.status.in_(["succeeded", "refunded"]),
        select(OrderItem.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == Order.id, Product.seller_id == seller_id)
        .exists(),
    ]

    # The lines and their products come with the page, so there is no query per order
    page_query = (
        select(Order)
        .join(Payment, Payment.order_id == Order.id)
        .options(selectinload(Order.items).joinedload(OrderItem.product))
        .where(*conditions)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    )
    orders = list(db.execute(page_query).scalars().all())

    # How many orders match the same conditions (all pages)
    count_query = (
        select(func.count())
        .select_from(Order)
        .join(Payment, Payment.order_id == Order.id)
        .where(*conditions)
    )
    total = db.execute(count_query).scalar_one()

    return orders, total


def get_order_for_seller(db: Session, seller_id: int, order_id: int):
    # One order, only if this seller may see it (same rules as the list), otherwise None
    query = (
        select(Order)
        .join(Payment, Payment.order_id == Order.id)
        .options(selectinload(Order.items).joinedload(OrderItem.product))
        .where(
            Order.id == order_id,
            Payment.status.in_(["succeeded", "refunded"]),
            select(OrderItem.id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(OrderItem.order_id == Order.id, Product.seller_id == seller_id)
            .exists(),
        )
    )
    return db.execute(query).scalar_one_or_none()


def list_orders_for_admin(db: Session, status: str | None, offset: int, limit: int):
    # One page of all orders, newest first, with the customer's email. Optional status filter.
    conditions = []
    if status is not None:
        conditions.append(Order.status == status)

    # Each row is (order, customer email). The lines come with the page in one extra query.
    page_query = (
        select(Order, User.email)
        .join(User, User.id == Order.user_id)
        .options(selectinload(Order.items))
        .where(*conditions)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(db.execute(page_query).all())

    # How many orders match the same conditions (all pages)
    count_query = select(func.count()).select_from(Order).where(*conditions)
    total = db.execute(count_query).scalar_one()

    return rows, total


def get_order_for_admin(db: Session, order_id: int):
    # One order with its customer's email, lines and payment: a row (order, email), or None
    query = (
        select(Order, User.email)
        .join(User, User.id == Order.user_id)
        .options(selectinload(Order.items), selectinload(Order.payment))
        .where(Order.id == order_id)
    )
    return db.execute(query).first()
