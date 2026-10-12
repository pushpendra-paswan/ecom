import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import User
from app.services import checkout_service, order_lifecycle_service
from tests.conftest import make_event


@pytest.fixture
def shop(test_engine, committed_data, create_user, monkeypatch):
    # One committed pending order (made by the real checkout service) of 3 units of a product with stock 10,
    # plus an admin user. The customer's cart is empty afterwards.
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_dummy")
    (product_id,) = committed_data.products(count=1, stock=10)
    customer_id, address_id = committed_data.customer("buyer@example.com")
    admin_id = create_user("admin@example.com", role="admin")
    committed_data.put_in_cart(customer_id, product_id, 3)

    session_factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.side_effect = lambda **kwargs: SimpleNamespace(
            id="cs_test_" + kwargs["idempotency_key"], url="https://checkout.stripe.com/c/pay/fake"
        )
        with session_factory() as db:
            body = checkout_service.checkout(db, db.get(User, customer_id), address_id)

    return SimpleNamespace(
        session_factory=session_factory,
        customer_id=customer_id,
        admin_id=admin_id,
        product_id=product_id,
        order_id=body["order_id"],
        total_amount=body["total_amount"],
        session_id="cs_test_order-" + str(body["order_id"]),
    )


def webhook_event(shop, event_type="checkout.session.completed"):
    # The Stripe event that says this order was paid
    order = SimpleNamespace(id=shop.order_id, total_amount=shop.total_amount)
    return make_event(event_type, shop.session_id, order, payment_intent="pi_test_concurrent")


def run_together(actions):
    # Runs every action in its own thread, lined up by a barrier so they start at the same moment.
    # Each action returns an HTTP status code. Waits at most 15 seconds and fails if a thread is still alive.
    barrier = threading.Barrier(len(actions))
    results = [None] * len(actions)

    def run(position):
        barrier.wait(timeout=10)
        results[position] = actions[position]()

    threads = [threading.Thread(target=run, args=(position,)) for position in range(len(actions))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    for thread in threads:
        assert not thread.is_alive(), "a thread is still running (deadlock?)"
    return results


def cancel_action(shop):
    # The customer cancels the order. Returns the status code the API would answer.
    def action():
        with shop.session_factory() as db:
            try:
                order_lifecycle_service.cancel_order(db, db.get(User, shop.customer_id), shop.order_id)
            except HTTPException as error:
                return error.status_code
        return 200

    return action


def ship_action(shop):
    # The admin marks the order as shipped
    def action():
        with shop.session_factory() as db:
            try:
                order_lifecycle_service.update_order_status(db, db.get(User, shop.admin_id), shop.order_id, "shipped")
            except HTTPException as error:
                return error.status_code
        return 200

    return action


def read_rows(test_engine, sql):
    with test_engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql)).mappings().all()]


def read_state(test_engine):
    order = read_rows(test_engine, "SELECT status FROM orders")[0]["status"]
    payment = read_rows(test_engine, "SELECT status FROM payments")[0]["status"]
    stock = read_rows(test_engine, "SELECT stock FROM products")[0]["stock"]
    return order, payment, stock


def test_cancel_against_ship_on_one_paid_order(test_engine, shop, post_webhook, refund_create):
    assert post_webhook(webhook_event(shop)).status_code == 200
    assert read_state(test_engine) == ("paid", "succeeded", 7)

    cancel_status, ship_status = run_together([cancel_action(shop), ship_action(shop)])

    order_status, payment_status, stock = read_state(test_engine)
    if order_status == "cancelled":
        # The cancel won: the ship request was refused, the stock is back once and the refund was made once
        assert (cancel_status, ship_status) == (200, 409)
        assert stock == 10
        assert payment_status == "refunded"
        assert refund_create.call_count == 1
    else:
        # The ship won: the cancel request was refused, the stock is unchanged and nothing was refunded
        assert order_status == "shipped"
        assert (cancel_status, ship_status) == (409, 200)
        assert stock == 7
        assert payment_status == "succeeded"
        assert refund_create.call_count == 0


def test_two_cancels_of_one_paid_order_at_once(test_engine, shop, post_webhook, refund_create):
    assert post_webhook(webhook_event(shop)).status_code == 200

    results = run_together([cancel_action(shop), cancel_action(shop)])

    # Both answer 200, the stock came back exactly once, the payment ends refunded
    assert results == [200, 200]
    assert read_state(test_engine) == ("cancelled", "refunded", 10)
    # Every refund call that happened used the same idempotency key (Stripe refunds only once for it)
    assert refund_create.call_count >= 1
    keys = {call.kwargs["idempotency_key"] for call in refund_create.call_args_list}
    assert keys == {"cancel-refund-" + str(shop.order_id)}


def test_cancel_of_a_pending_order_against_the_completed_webhook(test_engine, shop, post_webhook, refund_create):
    event = webhook_event(shop)
    assert read_state(test_engine) == ("pending_payment", "pending", 7)

    def webhook_action():
        return post_webhook(event).status_code

    results = run_together([cancel_action(shop), webhook_action])

    # Whichever ran first, the order ends cancelled and refunded, the stock is back once and the
    # money was given back exactly once
    assert results == [200, 200]
    assert read_state(test_engine) == ("cancelled", "refunded", 10)
    assert refund_create.call_count == 1
