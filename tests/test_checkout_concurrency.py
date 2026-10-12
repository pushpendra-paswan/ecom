import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import User
from app.services import checkout_service


@pytest.fixture
def stripe_create(monkeypatch):
    # A dummy test key and a fake Stripe call (the real Stripe API is never called)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_dummy")
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.side_effect = lambda **kwargs: SimpleNamespace(
            id="cs_test_" + kwargs["idempotency_key"],
            url="https://checkout.stripe.com/c/pay/fake",
        )
        yield mock_create


def run_checkouts_together(test_engine, checkouts):
    # checkouts is a list of (user_id, address_id). Each one runs in its own thread with its own session.
    # A barrier makes all threads call checkout at the same moment.
    # Returns one result per checkout: ("ok", status_code, response_body) or ("error", status_code, detail).
    session_factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(len(checkouts))
    results = [None] * len(checkouts)

    def run_one(position, user_id, address_id):
        db = session_factory()
        try:
            user = db.get(User, user_id)
            db.commit()
            barrier.wait(timeout=10)
            try:
                body = checkout_service.checkout(db, user, address_id)
                results[position] = ("ok", 201, body)
            except HTTPException as error:
                results[position] = ("error", error.status_code, error.detail)
        finally:
            db.close()

    threads = []
    for position, (user_id, address_id) in enumerate(checkouts):
        thread = threading.Thread(target=run_one, args=(position, user_id, address_id))
        threads.append(thread)
        thread.start()

    # A deadlock would leave a thread running: wait at most 15 seconds and fail if one is still alive
    for thread in threads:
        thread.join(timeout=15)
    for thread in threads:
        assert not thread.is_alive(), "a checkout thread is still running (deadlock?)"

    return results


def read_rows(test_engine, sql):
    with test_engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql)).mappings().all()]


def test_two_buyers_for_the_last_item(test_engine, committed_data, stripe_create):
    # Stock 1, and two customers each have 1 unit in their cart
    (product_id,) = committed_data.products(count=1, stock=1)
    first_user, first_address = committed_data.customer("first@example.com")
    second_user, second_address = committed_data.customer("second@example.com")
    committed_data.put_in_cart(first_user, product_id, 1)
    committed_data.put_in_cart(second_user, product_id, 1)

    results = run_checkouts_together(
        test_engine, [(first_user, first_address), (second_user, second_address)]
    )

    # Exactly one succeeds (201) and the other gets 409
    statuses = sorted(result[1] for result in results)
    assert statuses == [201, 409]
    failure = [result for result in results if result[0] == "error"][0]
    assert failure[2] == "Product 1: out of stock"

    # The stock is 0, there is exactly one order, and one Stripe session
    assert read_rows(test_engine, "SELECT stock FROM products")[0]["stock"] == 0
    assert len(read_rows(test_engine, "SELECT * FROM orders")) == 1
    assert len(read_rows(test_engine, "SELECT * FROM payments")) == 1
    assert stripe_create.call_count == 1


def test_double_submit_creates_one_order(test_engine, committed_data, stripe_create):
    # One customer presses the button twice at the same moment
    (product_id,) = committed_data.products(count=1, stock=10)
    user_id, address_id = committed_data.customer("double@example.com")
    committed_data.put_in_cart(user_id, product_id, 2)

    results = run_checkouts_together(test_engine, [(user_id, address_id), (user_id, address_id)])

    # One order was created (201), the other request found an empty cart (400)
    assert sorted(result[1] for result in results) == [201, 400]
    failure = [result for result in results if result[0] == "error"][0]
    assert failure[2] == "Your cart is empty"
    assert len(read_rows(test_engine, "SELECT * FROM orders")) == 1
    assert read_rows(test_engine, "SELECT stock FROM products")[0]["stock"] == 8
    assert stripe_create.call_count == 1


def test_opposite_product_order_does_not_deadlock(test_engine, committed_data, stripe_create):
    # Plenty of stock. Customer A puts product 1 then 2 in the cart, customer B puts 2 then 1.
    first_product, second_product = committed_data.products(count=2, stock=100)
    user_a, address_a = committed_data.customer("a@example.com")
    user_b, address_b = committed_data.customer("b@example.com")
    committed_data.put_in_cart(user_a, first_product, 1)
    committed_data.put_in_cart(user_a, second_product, 1)
    committed_data.put_in_cart(user_b, second_product, 1)
    committed_data.put_in_cart(user_b, first_product, 1)

    # run_checkouts_together fails the test if a thread is still alive after 15 seconds
    results = run_checkouts_together(test_engine, [(user_a, address_a), (user_b, address_b)])

    # Both succeed
    assert [result[1] for result in results] == [201, 201]
    assert len(read_rows(test_engine, "SELECT * FROM orders")) == 2
    stock = read_rows(test_engine, "SELECT stock FROM products ORDER BY id")
    assert [row["stock"] for row in stock] == [98, 98]
