import logging
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import User
from app.services import checkout_service


def make_event(event_type, session_id, order_id, total_amount, payment_status):
    # A minimal Stripe event for one checkout session
    return {
        "id": "evt_concurrent_1",
        "object": "event",
        "type": event_type,
        "data": {
            "object": {
                "id": session_id,
                "payment_status": payment_status,
                "amount_total": total_amount,
                "currency": "inr",
                "payment_intent": "pi_test_concurrent",
                "metadata": {"order_id": str(order_id)},
            }
        },
    }


@pytest.fixture
def pending_order(test_engine, committed_data, monkeypatch):
    # One committed pending order (made by the real checkout service) of 3 units of a product with stock 10
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_dummy")
    (product_id,) = committed_data.products(count=1, stock=10)
    user_id, address_id = committed_data.customer("buyer@example.com")
    committed_data.put_in_cart(user_id, product_id, 3)

    session_factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.side_effect = lambda **kwargs: SimpleNamespace(
            id="cs_test_" + kwargs["idempotency_key"], url="https://checkout.stripe.com/c/pay/fake"
        )
        with session_factory() as db:
            user = db.get(User, user_id)
            body = checkout_service.checkout(db, user, address_id)

    return SimpleNamespace(
        id=body["order_id"],
        total_amount=body["total_amount"],
        session_id="cs_test_order-" + str(body["order_id"]),
        product_id=product_id,
    )


def deliver_twice_at_once(post_webhook, event):
    # Two threads post the same event at the same moment (a barrier lines them up)
    barrier = threading.Barrier(2)
    responses = [None, None]

    def deliver(position):
        barrier.wait(timeout=10)
        responses[position] = post_webhook(event)

    threads = [threading.Thread(target=deliver, args=(position,)) for position in range(2)]
    for thread in threads:
        thread.start()

    # A deadlock would leave a thread running: wait at most 15 seconds and fail if one is still alive
    for thread in threads:
        thread.join(timeout=15)
    for thread in threads:
        assert not thread.is_alive(), "a webhook thread is still running (deadlock?)"

    return responses


def read_rows(test_engine, sql):
    with test_engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql)).mappings().all()]


def test_completed_event_delivered_twice_at_once_pays_the_order_once(
    test_engine, post_webhook, pending_order, caplog
):
    event = make_event("checkout.session.completed", pending_order.session_id, pending_order.id, pending_order.total_amount, "paid")
    caplog.set_level(logging.INFO)

    responses = deliver_twice_at_once(post_webhook, event)

    # Both deliveries answer 200, and the order was changed by exactly one of them
    assert [response.status_code for response in responses] == [200, 200]
    assert caplog.text.count("outcome=order paid") == 1
    order = read_rows(test_engine, "SELECT status FROM orders")[0]
    payment = read_rows(test_engine, "SELECT status, stripe_payment_intent_id FROM payments")[0]
    assert order["status"] == "paid"
    assert payment["status"] == "succeeded"
    assert payment["stripe_payment_intent_id"] == "pi_test_concurrent"


def test_expired_event_delivered_twice_at_once_gives_stock_back_once(
    test_engine, post_webhook, pending_order, caplog
):
    event = make_event("checkout.session.expired", pending_order.session_id, pending_order.id, pending_order.total_amount, "unpaid")
    assert read_rows(test_engine, "SELECT stock FROM products")[0]["stock"] == 7
    caplog.set_level(logging.INFO)

    responses = deliver_twice_at_once(post_webhook, event)

    # Both deliveries answer 200, the stock came back exactly once (7 + 3 = 10, not 13)
    assert [response.status_code for response in responses] == [200, 200]
    assert caplog.text.count("outcome=order cancelled, stock restored") == 1
    assert read_rows(test_engine, "SELECT stock FROM products")[0]["stock"] == 10
    assert read_rows(test_engine, "SELECT status FROM orders")[0]["status"] == "cancelled"
    assert read_rows(test_engine, "SELECT status FROM payments")[0]["status"] == "failed"
