from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.models.cart import Cart, CartItem


def list_cart_items(db: Session, user_id: int):
    # All lines of the user's cart with their products, in ONE query, oldest line first
    query = (
        select(CartItem)
        .join(Cart, Cart.id == CartItem.cart_id)
        .options(joinedload(CartItem.product))
        .where(Cart.user_id == user_id)
        .order_by(CartItem.id)
    )
    return list(db.execute(query).scalars().all())


def get_cart_item(db: Session, user_id: int, product_id: int):
    # One line of the user's cart with its product, or None. Only this user's cart is searched.
    query = (
        select(CartItem)
        .join(Cart, Cart.id == CartItem.cart_id)
        .options(joinedload(CartItem.product))
        .where(Cart.user_id == user_id, CartItem.product_id == product_id)
    )
    return db.execute(query).scalar_one_or_none()


def count_cart_quantity(db: Session, user_id: int):
    # The sum of the quantities of all lines (0 when there is no cart or no lines)
    query = (
        select(func.coalesce(func.sum(CartItem.quantity), 0))
        .join(Cart, Cart.id == CartItem.cart_id)
        .where(Cart.user_id == user_id)
    )
    return db.execute(query).scalar_one()


def get_or_create_cart_id(db: Session, user_id: int):
    # Create the cart in one atomic statement. If it already exists, nothing happens,
    # so two requests at the same moment can never create two carts or fail.
    insert_statement = insert(Cart).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"])
    db.execute(insert_statement)

    # Read the cart id (it exists now, created by this request or an earlier one)
    return db.execute(select(Cart.id).where(Cart.user_id == user_id)).scalar_one()


def upsert_cart_item(db: Session, cart_id: int, product_id: int, quantity: int):
    # One atomic statement: insert the line, or add to the quantity of the existing line.
    # The old quantity is never read first, so two requests at the same moment both count.
    insert_statement = insert(CartItem).values(cart_id=cart_id, product_id=product_id, quantity=quantity)
    upsert_statement = insert_statement.on_conflict_do_update(
        constraint="uq_cart_items_cart_id_product_id",
        set_={"quantity": CartItem.quantity + insert_statement.excluded.quantity},
    ).returning(CartItem.quantity)

    # RETURNING gives the new quantity of the line
    return db.execute(upsert_statement).scalar_one()


def delete_cart_item(db: Session, user_id: int, product_id: int):
    # Remove one line, only from this user's cart (does nothing if the line does not exist)
    users_cart = select(Cart.id).where(Cart.user_id == user_id)
    db.execute(
        delete(CartItem).where(CartItem.cart_id.in_(users_cart), CartItem.product_id == product_id)
    )


def delete_all_cart_items(db: Session, user_id: int):
    # Remove every line of this user's cart. The cart row stays.
    users_cart = select(Cart.id).where(Cart.user_id == user_id)
    db.execute(delete(CartItem).where(CartItem.cart_id.in_(users_cart)))
