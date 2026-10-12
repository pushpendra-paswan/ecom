from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order, OrderItem, Payment


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


def lock_order(db: Session, order_id: int):
    # Find an order and lock its row (SELECT ... FOR UPDATE), or None if it does not exist.
    # Anyone else who wants to change this order waits until our transaction ends.
    # populate_existing makes sure the freshly locked values replace anything already loaded.
    query = (
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.execute(query).scalar_one_or_none()


def get_payment_by_session_id(db: Session, stripe_checkout_session_id: str):
    # Find the payment of a Stripe Checkout Session, or None
    query = select(Payment).where(Payment.stripe_checkout_session_id == stripe_checkout_session_id)
    return db.execute(query).scalar_one_or_none()


def get_payment_by_order_id(db: Session, order_id: int):
    # Find the payment of an order (there is at most one), or None
    query = select(Payment).where(Payment.order_id == order_id)
    return db.execute(query).scalar_one_or_none()
