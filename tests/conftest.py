import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db import get_db
from app.main import app


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
