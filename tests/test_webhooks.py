import json
import logging
import time

import pytest
import stripe

from app.core.config import settings
from tests.conftest import make_event


@pytest.fixture
def pending_order(store):
    # One pending order of one product, and the event that would mark it paid
    product_id = store.product()
    order = store.place_order([(product_id, 2)])
    event = make_event("checkout.session.completed", order.session_id, order)
    return order, event


# ---------- signature ----------


def test_missing_signature_header_is_rejected(client, post_webhook, pending_order, read_order):
    order, event = pending_order

    response = client.post("/webhooks/stripe", content=json.dumps(event).encode())

    assert response.status_code == 400
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_wrong_signature_is_rejected(post_webhook, pending_order, read_order):
    order, event = pending_order

    response = post_webhook(event, secret="whsec_somebody_else")

    assert response.status_code == 400
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_tampered_body_is_rejected(post_webhook, pending_order, read_order):
    order, event = pending_order

    # The signature is valid for a different body than the one that is sent
    other_event = dict(event, id="evt_other")
    response = post_webhook(event, signed_body=json.dumps(other_event).encode())

    assert response.status_code == 400
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_old_timestamp_is_rejected(post_webhook, pending_order, read_order):
    order, event = pending_order

    # Correctly signed, but 10 minutes old
    response = post_webhook(event, timestamp=int(time.time()) - 600)

    assert response.status_code == 400
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_signed_body_that_is_not_json_is_rejected(post_webhook, pending_order, read_order):
    order, event = pending_order

    response = post_webhook(b"this is not json")

    assert response.status_code == 400
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_empty_webhook_secret_gives_503(post_webhook, monkeypatch, pending_order, read_order):
    order, event = pending_order
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    response = post_webhook(event)

    assert response.status_code == 503
    assert response.json()["detail"] == "Webhooks are not configured"
    assert read_order(order.id)["order_status"] == "pending_payment"


# ---------- checkout.session.completed ----------


def test_completed_and_paid_marks_the_order_paid(client, post_webhook, store, read_order, read_stock):
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 2)])
    event = make_event("checkout.session.completed", order.session_id, order, payment_intent="pi_test_paid")

    # No login token is sent
    response = post_webhook(event)

    assert response.status_code == 200
    assert response.json() == {"received": True}
    state = read_order(order.id)
    assert state["order_status"] == "paid"
    assert state["payment_status"] == "succeeded"
    assert state["payment_intent"] == "pi_test_paid"
    # The stock was reserved at checkout and stays as it is
    assert read_stock(product_id) == 8

    # The customer sees it through the API
    detail = client.get("/orders/" + str(order.id), headers=store.customer).json()
    assert detail["status"] == "paid"
    assert detail["payment"]["status"] == "succeeded"


def test_same_completed_event_twice_changes_nothing_the_second_time(post_webhook, pending_order, read_order):
    order, event = pending_order

    first = post_webhook(event)
    state_after_first = read_order(order.id)
    second = post_webhook(event)

    assert first.status_code == 200
    assert second.status_code == 200
    assert read_order(order.id) == state_after_first


def test_completed_but_unpaid_changes_nothing(post_webhook, store, pending_order, read_order):
    order, _ = pending_order
    event = make_event("checkout.session.completed", order.session_id, order, payment_status="unpaid")

    response = post_webhook(event)

    assert response.status_code == 200
    state = read_order(order.id)
    assert state["order_status"] == "pending_payment"
    assert state["payment_status"] == "pending"
    assert state["payment_intent"] is None


def test_completed_with_wrong_amount_changes_nothing(post_webhook, pending_order, read_order):
    order, _ = pending_order
    event = make_event("checkout.session.completed", order.session_id, order, amount_total=order.total_amount + 1)

    response = post_webhook(event)

    assert response.status_code == 200
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_completed_with_wrong_currency_changes_nothing(post_webhook, pending_order, read_order):
    order, _ = pending_order
    event = make_event("checkout.session.completed", order.session_id, order, currency="usd")

    response = post_webhook(event)

    assert response.status_code == 200
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_completed_for_a_shipped_order_changes_nothing(post_webhook, pending_order, change_database, read_order):
    order, event = pending_order
    change_database("UPDATE orders SET status = 'shipped' WHERE id = :id", id=order.id)
    state_before = read_order(order.id)

    response = post_webhook(event)

    assert response.status_code == 200
    assert read_order(order.id) == state_before


# ---------- checkout.session.expired ----------


def test_expired_cancels_the_order_and_gives_all_stock_back(post_webhook, store, read_order, read_stock):
    first_product = store.product(stock=10)
    second_product = store.product(stock=5)
    order = store.place_order([(first_product, 2), (second_product, 3)])
    assert read_stock(first_product) == 8
    assert read_stock(second_product) == 2
    event = make_event("checkout.session.expired", order.session_id, order, payment_status="unpaid")

    response = post_webhook(event)

    assert response.status_code == 200
    state = read_order(order.id)
    assert state["order_status"] == "cancelled"
    assert state["payment_status"] == "failed"
    # Both products are back to what they were before checkout
    assert read_stock(first_product) == 10
    assert read_stock(second_product) == 5


def test_same_expired_event_twice_gives_stock_back_once(post_webhook, store, read_stock):
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 4)])
    event = make_event("checkout.session.expired", order.session_id, order, payment_status="unpaid")

    first = post_webhook(event)
    second = post_webhook(event)

    assert first.status_code == 200
    assert second.status_code == 200
    assert read_stock(product_id) == 10


def test_expired_for_a_paid_order_changes_nothing(post_webhook, store, read_order, read_stock):
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 2)])
    post_webhook(make_event("checkout.session.completed", order.session_id, order))
    state_before = read_order(order.id)

    response = post_webhook(
        make_event("checkout.session.expired", order.session_id, order, payment_status="unpaid", event_id="evt_2")
    )

    assert response.status_code == 200
    assert read_order(order.id) == state_before
    assert read_stock(product_id) == 8


# ---------- late payment ----------


def late_payment_setup(store, post_webhook):
    # An order that expired (cancelled, stock back), and the "completed" event that arrives afterwards
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 2)])
    expired = make_event("checkout.session.expired", order.session_id, order, payment_status="unpaid")
    assert post_webhook(expired).status_code == 200
    late_event = make_event(
        "checkout.session.completed", order.session_id, order, payment_intent="pi_test_late", event_id="evt_late"
    )
    return product_id, order, late_event


def test_late_payment_refunds_and_keeps_the_order_cancelled(
    post_webhook, store, refund_create, read_order, read_stock
):
    product_id, order, late_event = late_payment_setup(store, post_webhook)
    assert read_order(order.id)["payment_intent"] is None

    response = post_webhook(late_event)

    assert response.status_code == 200
    state = read_order(order.id)
    assert state["order_status"] == "cancelled"
    assert state["payment_intent"] == "pi_test_late"
    # The payment is refunded and the refund id is saved
    assert state["payment_status"] == "refunded"
    assert state["refund_id"] == "re_test_1"
    # One refund, for this payment intent, with the idempotency key
    assert refund_create.call_count == 1
    assert refund_create.call_args.kwargs["payment_intent"] == "pi_test_late"
    assert refund_create.call_args.kwargs["idempotency_key"] == "late-payment-refund-" + str(order.id)
    # The stock was already given back when the order was cancelled, and is not touched again
    assert read_stock(product_id) == 10

    # A second delivery of the same event changes nothing and makes no second refund call
    state_after_first = read_order(order.id)
    second = post_webhook(late_event)
    assert second.status_code == 200
    assert read_order(order.id) == state_after_first
    assert refund_create.call_count == 1
    assert read_stock(product_id) == 10


def test_failed_refund_gives_500_and_the_retry_refunds_again(post_webhook, store, refund_create, read_order):
    product_id, order, late_event = late_payment_setup(store, post_webhook)
    refund_create.side_effect = stripe.APIConnectionError("network down")

    response = post_webhook(late_event)

    # 500 makes Stripe deliver the event again. The order is still cancelled.
    assert response.status_code == 500
    assert read_order(order.id)["order_status"] == "cancelled"
    assert refund_create.call_count == 1
    # The refund did not work, so the payment is not marked refunded
    assert read_order(order.id)["payment_status"] == "failed"

    # The retry reaches the same code and calls the refund again, this time it works
    refund_create.side_effect = None
    retry = post_webhook(late_event)
    assert retry.status_code == 200
    assert refund_create.call_count == 2
    assert refund_create.call_args.kwargs["idempotency_key"] == "late-payment-refund-" + str(order.id)
    assert read_order(order.id)["order_status"] == "cancelled"
    assert read_order(order.id)["payment_status"] == "refunded"


# ---------- finding the payment ----------


def test_fallback_finds_the_payment_by_order_id_and_saves_the_session_id(
    post_webhook, pending_order, change_database, read_order
):
    # Checkout stage 2 failed after Stripe created the session: the payment has no session id
    order, _ = pending_order
    change_database("UPDATE payments SET stripe_checkout_session_id = NULL WHERE order_id = :id", id=order.id)
    event = make_event("checkout.session.completed", "cs_test_created_by_stripe", order)

    response = post_webhook(event)

    assert response.status_code == 200
    state = read_order(order.id)
    assert state["order_status"] == "paid"
    assert state["session_id"] == "cs_test_created_by_stripe"


def test_fallback_ignores_an_order_that_has_a_different_session(post_webhook, pending_order, read_order):
    order, _ = pending_order
    event = make_event("checkout.session.completed", "cs_test_some_other_session", order)

    response = post_webhook(event)

    assert response.status_code == 200
    state = read_order(order.id)
    assert state["order_status"] == "pending_payment"
    assert state["session_id"] == order.session_id


def test_unknown_session_without_metadata_changes_nothing(post_webhook, pending_order, read_order):
    order, _ = pending_order
    event = make_event("checkout.session.completed", "cs_test_unknown", order, metadata={})

    response = post_webhook(event)

    assert response.status_code == 200
    assert read_order(order.id)["order_status"] == "pending_payment"


@pytest.mark.parametrize("bad_order_id", ["abc", "1.5", "-1", " 1", "", "99999999999999999999"])
def test_bad_metadata_order_id_gives_200(post_webhook, pending_order, read_order, bad_order_id):
    order, _ = pending_order
    event = make_event(
        "checkout.session.completed", "cs_test_unknown", order, metadata={"order_id": bad_order_id}
    )

    response = post_webhook(event)

    assert response.status_code == 200
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_unknown_order_id_in_metadata_gives_200(post_webhook, pending_order, read_order):
    order, _ = pending_order
    event = make_event(
        "checkout.session.completed", "cs_test_unknown", order, metadata={"order_id": str(order.id + 1000)}
    )

    response = post_webhook(event)

    assert response.status_code == 200
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_unhandled_event_type_is_ignored(post_webhook, pending_order, read_order):
    order, _ = pending_order
    event = make_event("payment_intent.created", order.session_id, order)

    response = post_webhook(event)

    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert read_order(order.id)["order_status"] == "pending_payment"


# ---------- logging ----------


def test_nothing_sensitive_is_logged(post_webhook, pending_order, caplog):
    order, event = pending_order
    # A value that only appears inside the request body
    event["data"]["object"]["customer_email"] = "body-marker-xyz@example.com"
    caplog.set_level(logging.DEBUG)

    good = post_webhook(event)
    expired = post_webhook(
        make_event("checkout.session.expired", order.session_id, order, event_id="evt_log_2")
    )
    bad = post_webhook(event, secret="whsec_somebody_else")

    assert good.status_code == 200
    assert expired.status_code == 200
    assert bad.status_code == 400
    # Events are logged by id, but never the body, the signature header or the secrets
    assert "evt_test_1" in caplog.text
    assert "body-marker-xyz@example.com" not in caplog.text
    assert "whsec_" not in caplog.text
    for response in (good, expired, bad):
        signature_header = response.request.headers["Stripe-Signature"]
        assert signature_header not in caplog.text
        assert signature_header.split("v1=")[1] not in caplog.text
    assert "sk_test_dummy" not in caplog.text


def test_late_payment_for_an_already_refunded_charge_counts_as_refunded(post_webhook, store, refund_create, read_order):
    product_id, order, late_event = late_payment_setup(store, post_webhook)
    refund_create.side_effect = stripe.InvalidRequestError("already refunded", "charge", code="charge_already_refunded")

    response = post_webhook(late_event)

    # Stripe says the money is already back: success, the payment is refunded (no refund id to save)
    assert response.status_code == 200
    state = read_order(order.id)
    assert state["order_status"] == "cancelled"
    assert state["payment_status"] == "refunded"
    assert state["refund_id"] is None
