from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app import db as database_module
from app.core.config import settings
from app.db import get_db
from app.models.user import User
from app.services import order_lifecycle_service
from tests.conftest import make_event

# Plain tests for branches that the other test files do not reach (error paths and permission checks)


# ---------- database session and health ----------


def test_get_db_always_closes_the_session():
    fake_session = MagicMock()
    with patch.object(database_module, "SessionLocal", return_value=fake_session):
        # A request that ends normally
        generator = get_db()
        assert next(generator) is fake_session
        generator.close()
        assert fake_session.close.call_count == 1

        # A request that fails in the middle
        generator = get_db()
        next(generator)
        with pytest.raises(RuntimeError):
            generator.throw(RuntimeError("boom"))
        assert fake_session.close.call_count == 2


def test_health_says_503_when_the_database_is_down(client):
    # Every query fails, as if Postgres was down
    with patch("sqlalchemy.orm.Session.execute", side_effect=RuntimeError("database is down")):
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unreachable"}


# ---------- accounts ----------


def test_register_race_on_the_same_email_gives_409(client, create_user):
    create_user("taken@example.com")

    # The first check says "free" (as if both requests checked at the same moment), the unique constraint decides
    with patch("app.services.auth_service.user_repository.get_user_by_email", return_value=None):
        response = client.post(
            "/auth/register", json={"email": "taken@example.com", "password": "Password@123", "full_name": "Twin"}
        )
    assert response.status_code == 409
    assert response.json() == {"detail": "Email is already registered"}


def test_password_over_72_bytes_is_refused_on_register_and_login(client, create_user):
    # 40 characters, 80 bytes (each é uses two bytes)
    long_password = "é" * 40
    response = client.post(
        "/auth/register", json={"email": "bytes@example.com", "password": long_password, "full_name": "Bytes"}
    )
    assert response.status_code == 422
    assert "72 bytes" in response.json()["detail"]

    create_user("real@example.com")
    login = client.post("/auth/login", json={"email": "real@example.com", "password": long_password})
    assert login.status_code == 401
    assert login.json() == {"detail": "Incorrect email or password"}


def test_password_with_a_nul_character_is_refused(client, create_user):
    response = client.post(
        "/auth/register", json={"email": "nul@example.com", "password": "Pass\x00word@123", "full_name": "Nul"}
    )
    assert response.status_code == 422

    create_user("real@example.com")
    login = client.post("/auth/login", json={"email": "real@example.com", "password": "Password@123\x00"})
    assert login.status_code == 401


# ---------- cart, categories ----------


def test_cart_quantity_change_is_refused_when_the_product_sold_out(client, store, change_database):
    product_id = store.product(stock=5)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=store.customer)

    # The last items were sold to someone else
    change_database("UPDATE products SET stock = 0 WHERE id = :id", id=product_id)
    response = client.patch("/cart/items/" + str(product_id), json={"quantity": 1}, headers=store.customer)
    assert response.status_code == 409
    assert response.json() == {"detail": "Out of stock"}


def test_cart_quantity_change_is_refused_when_the_product_was_deactivated(client, store, change_database):
    product_id = store.product(stock=5)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=store.customer)
    change_database("UPDATE products SET is_active = false WHERE id = :id", id=product_id)

    response = client.patch("/cart/items/" + str(product_id), json={"quantity": 2}, headers=store.customer)
    assert response.status_code == 409


def test_category_rename_to_a_name_without_letters_gives_422(client, create_user, auth_headers, create_category):
    create_user("admin@example.com", role="admin")
    admin = auth_headers("admin@example.com")
    category_id = create_category("Books")

    response = client.put("/categories/" + str(category_id), json={"name": "!!!"}, headers=admin)
    assert response.status_code == 422


def test_category_delete_race_with_a_new_product_gives_409(client, store, create_user, auth_headers):
    # The product count says 0 (as if the product was added a moment later), the foreign key decides
    create_user("admin@example.com", role="admin")
    admin = auth_headers("admin@example.com")
    store.product(stock=1)
    category_id = client.get("/categories").json()[0]["id"]

    with patch("app.services.category_service.category_repository.count_products_in_category", return_value=0):
        response = client.delete("/categories/" + str(category_id), headers=admin)
    assert response.status_code == 409
    assert response.json() == {"detail": "Category has products"}


# ---------- order lifecycle ----------


def test_retry_refund_without_a_payment_intent_gives_409(client, store, change_database, refund_create):
    # A cancelled order whose payment succeeded, but Stripe never told us the payment intent
    order = store.place_order([(store.product(stock=5), 1)])
    change_database("UPDATE orders SET status = 'cancelled' WHERE id = :id", id=order.id)
    change_database("UPDATE payments SET status = 'succeeded' WHERE order_id = :id", id=order.id)

    response = client.post("/orders/" + str(order.id) + "/cancel", headers=store.customer)
    assert response.status_code == 409
    assert "no payment to refund" in response.json()["detail"]
    assert refund_create.call_count == 0


def test_cancelling_an_unpaid_order_without_a_test_key_does_not_call_stripe(
    client, store, monkeypatch, session_expire, read_order, read_stock
):
    product_id = store.product(stock=5)
    order = store.place_order([(product_id, 2)])

    # The key setting is empty now: the order is still cancelled and the stock comes back, Stripe is not called
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    response = client.post("/orders/" + str(order.id) + "/cancel", headers=store.customer)
    assert response.status_code == 200
    assert response.json()["payment_status"] == "failed"
    assert session_expire.call_count == 0
    assert read_stock(product_id) == 5


def test_status_service_refuses_a_customer_even_when_called_directly(db_session):
    customer = User(email="c@example.com", password_hash="x", full_name="C", role="customer")
    with pytest.raises(HTTPException) as error:
        order_lifecycle_service.update_order_status(db_session, customer, 1, "shipped")
    assert error.value.status_code == 403


# ---------- webhook ----------


def test_event_without_a_session_id_is_acknowledged_and_ignored(store, post_webhook, read_order):
    order = store.place_order([(store.product(stock=5), 1)])
    event = make_event("checkout.session.completed", None, order)
    assert post_webhook(event).status_code == 200
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_late_payment_without_a_payment_intent_cannot_be_refunded(
    client, store, post_webhook, refund_create, read_order
):
    # The customer cancels first, then a "paid" event arrives that has no payment intent
    order = store.place_order([(store.product(stock=5), 1)])
    assert client.post("/orders/" + str(order.id) + "/cancel", headers=store.customer).status_code == 200

    event = make_event("checkout.session.completed", order.session_id, order, payment_intent=None)
    assert post_webhook(event).status_code == 200
    assert refund_create.call_count == 0
    assert read_order(order.id)["order_status"] == "cancelled"
