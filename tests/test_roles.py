from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import require_customer, require_seller
from app.db import get_db
from app.main import app


def test_admin_users_needs_a_token(client):
    assert client.get("/admin/users").status_code == 401


def test_admin_users_forbidden_for_customer_and_seller(client, create_user, auth_headers):
    create_user("customer@example.com", role="customer")
    create_user("seller@example.com", role="seller")

    customer = client.get("/admin/users", headers=auth_headers("customer@example.com"))
    seller = client.get("/admin/users", headers=auth_headers("seller@example.com"))

    assert customer.status_code == 403
    assert seller.status_code == 403


def test_admin_users_allowed_for_admin(client, create_user, auth_headers):
    create_user("admin@example.com", role="admin")

    response = client.get("/admin/users", headers=auth_headers("admin@example.com"))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["items"][0]["email"] == "admin@example.com"
    assert "password_hash" not in body["items"][0]


def test_admin_users_pagination(client, create_user, auth_headers):
    # 5 users in total
    create_user("admin@example.com", role="admin")
    for number in range(4):
        create_user(f"user{number}@example.com")
    headers = auth_headers("admin@example.com")

    page_one = client.get("/admin/users?page=1&page_size=2", headers=headers).json()
    page_three = client.get("/admin/users?page=3&page_size=2", headers=headers).json()
    page_four = client.get("/admin/users?page=4&page_size=2", headers=headers).json()

    assert page_one["total"] == 5
    assert len(page_one["items"]) == 2
    assert len(page_three["items"]) == 1
    assert page_four["items"] == []

    # Invalid page values are rejected
    assert client.get("/admin/users?page=0", headers=headers).status_code == 422
    assert client.get("/admin/users?page_size=0", headers=headers).status_code == 422
    assert client.get("/admin/users?page_size=101", headers=headers).status_code == 422


def test_require_customer_and_require_seller(client, create_user, auth_headers):
    # A tiny app with two throwaway routes
    tiny_app = FastAPI()

    @tiny_app.get("/customers-only")
    def customers_only(user=Depends(require_customer)):
        return {"role": user.role}

    @tiny_app.get("/sellers-only")
    def sellers_only(user=Depends(require_seller)):
        return {"role": user.role}

    # Use the same test database as the real app
    tiny_app.dependency_overrides[get_db] = app.dependency_overrides[get_db]
    tiny_client = TestClient(tiny_app)

    create_user("customer@example.com", role="customer")
    create_user("seller@example.com", role="seller")
    create_user("admin@example.com", role="admin")
    customer = auth_headers("customer@example.com")
    seller = auth_headers("seller@example.com")
    admin = auth_headers("admin@example.com")

    # No token
    assert tiny_client.get("/customers-only").status_code == 401
    assert tiny_client.get("/sellers-only").status_code == 401

    # The role must match exactly (an admin is not a customer or a seller here)
    assert tiny_client.get("/customers-only", headers=customer).status_code == 200
    assert tiny_client.get("/customers-only", headers=seller).status_code == 403
    assert tiny_client.get("/customers-only", headers=admin).status_code == 403
    assert tiny_client.get("/sellers-only", headers=seller).status_code == 200
    assert tiny_client.get("/sellers-only", headers=customer).status_code == 403
    assert tiny_client.get("/sellers-only", headers=admin).status_code == 403
