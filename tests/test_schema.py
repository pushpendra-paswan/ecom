import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Cart, CartItem, Category, Order, Product, User


def test_negative_stock_is_rejected(db_session):
    # Create a seller and a category for the product
    seller = User(email="seller@test.com", password_hash="x", full_name="Seller", role="seller")
    category = Category(name="Books", slug="books")
    db_session.add_all([seller, category])
    db_session.flush()

    # A product with negative stock must fail
    db_session.add(Product(
        seller_id=seller.id, category_id=category.id, name="Bad", description="Bad",
        price=1000, stock=-1,
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_email_is_rejected(db_session):
    # Add two users with the same email
    db_session.add(User(email="same@test.com", password_hash="x", full_name="One"))
    db_session.add(User(email="same@test.com", password_hash="x", full_name="Two"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_second_cart_for_same_user_is_rejected(db_session):
    # Create one user with one cart
    user = User(email="buyer@test.com", password_hash="x", full_name="Buyer")
    db_session.add(user)
    db_session.flush()
    db_session.add(Cart(user_id=user.id))
    db_session.flush()

    # A second cart for the same user must fail
    db_session.add(Cart(user_id=user.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_product_twice_in_one_cart_is_rejected(db_session):
    # Create a user, a cart and a product
    user = User(email="buyer@test.com", password_hash="x", full_name="Buyer")
    category = Category(name="Books", slug="books")
    db_session.add_all([user, category])
    db_session.flush()
    product = Product(
        seller_id=user.id, category_id=category.id, name="Book", description="Book",
        price=1000, stock=5,
    )
    cart = Cart(user_id=user.id)
    db_session.add_all([product, cart])
    db_session.flush()

    # Add the product to the cart, then add it again
    db_session.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=1))
    db_session.flush()
    db_session.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=2))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_role_is_rejected(db_session):
    # A role that is not customer, seller or admin must fail
    db_session.add(User(email="boss@test.com", password_hash="x", full_name="Boss", role="superuser"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_order_status_is_rejected(db_session):
    # Create a user for the order
    user = User(email="buyer@test.com", password_hash="x", full_name="Buyer")
    db_session.add(user)
    db_session.flush()

    # An order with an unknown status must fail
    db_session.add(Order(
        user_id=user.id, status="teleported", total_amount=1000,
        shipping_full_name="Buyer", shipping_phone="1", shipping_line1="Street",
        shipping_city="City", shipping_state="State", shipping_postal_code="1",
        shipping_country="India",
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_cart_item_with_quantity_zero_is_rejected(db_session):
    # Create a user, a cart and a product
    user = User(email="buyer@test.com", password_hash="x", full_name="Buyer")
    category = Category(name="Books", slug="books")
    db_session.add_all([user, category])
    db_session.flush()
    product = Product(
        seller_id=user.id, category_id=category.id, name="Book", description="Book",
        price=1000, stock=5,
    )
    cart = Cart(user_id=user.id)
    db_session.add_all([product, cart])
    db_session.flush()

    # A cart item with quantity 0 must fail
    db_session.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=0))
    with pytest.raises(IntegrityError):
        db_session.flush()
