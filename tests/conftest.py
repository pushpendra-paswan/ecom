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
