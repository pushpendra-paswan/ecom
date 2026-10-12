import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

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

    # Create an engine that points at the test database
    engine = create_engine(settings.TEST_DATABASE_URL)
    yield engine
    engine.dispose()


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
