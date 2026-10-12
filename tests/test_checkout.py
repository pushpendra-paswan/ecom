import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.catalog import Product
from app.models.order import Order, OrderItem

CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_fake"


@pytest.fixture
def stripe_create(monkeypatch):
    # Use a dummy test key and replace the real Stripe call. The real Stripe API is never called.
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_dummy")
    with patch("stripe.checkout.Session.create") as mock_create:
        # Every call gets its own session id, because the session id is unique in the payments table
        mock_create.side_effect = lambda **kwargs: SimpleNamespace(
            id="cs_test_" + kwargs["idempotency_key"], url=CHECKOUT_URL
        )
        yield mock_create


@pytest.fixture
def query_database(test_engine):
    # Returns a function that runs a SELECT on the test database and gives a list of dicts
    def query(sql, **values):
        with test_engine.connect() as connection:
            rows = connection.execute(text(sql), values).mappings().all()
        return [dict(row) for row in rows]

    return query


@pytest.fixture
def shop(create_user, create_category, create_product, auth_headers, client, test_engine):
    # A seller, a category, two logged-in customers, and functions that make products,
    # addresses and cart lines
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    customer_id = create_user("customer@example.com")
    other_customer_id = create_user("other@example.com")

    class Shop:
        customer = auth_headers("customer@example.com")
        other_customer = auth_headers("other@example.com")
        customer_id = None
        other_customer_id = None

        def product(self, **changes):
            return create_product(seller_id, category_id, **changes)

        def address(self, headers=None, **changes):
            body = {
                "full_name": "Rohan Gupta",
                "phone": "9876543210",
                "line1": "12 MG Road",
                "line2": "Near the park",
                "city": "Bengaluru",
                "state": "Karnataka",
                "postal_code": "560001",
                "country": "India",
            }
            body.update(changes)
            response = client.post(
                "/users/me/addresses", json=body, headers=headers or self.customer
            )
            assert response.status_code == 201
            return response.json()["id"]

        def add_to_cart(self, product_id, quantity=1, headers=None):
            response = client.post(
                "/cart/items",
                json={"product_id": product_id, "quantity": quantity},
                headers=headers or self.customer,
            )
            assert response.status_code == 200

        def change_product(self, product_id, **values):
            with Session(test_engine) as session:
                product = session.get(Product, product_id)
                for field, value in values.items():
                    setattr(product, field, value)
                session.commit()

    shop = Shop()
    shop.customer_id = customer_id
    shop.other_customer_id = other_customer_id
    return shop


def checkout(client, headers, address_id):
    return client.post("/orders/checkout", json={"address_id": address_id}, headers=headers)


# ---------- access ----------


def test_every_order_endpoint_needs_a_customer(client, create_user, auth_headers):
    create_user("seller@example.com", role="seller")
    create_user("admin@example.com", role="admin")
    calls = [
        ("post", "/orders/checkout", {"address_id": 1}),
        ("get", "/orders", None),
        ("get", "/orders/1", None),
    ]

    for method, path, body in calls:
        # No token: 401
        response = client.request(method, path, json=body)
        assert response.status_code == 401, (method, path)

        # A seller or an admin: 403
        for email in ("seller@example.com", "admin@example.com"):
            response = client.request(method, path, json=body, headers=auth_headers(email))
            assert response.status_code == 403, (method, path, email)


# ---------- the happy path ----------


def test_checkout_creates_the_order_and_payment(client, shop, stripe_create, query_database):
    pen = shop.product(name="Pen", price=15000, stock=10)
    book = shop.product(name="Book", price=49950, stock=5)
    address_id = shop.address()
    shop.add_to_cart(pen, 2)
    shop.add_to_cart(book, 1)

    response = checkout(client, shop.customer, address_id)

    # The answer: order id, the Stripe URL and the total (2 x 150.00 + 499.50)
    assert response.status_code == 201
    body = response.json()
    assert body["checkout_url"] == CHECKOUT_URL
    assert body["total_amount"] == 2 * 15000 + 49950
    order_id = body["order_id"]

    # The order is waiting for payment, with the right total and owner
    orders = query_database("SELECT * FROM orders")
    assert len(orders) == 1
    assert orders[0]["id"] == order_id
    assert orders[0]["user_id"] == shop.customer_id
    assert orders[0]["status"] == "pending_payment"
    assert orders[0]["total_amount"] == 79950

    # The order items hold the name, the price and the quantity
    items = query_database("SELECT * FROM order_items ORDER BY id")
    assert [(i["product_id"], i["product_name"], i["unit_price"], i["quantity"]) for i in items] == [
        (pen, "Pen", 15000, 2),
        (book, "Book", 49950, 1),
    ]

    # The stock went down by the quantities
    stock = query_database("SELECT id, stock FROM products ORDER BY id")
    assert [(row["id"], row["stock"]) for row in stock] == [(pen, 8), (book, 4)]

    # The payment is pending, with the amount, the currency and the mocked session id
    payments = query_database("SELECT * FROM payments")
    assert len(payments) == 1
    assert payments[0]["order_id"] == order_id
    assert payments[0]["status"] == "pending"
    assert payments[0]["amount"] == 79950
    assert payments[0]["currency"] == settings.STRIPE_CURRENCY
    assert payments[0]["stripe_checkout_session_id"] == "cs_test_order-" + str(order_id)
    assert payments[0]["stripe_payment_intent_id"] is None

    # The cart is empty, but the cart row stays
    assert query_database("SELECT * FROM cart_items") == []
    assert len(query_database("SELECT * FROM carts")) == 1


def test_stripe_is_called_once_with_values_from_the_database(
    client, shop, stripe_create, query_database
):
    pen = shop.product(name="Pen", price=15000, stock=10)
    book = shop.product(name="Book", price=49950, stock=5)
    address_id = shop.address()
    shop.add_to_cart(pen, 3)
    shop.add_to_cart(book, 1)

    response = checkout(client, shop.customer, address_id)
    order_id = response.json()["order_id"]

    # Stripe was called exactly once
    assert stripe_create.call_count == 1
    arguments = stripe_create.call_args.kwargs

    # The line items are the order items from the database
    order_items = query_database("SELECT * FROM order_items ORDER BY id")
    stripe_lines = [
        (
            line["price_data"]["product_data"]["name"],
            line["price_data"]["unit_amount"],
            line["quantity"],
            line["price_data"]["currency"],
        )
        for line in arguments["line_items"]
    ]
    database_lines = [
        (item["product_name"], item["unit_price"], item["quantity"], settings.STRIPE_CURRENCY)
        for item in order_items
    ]
    assert stripe_lines == database_lines

    # The other settings
    assert arguments["mode"] == "payment"
    assert arguments["api_key"] == "sk_test_dummy"
    assert arguments["client_reference_id"] == str(order_id)
    assert arguments["metadata"] == {"order_id": str(order_id)}
    assert arguments["customer_email"] == "customer@example.com"
    assert arguments["idempotency_key"] == "order-" + str(order_id)
    assert arguments["success_url"] == (
        settings.FRONTEND_BASE_URL + "/order-success.html?order_id=" + str(order_id)
    )
    assert arguments["cancel_url"] == (
        settings.FRONTEND_BASE_URL + "/order-cancelled.html?order_id=" + str(order_id)
    )

    # The session expires in about 30 minutes (an integer Unix timestamp)
    assert isinstance(arguments["expires_at"], int)
    minutes_ahead = (arguments["expires_at"] - time.time()) / 60
    assert 29 < minutes_ahead < 31


# ---------- snapshots ----------


def test_old_orders_do_not_change_when_the_product_or_address_changes(
    client, shop, stripe_create, query_database
):
    pen = shop.product(name="Pen", price=15000, stock=10)
    address_id = shop.address()
    shop.add_to_cart(pen, 2)
    order_id = checkout(client, shop.customer, address_id).json()["order_id"]

    # Change the price and the name of the product, then edit and delete the address
    shop.change_product(pen, price=99900, name="Gold Pen")
    response = client.put(
        "/users/me/addresses/" + str(address_id),
        json={
            "full_name": "Someone Else",
            "phone": "1",
            "line1": "New street",
            "city": "Delhi",
            "state": "Delhi",
            "postal_code": "110001",
        },
        headers=shop.customer,
    )
    assert response.status_code == 200
    response = client.delete("/users/me/addresses/" + str(address_id), headers=shop.customer)
    assert response.status_code == 204

    # The order item still has the old name and price
    items = query_database("SELECT * FROM order_items")
    assert items[0]["unit_price"] == 15000
    assert items[0]["product_name"] == "Pen"

    # The order still has the old address
    orders = query_database("SELECT * FROM orders WHERE id = :id", id=order_id)
    assert orders[0]["shipping_full_name"] == "Rohan Gupta"
    assert orders[0]["shipping_phone"] == "9876543210"
    assert orders[0]["shipping_line1"] == "12 MG Road"
    assert orders[0]["shipping_line2"] == "Near the park"
    assert orders[0]["shipping_city"] == "Bengaluru"
    assert orders[0]["shipping_state"] == "Karnataka"
    assert orders[0]["shipping_postal_code"] == "560001"
    assert orders[0]["shipping_country"] == "India"

    # The order detail shows the same old values
    detail = client.get("/orders/" + str(order_id), headers=shop.customer).json()
    assert detail["shipping_address"]["city"] == "Bengaluru"
    assert detail["items"][0]["unit_price"] == 15000


# ---------- bad input and nothing changes ----------


def test_bad_address_creates_nothing(client, shop, stripe_create, query_database):
    pen = shop.product(price=15000, stock=10)
    shop.address()
    other_address_id = shop.address(headers=shop.other_customer)
    shop.add_to_cart(pen, 2)

    cart_before = query_database("SELECT * FROM cart_items")

    # Someone else's address and an address that does not exist: 404
    response = checkout(client, shop.customer, other_address_id)
    assert response.status_code == 404
    assert response.json()["detail"] == "Address not found"
    response = checkout(client, shop.customer, 99999)
    assert response.status_code == 404
    assert response.json()["detail"] == "Address not found"

    # Zero, text and a missing body: 422
    response = client.post("/orders/checkout", json={"address_id": 0}, headers=shop.customer)
    assert response.status_code == 422
    response = client.post("/orders/checkout", json={"address_id": "abc"}, headers=shop.customer)
    assert response.status_code == 422
    response = client.post("/orders/checkout", headers=shop.customer)
    assert response.status_code == 422

    # Nothing happened: no order, no payment, same stock, same cart, no Stripe call
    assert query_database("SELECT * FROM orders") == []
    assert query_database("SELECT * FROM payments") == []
    assert query_database("SELECT stock FROM products")[0]["stock"] == 10
    assert query_database("SELECT * FROM cart_items") == cart_before
    assert stripe_create.call_count == 0


def test_empty_cart_gives_400(client, shop, stripe_create, query_database):
    address_id = shop.address()

    # No cart row at all
    assert query_database("SELECT * FROM carts") == []
    response = checkout(client, shop.customer, address_id)
    assert response.status_code == 400
    assert response.json()["detail"] == "Your cart is empty"

    # A cart row with no lines
    pen = shop.product()
    shop.add_to_cart(pen, 1)
    client.delete("/cart", headers=shop.customer)
    assert len(query_database("SELECT * FROM carts")) == 1
    response = checkout(client, shop.customer, address_id)
    assert response.status_code == 400
    assert response.json()["detail"] == "Your cart is empty"

    assert query_database("SELECT * FROM orders") == []
    assert stripe_create.call_count == 0


def test_cart_problems_give_409_with_the_product_names(client, shop, stripe_create, query_database):
    address_id = shop.address()
    gone = shop.product(name="Gone Pen", stock=10)
    sold_out = shop.product(name="Sold Out Pen", stock=10)
    few = shop.product(name="Few Pens", stock=10)
    shop.add_to_cart(gone, 1)
    shop.add_to_cart(sold_out, 1)
    shop.add_to_cart(few, 5)

    # An inactive product, a product with stock 0 and a product with too little stock
    shop.change_product(gone, is_active=False)
    shop.change_product(sold_out, stock=0)
    shop.change_product(few, stock=3)

    response = checkout(client, shop.customer, address_id)

    # One message names every bad line
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "Gone Pen: no longer available" in detail
    assert "Sold Out Pen: out of stock" in detail
    assert "Few Pens: only 3 left" in detail

    # Nothing changed
    assert query_database("SELECT * FROM orders") == []
    assert query_database("SELECT * FROM payments") == []
    assert len(query_database("SELECT * FROM cart_items")) == 3
    assert stripe_create.call_count == 0


def test_one_bad_line_stops_the_whole_checkout(client, shop, stripe_create, query_database):
    address_id = shop.address()
    good = shop.product(name="Good Pen", stock=10)
    bad = shop.product(name="Bad Pen", stock=10)
    shop.add_to_cart(good, 2)
    shop.add_to_cart(bad, 4)
    shop.change_product(bad, stock=1)

    stock_before = query_database("SELECT id, stock FROM products ORDER BY id")
    cart_before = query_database("SELECT * FROM cart_items ORDER BY id")

    response = checkout(client, shop.customer, address_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "Bad Pen: only 1 left"
    assert query_database("SELECT * FROM orders") == []
    assert query_database("SELECT * FROM order_items") == []
    assert query_database("SELECT * FROM payments") == []
    assert query_database("SELECT id, stock FROM products ORDER BY id") == stock_before
    assert query_database("SELECT * FROM cart_items ORDER BY id") == cart_before


# ---------- Stripe problems ----------


def test_stripe_failure_gives_everything_back(client, shop, stripe_create, query_database):
    pen = shop.product(name="Pen", price=15000, stock=10)
    book = shop.product(name="Book", price=49950, stock=5)
    address_id = shop.address()
    shop.add_to_cart(pen, 3)
    shop.add_to_cart(book, 2)
    stripe_create.side_effect = stripe.APIConnectionError("secret-network-details")

    response = checkout(client, shop.customer, address_id)

    # A generic message, without the Stripe error text
    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Payment service is unavailable. Your cart has not been changed. Please try again."
    )
    assert "secret-network-details" not in response.text

    # The order is cancelled and the payment failed
    orders = query_database("SELECT * FROM orders")
    assert len(orders) == 1
    assert orders[0]["status"] == "cancelled"
    payments = query_database("SELECT * FROM payments")
    assert payments[0]["status"] == "failed"
    assert payments[0]["stripe_checkout_session_id"] is None

    # The stock is back
    stock = query_database("SELECT id, stock FROM products ORDER BY id")
    assert [(row["id"], row["stock"]) for row in stock] == [(pen, 10), (book, 5)]

    # The cart items are back with their quantities
    cart = client.get("/cart", headers=shop.customer).json()
    assert [(line["product_id"], line["quantity"]) for line in cart["items"]] == [
        (pen, 3),
        (book, 2),
    ]


def test_missing_or_live_stripe_key_gives_503(client, shop, stripe_create, monkeypatch, query_database):
    pen = shop.product(stock=10)
    address_id = shop.address()
    shop.add_to_cart(pen, 1)

    # No key
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    response = checkout(client, shop.customer, address_id)
    assert response.status_code == 503
    assert response.json()["detail"] == "Payments are not configured"

    # A live key
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_dummy")
    response = checkout(client, shop.customer, address_id)
    assert response.status_code == 503
    assert response.json()["detail"] == "Only Stripe test keys are allowed"

    # Nothing was created or changed
    assert query_database("SELECT * FROM orders") == []
    assert query_database("SELECT stock FROM products")[0]["stock"] == 10
    assert len(query_database("SELECT * FROM cart_items")) == 1
    assert stripe_create.call_count == 0


# ---------- reading orders ----------


def test_order_list_shows_only_my_orders_newest_first(client, shop, test_engine):
    pen = shop.product(name="Pen", price=15000)
    book = shop.product(name="Book", price=20000)
    with Session(test_engine) as session:
        # Three orders for the customer (two with the same time) and one for the other customer
        now = datetime.now(timezone.utc)
        order_ids = []
        for user_id, minutes_ago in [
            (shop.customer_id, 30),
            (shop.customer_id, 10),
            (shop.customer_id, 10),
            (shop.other_customer_id, 1),
        ]:
            order = Order(
                user_id=user_id,
                status="pending_payment",
                total_amount=15000,
                shipping_full_name="A",
                shipping_phone="1",
                shipping_line1="B",
                shipping_city="C",
                shipping_state="D",
                shipping_postal_code="E",
                shipping_country="India",
                created_at=now - timedelta(minutes=minutes_ago),
            )
            session.add(order)
            session.flush()
            order_ids.append(order.id)
        # The first order has two items, the second has one
        session.add(OrderItem(order_id=order_ids[0], product_id=pen, product_name="Pen", unit_price=15000, quantity=2))
        session.add(OrderItem(order_id=order_ids[0], product_id=book, product_name="Book", unit_price=20000, quantity=1))
        session.add(OrderItem(order_id=order_ids[1], product_id=pen, product_name="Pen", unit_price=15000, quantity=4))
        session.commit()

    # Newest first; the two orders with the same time are ordered by id descending
    response = client.get("/orders", headers=shop.customer)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [order["id"] for order in body["items"]] == [order_ids[2], order_ids[1], order_ids[0]]

    # item_count is the total quantity and the items are listed
    oldest = body["items"][2]
    assert oldest["status"] == "pending_payment"
    assert oldest["total_amount"] == 15000
    assert oldest["item_count"] == 3
    assert sorted(item["product_name"] for item in oldest["items"]) == ["Book", "Pen"]
    assert set(oldest["items"][0].keys()) == {"product_id", "product_name", "unit_price", "quantity"}
    assert body["items"][1]["item_count"] == 4
    assert body["items"][0]["items"] == []

    # Pagination
    response = client.get("/orders?page=2&page_size=2", headers=shop.customer)
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 2
    assert [order["id"] for order in body["items"]] == [order_ids[0]]

    # The other customer sees only their own order
    other = client.get("/orders", headers=shop.other_customer).json()
    assert [order["id"] for order in other["items"]] == [order_ids[3]]

    # Bad page values: 422
    assert client.get("/orders?page=0", headers=shop.customer).status_code == 422
    assert client.get("/orders?page_size=101", headers=shop.customer).status_code == 422


def test_order_detail_and_privacy(client, shop, stripe_create):
    pen = shop.product(name="Pen", price=15000, stock=10)
    book = shop.product(name="Book", price=49950, stock=5)
    address_id = shop.address()
    shop.add_to_cart(pen, 2)
    shop.add_to_cart(book, 1)
    order_id = checkout(client, shop.customer, address_id).json()["order_id"]

    response = client.get("/orders/" + str(order_id), headers=shop.customer)

    # The shape of the detail
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id", "status", "total_amount", "created_at", "shipping_address", "items", "payment",
    }
    assert body["id"] == order_id
    assert body["status"] == "pending_payment"
    assert body["total_amount"] == 79950
    assert body["shipping_address"] == {
        "full_name": "Rohan Gupta",
        "phone": "9876543210",
        "line1": "12 MG Road",
        "line2": "Near the park",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560001",
        "country": "India",
    }
    assert body["items"] == [
        {"product_id": pen, "product_name": "Pen", "unit_price": 15000, "quantity": 2, "line_total": 30000},
        {"product_id": book, "product_name": "Book", "unit_price": 49950, "quantity": 1, "line_total": 49950},
    ]
    assert body["payment"] == {"status": "pending", "amount": 79950, "currency": settings.STRIPE_CURRENCY}

    # No Stripe ids anywhere, in the detail or in the list
    listing = client.get("/orders", headers=shop.customer)
    for text_body in (response.text, listing.text):
        assert "cs_test_" not in text_body
        assert "stripe" not in text_body.lower()
        assert "payment_intent" not in text_body

    # Another customer gets 404 (not 403), and so does an order that does not exist
    response = client.get("/orders/" + str(order_id), headers=shop.other_customer)
    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"
    assert client.get("/orders/99999", headers=shop.customer).status_code == 404

    # An id that is not a number: 422
    assert client.get("/orders/abc", headers=shop.customer).status_code == 422
