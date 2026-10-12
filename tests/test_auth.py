from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import text

from app.core.config import settings


def test_register_succeeds_and_hides_password_hash(client):
    response = client.post(
        "/auth/register",
        json={"email": "  New@Example.com ", "password": "secret123", "full_name": "New User"},
    )

    assert response.status_code == 201
    body = response.json()
    # The email is trimmed and lowercased, and the role defaults to customer
    assert body["email"] == "new@example.com"
    assert body["role"] == "customer"
    # No password information may be returned
    assert "password" not in body
    assert "password_hash" not in body


def test_register_as_seller(client):
    response = client.post(
        "/auth/register",
        json={"email": "s@example.com", "password": "secret123", "full_name": "S", "role": "seller"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "seller"


def test_register_duplicate_email_gives_409(client):
    user = {"email": "dup@example.com", "password": "secret123", "full_name": "Dup"}
    client.post("/auth/register", json=user)

    # Same email again, written in a different case
    user["email"] = "DUP@example.com"
    response = client.post("/auth/register", json=user)

    assert response.status_code == 409


def test_register_short_password_gives_422(client):
    response = client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "short", "full_name": "A"},
    )

    assert response.status_code == 422


def test_register_admin_role_gives_422(client):
    response = client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "secret123", "full_name": "A", "role": "admin"},
    )

    assert response.status_code == 422


def test_login_succeeds(client, create_user):
    create_user("login@example.com")

    response = client.post(
        "/auth/login", json={"email": "Login@example.com", "password": "Password@123"}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_wrong_password_and_unknown_email_give_the_same_401(client, create_user):
    create_user("real@example.com")

    wrong_password = client.post(
        "/auth/login", json={"email": "real@example.com", "password": "wrong-password"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "Password@123"}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_disabled_user_cannot_log_in(client, create_user):
    create_user("off@example.com", is_active=False)

    response = client.post(
        "/auth/login", json={"email": "off@example.com", "password": "Password@123"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is disabled"


def test_disabled_account_with_wrong_password_gives_401(client, create_user):
    # The password is checked first, so the disabled state is not revealed to strangers
    create_user("off@example.com", is_active=False)

    response = client.post(
        "/auth/login", json={"email": "off@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_missing_token_gives_401(client):
    response = client.get("/users/me")

    assert response.status_code == 401


def test_garbage_token_gives_401(client):
    response = client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_expired_token_gives_401(client, create_user):
    user_id = create_user("old@example.com")

    # Make a correctly signed token that expired a minute ago
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = jwt.encode(
        {"sub": str(user_id), "exp": expired_at}, settings.JWT_SECRET, algorithm="HS256"
    )

    response = client.get("/users/me", headers={"Authorization": "Bearer " + token})

    assert response.status_code == 401


def test_valid_token_works_until_the_user_is_disabled(client, create_user, auth_headers, test_engine):
    create_user("soon-off@example.com")
    headers = auth_headers("soon-off@example.com")
    assert client.get("/users/me", headers=headers).status_code == 200

    # Disable the user in the database. The token itself is still valid.
    with test_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET is_active = false WHERE email = 'soon-off@example.com'")
        )

    assert client.get("/users/me", headers=headers).status_code == 401
