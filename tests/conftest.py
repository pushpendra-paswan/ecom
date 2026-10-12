import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import bcrypt
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.cart import Cart, CartItem
from app.models.catalog import Category, Product
from app.models.user import Address, User


@pytest.fixture(scope="session")
def test_engine():
    # Work out the test database name from TEST_DATABASE_URL
    test_url = make_url(settings.TEST_DATABASE_URL)

    # Refuse to run if the test database is the same as the dev database
    if test_url.database == make_url(settings.DATABASE_URL).database:
        raise RuntimeError("TEST_DATABASE_URL must point to a different database than DATABASE_URL")

    # Connect to the default "postgres" database to be able to create the test database
    admin_connection = psycopg.connect(
        host=test_url.host,
        port=test_url.port,
        user=test_url.username,
        password=test_url.password,
        dbname="postgres",
        autocommit=True,
    )

    # Create the test database if it does not exist yet
    database_exists = admin_connection.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (test_url.database,)
    ).fetchone()
    if database_exists is None:
        admin_connection.execute(f'CREATE DATABASE "{test_url.database}"')
    admin_connection.close()

    # Point Alembic at the test database
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", settings.TEST_DATABASE_URL)

    # Build the schema with the real migration, starting from an empty database
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    # Create an engine that points at the test database
    engine = create_engine(settings.TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    # Start a transaction that the test can never commit for real
    connection = test_engine.connect()
    outer_transaction = connection.begin()

    # The session joins that transaction (a failed statement only rolls back to a savepoint)
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    yield session

    # Throw away everything the test wrote
    session.close()
    outer_transaction.rollback()
    connection.close()


@pytest.fixture
def client(test_engine):
    # Make a session factory that uses the test database
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    # Replace get_db so the app uses the test database during tests
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Give the test a client, then remove the override afterwards
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

    # The client really commits, so empty the tables after the test
    # (CASCADE also empties every table that points to these two)
    with test_engine.begin() as connection:
        connection.execute(text("TRUNCATE users, categories RESTART IDENTITY CASCADE"))


@pytest.fixture
def create_user(test_engine):
    # Returns a function that inserts a user straight into the test database
    def create(email, role="customer", is_active=True, password="Password@123"):
        # Low bcrypt rounds make the tests faster
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()
        with Session(test_engine) as session:
            user = User(
                email=email,
                password_hash=password_hash,
                full_name="Test " + role,
                role=role,
                is_active=is_active,
            )
            session.add(user)
            session.commit()
            return user.id

    return create


@pytest.fixture
def auth_headers(client):
    # Returns a function that logs in through the API and gives the Authorization header
    def headers_for(email, password="Password@123"):
        response = client.post("/auth/login", json={"email": email, "password": password})
        token = response.json()["access_token"]
        return {"Authorization": "Bearer " + token}

    return headers_for


@pytest.fixture
def create_category(test_engine):
    # Returns a function that inserts a category straight into the test database
    def create(name, slug=None):
        if slug is None:
            slug = name.lower().replace(" ", "-")
        with Session(test_engine) as session:
            category = Category(name=name, slug=slug)
            session.add(category)
            session.commit()
            return category.id

    return create


@pytest.fixture
def create_product(test_engine):
    # Returns a function that inserts a product straight into the test database
    def create(
        seller_id,
        category_id,
        name="Test product",
        price=10000,
        stock=10,
        is_active=True,
        created_at=None,
        description="A test product",
    ):
        with Session(test_engine) as session:
            product = Product(
                seller_id=seller_id,
                category_id=category_id,
                name=name,
                description=description,
                price=price,
                stock=stock,
                is_active=is_active,
            )
            # Tests that check the order of products set created_at themselves
            if created_at is not None:
                product.created_at = created_at
            session.add(product)
            session.commit()
            return product.id

    return create


@pytest.fixture
def committed_data(test_engine, create_user, create_category, create_product):
    # For the concurrency tests: real, committed data made with separate sessions, because several
    # threads (each with its own session and connection) must be able to see it.
    class CommittedData:
        def customer(self, email):
            # A customer with one address; returns (user_id, address_id)
            user_id = create_user(email)
            with Session(test_engine) as session:
                address = Address(
                    user_id=user_id,
                    full_name="Test customer",
                    phone="9876543210",
                    line1="1 Test Road",
                    city="Pune",
                    state="Maharashtra",
                    postal_code="411001",
                    country="India",
                    is_default=True,
                )
                session.add(address)
                session.commit()
                return user_id, address.id

        def products(self, count, stock, price=10000):
            # Several products of one new seller and category; returns their ids in creation order
            seller_id = create_user("seller@example.com", role="seller")
            category_id = create_category("Concurrency")
            product_ids = []
            for number in range(count):
                product_ids.append(
                    create_product(
                        seller_id, category_id, name="Product " + str(number + 1), price=price, stock=stock
                    )
                )
            return product_ids

        def put_in_cart(self, user_id, product_id, quantity):
            # Add one line to the user's cart (the cart row is created if needed)
            with Session(test_engine) as session:
                cart = session.execute(select(Cart).where(Cart.user_id == user_id)).scalar_one_or_none()
                if cart is None:
                    cart = Cart(user_id=user_id)
                    session.add(cart)
                    session.flush()
                session.add(CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity))
                session.commit()

    yield CommittedData()

    # Always remove everything, even when the test failed (CASCADE empties every table that points to these)
    with test_engine.begin() as connection:
        connection.execute(text("TRUNCATE users, categories RESTART IDENTITY CASCADE"))


# The signing secret used by the webhook tests (never a real Stripe secret)
TEST_WEBHOOK_SECRET = "whsec_test_secret_for_tests"


@pytest.fixture
def post_webhook(client, monkeypatch):
    # Use the test signing secret for the app
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)

    # Returns a function that posts a signed Stripe event to /webhooks/stripe.
    # event: a dictionary (turned into JSON bytes), or bytes that are sent as they are.
    # timestamp and secret can be changed to make a bad signature. signed_body (bytes) makes the
    # signature for a different body than the one that is sent (a tampered body).
    def post(event, timestamp=None, secret=TEST_WEBHOOK_SECRET, signed_body=None):
        # The exact bytes that are signed are the exact bytes that are sent
        if isinstance(event, bytes):
            payload = event
        else:
            payload = json.dumps(event).encode()
        if signed_body is None:
            signed_body = payload
        if timestamp is None:
            timestamp = int(time.time())

        # Stripe-Signature: t=<timestamp>,v1=<HMAC-SHA256 of "<timestamp>.<payload>">
        signed_text = str(timestamp).encode() + b"." + signed_body
        signature = hmac.new(secret.encode(), signed_text, hashlib.sha256).hexdigest()
        header = "t=" + str(timestamp) + ",v1=" + signature

        return client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": header, "Content-Type": "application/json"},
        )

    return post


# ---------- shared by the order, webhook and cancel tests (M8, M9) ----------

@pytest.fixture
def stripe_create(monkeypatch):
    # A dummy test key and a fake Stripe Checkout call (the real Stripe API is never called)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_dummy")
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.side_effect = lambda **kwargs: SimpleNamespace(
            id="cs_test_" + kwargs["idempotency_key"], url="https://checkout.stripe.com/c/pay/fake"
        )
        yield mock_create


@pytest.fixture(autouse=True)
def session_expire():
    # Every test gets a fake "expire session" call, so the real Stripe API can never be reached
    with patch("stripe.checkout.Session.expire") as mock_expire:
        mock_expire.return_value = SimpleNamespace(id="cs_test_expired")
        yield mock_expire


@pytest.fixture(autouse=True)
def refund_create():
    # Every test gets a fake refund call, so the real Stripe API can never be reached
    with patch("stripe.Refund.create") as mock_refund:
        mock_refund.return_value = SimpleNamespace(id="re_test_1")
        yield mock_refund


@pytest.fixture
def query_database(test_engine):
    # Returns a function that runs a SELECT on the test database and gives a list of dicts
    def query(sql, **values):
        with test_engine.connect() as connection:
            rows = connection.execute(text(sql), values).mappings().all()
        return [dict(row) for row in rows]

    return query


@pytest.fixture
def change_database(test_engine):
    # Returns a function that runs an UPDATE on the test database
    def change(sql, **values):
        with test_engine.begin() as connection:
            connection.execute(text(sql), values)

    return change


@pytest.fixture
def store(create_user, create_category, create_product, auth_headers, client, stripe_create):
    # A seller, a category, a logged-in customer, and functions that make products and place orders
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_user("customer@example.com")

    class Store:
        customer = auth_headers("customer@example.com")
        first_seller = seller_id

        def product(self, stock=10, price=10000, seller=None):
            # seller is a user id; the default seller is the first one
            if seller is None:
                seller = seller_id
            return create_product(seller, category_id, stock=stock, price=price)

        def place_order(self, items, customer=None):
            # customer is a headers dictionary; the default customer is customer@example.com
            if customer is None:
                customer = self.customer
            # items is a list of (product_id, quantity). Goes through the real checkout API.
            address = client.post(
                "/users/me/addresses",
                json={
                    "full_name": "Rohan Gupta",
                    "phone": "9876543210",
                    "line1": "12 MG Road",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "postal_code": "560001",
                    "country": "India",
                },
                headers=customer,
            )
            for product_id, quantity in items:
                response = client.post(
                    "/cart/items", json={"product_id": product_id, "quantity": quantity}, headers=customer
                )
                assert response.status_code == 200
            response = client.post(
                "/orders/checkout", json={"address_id": address.json()["id"]}, headers=customer
            )
            assert response.status_code == 201
            body = response.json()
            return SimpleNamespace(
                id=body["order_id"],
                total_amount=body["total_amount"],
                session_id="cs_test_order-" + str(body["order_id"]),
            )

    return Store()


@pytest.fixture
def read_order(query_database):
    # Returns a function that gives the order and payment columns we care about
    def read(order_id):
        rows = query_database(
            "SELECT o.status AS order_status, o.updated_at AS order_updated_at,"
            " p.status AS payment_status, p.updated_at AS payment_updated_at,"
            " p.stripe_payment_intent_id AS payment_intent, p.stripe_checkout_session_id AS session_id,"
            " p.stripe_refund_id AS refund_id"
            " FROM orders o JOIN payments p ON p.order_id = o.id WHERE o.id = :order_id",
            order_id=order_id,
        )
        return rows[0]

    return read


@pytest.fixture
def read_stock(query_database):
    # Returns a function that gives the stock of a product
    def read(product_id):
        return query_database("SELECT stock FROM products WHERE id = :id", id=product_id)[0]["stock"]

    return read


def make_event(
    event_type,
    session_id,
    order,
    payment_status="paid",
    amount_total=None,
    currency="inr",
    payment_intent="pi_test_1",
    metadata=None,
    event_id="evt_test_1",
):
    # A minimal but realistic Stripe event. The order can be None (no metadata).
    if amount_total is None:
        amount_total = order.total_amount
    if metadata is None:
        metadata = {"order_id": str(order.id)}
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "payment_status": payment_status,
                "amount_total": amount_total,
                "currency": currency,
                "payment_intent": payment_intent,
                "metadata": metadata,
            }
        },
    }


@pytest.fixture
def pay(post_webhook):
    # Returns a function that pays an order the real way: the "completed" webhook event
    def pay_order(order):
        event = make_event(
            "checkout.session.completed",
            order.session_id,
            order,
            payment_intent="pi_test_" + str(order.id),
            event_id="evt_paid_" + str(order.id),
        )
        assert post_webhook(event).status_code == 200

    return pay_order
