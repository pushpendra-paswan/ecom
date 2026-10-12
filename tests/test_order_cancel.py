import pytest
import stripe

from app.core.config import settings
from tests.conftest import make_event


@pytest.fixture(autouse=True)
def stripe_test_key(monkeypatch):
    # A dummy Stripe test key for every test in this file (the real Stripe API is never called)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_dummy")


@pytest.fixture
def cancel(client):
    # Returns a function that posts the cancel request
    def cancel_order(order_id, headers=None):
        return client.post("/orders/" + str(order_id) + "/cancel", headers=headers)

    return cancel_order


@pytest.fixture
def paid_order(store, pay):
    # A paid order of 2 units of a product with stock 10 (so the stock is 8 until it is cancelled)
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 2)])
    pay(order)
    order.product_id = product_id
    return order


# ---------- who may cancel ----------


def test_cancel_without_a_token_gives_401(client, cancel):
    assert cancel(1).status_code == 401


def test_a_seller_cannot_cancel_an_order(store, create_user, auth_headers, cancel, read_order):
    order = store.place_order([(store.product(), 1)])
    seller_headers = auth_headers("seller@example.com")

    response = cancel(order.id, seller_headers)

    assert response.status_code == 403
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_another_customers_order_gives_404(store, create_user, auth_headers, cancel, read_order):
    order = store.place_order([(store.product(), 1)])
    create_user("other@example.com")

    response = cancel(order.id, auth_headers("other@example.com"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"
    assert read_order(order.id)["order_status"] == "pending_payment"


def test_missing_order_gives_404_and_a_bad_id_gives_422(store, cancel):
    assert cancel(9999, store.customer).status_code == 404
    assert cancel("abc", store.customer).status_code == 422


def test_an_admin_can_cancel_anyones_order(store, create_user, auth_headers, cancel, read_order, read_stock):
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 3)])
    create_user("admin@example.com", role="admin")

    response = cancel(order.id, auth_headers("admin@example.com"))

    assert response.status_code == 200
    assert response.json() == {"order_id": order.id, "status": "cancelled", "payment_status": "failed"}
    assert read_stock(product_id) == 10


# ---------- cancelling an order that is not paid ----------


def test_cancel_a_pending_order_restores_all_stock_and_expires_the_session(
    store, cancel, session_expire, refund_create, read_order, read_stock
):
    first_product = store.product(stock=10)
    second_product = store.product(stock=5)
    order = store.place_order([(first_product, 2), (second_product, 3)])
    assert read_stock(first_product) == 8
    assert read_stock(second_product) == 2

    response = cancel(order.id, store.customer)

    assert response.status_code == 200
    assert response.json() == {"order_id": order.id, "status": "cancelled", "payment_status": "failed"}
    state = read_order(order.id)
    assert state["order_status"] == "cancelled"
    assert state["payment_status"] == "failed"
    assert read_stock(first_product) == 10
    assert read_stock(second_product) == 5
    # The Stripe session was expired once, and no refund was made
    assert session_expire.call_count == 1
    assert session_expire.call_args.args[0] == order.session_id
    assert refund_create.call_count == 0


def test_cancel_still_works_when_expiring_the_session_fails(store, cancel, session_expire, read_order):
    order = store.place_order([(store.product(), 1)])
    session_expire.side_effect = stripe.APIConnectionError("network down")

    response = cancel(order.id, store.customer)

    assert response.status_code == 200
    assert read_order(order.id)["order_status"] == "cancelled"


def test_an_order_without_a_session_id_makes_no_expire_call(store, cancel, change_database, session_expire, read_order):
    order = store.place_order([(store.product(), 1)])
    change_database("UPDATE payments SET stripe_checkout_session_id = NULL WHERE order_id = :id", id=order.id)

    response = cancel(order.id, store.customer)

    assert response.status_code == 200
    assert read_order(order.id)["order_status"] == "cancelled"
    assert session_expire.call_count == 0


def test_cancelling_a_cancelled_unpaid_order_changes_nothing(
    store, cancel, session_expire, read_order, read_stock
):
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 2)])
    assert cancel(order.id, store.customer).status_code == 200
    state_after_first = read_order(order.id)

    second = cancel(order.id, store.customer)

    assert second.status_code == 200
    assert second.json() == {"order_id": order.id, "status": "cancelled", "payment_status": "failed"}
    assert read_order(order.id) == state_after_first
    assert read_stock(product_id) == 10
    assert session_expire.call_count == 1


def test_expired_event_after_a_cancel_changes_nothing(store, cancel, post_webhook, read_stock, read_order):
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 2)])
    assert cancel(order.id, store.customer).status_code == 200
    state_after_cancel = read_order(order.id)

    expired = make_event("checkout.session.expired", order.session_id, order, payment_status="unpaid")
    response = post_webhook(expired)

    # The stock was given back by the cancel, and is not given back a second time
    assert response.status_code == 200
    assert read_stock(product_id) == 10
    assert read_order(order.id) == state_after_cancel


def test_completed_event_after_a_cancel_is_refunded_and_the_order_stays_cancelled(
    store, cancel, post_webhook, refund_create, read_stock, read_order
):
    product_id = store.product(stock=10)
    order = store.place_order([(product_id, 2)])
    assert cancel(order.id, store.customer).status_code == 200

    # The customer still managed to pay: the late payment is refunded
    completed = make_event("checkout.session.completed", order.session_id, order, payment_intent="pi_test_late")
    response = post_webhook(completed)

    assert response.status_code == 200
    state = read_order(order.id)
    assert state["order_status"] == "cancelled"
    assert state["payment_status"] == "refunded"
    assert refund_create.call_count == 1
    assert refund_create.call_args.kwargs["payment_intent"] == "pi_test_late"
    assert read_stock(product_id) == 10


# ---------- cancelling a paid order ----------


def test_cancel_a_paid_order_refunds_it(client, store, paid_order, cancel, refund_create, read_order, read_stock):
    response = cancel(paid_order.id, store.customer)

    assert response.status_code == 200
    assert response.json() == {"order_id": paid_order.id, "status": "cancelled", "payment_status": "refunded"}
    state = read_order(paid_order.id)
    assert state["order_status"] == "cancelled"
    assert state["payment_status"] == "refunded"
    assert state["refund_id"] == "re_test_1"
    assert read_stock(paid_order.product_id) == 10
    # One refund, for the right payment, with the idempotency key
    assert refund_create.call_count == 1
    assert refund_create.call_args.kwargs["payment_intent"] == "pi_test_" + str(paid_order.id)
    assert refund_create.call_args.kwargs["idempotency_key"] == "cancel-refund-" + str(paid_order.id)

    # The customer sees the refunded payment
    detail = client.get("/orders/" + str(paid_order.id), headers=store.customer)
    assert detail.json()["status"] == "cancelled"
    assert detail.json()["payment"]["status"] == "refunded"


def test_a_second_cancel_changes_nothing_and_refunds_nothing(
    store, paid_order, cancel, refund_create, read_order, read_stock
):
    assert cancel(paid_order.id, store.customer).status_code == 200
    state_after_first = read_order(paid_order.id)

    second = cancel(paid_order.id, store.customer)

    assert second.status_code == 200
    assert second.json() == {"order_id": paid_order.id, "status": "cancelled", "payment_status": "refunded"}
    assert read_order(paid_order.id) == state_after_first
    assert refund_create.call_count == 1
    assert read_stock(paid_order.product_id) == 10


def test_a_failed_refund_gives_502_and_retry_refund_works(
    store, paid_order, cancel, refund_create, read_order, read_stock
):
    refund_create.side_effect = stripe.APIConnectionError("secret network text sk_test_abc")

    response = cancel(paid_order.id, store.customer)

    # 502 with a generic message (none of the Stripe error text). The cancellation is kept.
    assert response.status_code == 502
    assert "Retry refund" in response.json()["detail"]
    assert "secret" not in response.text
    state = read_order(paid_order.id)
    assert state["order_status"] == "cancelled"
    assert state["payment_status"] == "succeeded"
    assert read_stock(paid_order.product_id) == 10

    # Cancel again, now the refund works: the payment is refunded and the stock is NOT restored again
    refund_create.side_effect = None
    retry = cancel(paid_order.id, store.customer)
    assert retry.status_code == 200
    assert retry.json()["payment_status"] == "refunded"
    state = read_order(paid_order.id)
    assert state["payment_status"] == "refunded"
    assert state["refund_id"] == "re_test_1"
    assert read_stock(paid_order.product_id) == 10
    assert refund_create.call_count == 2
    assert refund_create.call_args.kwargs["idempotency_key"] == "cancel-refund-" + str(paid_order.id)


def test_charge_already_refunded_counts_as_success(store, paid_order, cancel, refund_create, read_order):
    refund_create.side_effect = stripe.InvalidRequestError("already refunded", "charge", code="charge_already_refunded")

    response = cancel(paid_order.id, store.customer)

    assert response.status_code == 200
    assert response.json()["payment_status"] == "refunded"
    state = read_order(paid_order.id)
    assert state["payment_status"] == "refunded"
    assert state["refund_id"] is None


# ---------- orders that cannot be cancelled ----------


@pytest.mark.parametrize("status", ["shipped", "delivered"])
def test_shipped_and_delivered_orders_cannot_be_cancelled(
    status, store, paid_order, cancel, change_database, session_expire, refund_create, read_order, read_stock
):
    change_database("UPDATE orders SET status = :status WHERE id = :id", status=status, id=paid_order.id)
    state_before = read_order(paid_order.id)

    response = cancel(paid_order.id, store.customer)

    assert response.status_code == 409
    assert response.json()["detail"] == "A shipped order can no longer be cancelled."
    assert read_order(paid_order.id) == state_before
    assert read_stock(paid_order.product_id) == 8
    assert session_expire.call_count == 0
    assert refund_create.call_count == 0


@pytest.mark.parametrize("key", ["", "sk_live_dummy"])
def test_paid_cancel_needs_a_stripe_test_key(
    key, store, paid_order, cancel, monkeypatch, refund_create, read_order, read_stock
):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", key)
    state_before = read_order(paid_order.id)

    response = cancel(paid_order.id, store.customer)

    # 503 and nothing changes (no cancellation, no stock, no Stripe call)
    assert response.status_code == 503
    assert read_order(paid_order.id) == state_before
    assert read_order(paid_order.id)["order_status"] == "paid"
    assert read_stock(paid_order.product_id) == 8
    assert refund_create.call_count == 0


def test_retry_refund_needs_a_stripe_test_key_too(
    store, paid_order, cancel, monkeypatch, refund_create, read_order
):
    refund_create.side_effect = stripe.APIConnectionError("network down")
    assert cancel(paid_order.id, store.customer).status_code == 502
    refund_create.side_effect = None
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_dummy")

    response = cancel(paid_order.id, store.customer)

    assert response.status_code == 503
    assert read_order(paid_order.id)["payment_status"] == "succeeded"
    assert refund_create.call_count == 1


def test_a_paid_order_without_a_payment_intent_gives_409(
    store, paid_order, cancel, change_database, refund_create, read_order, read_stock
):
    change_database("UPDATE payments SET stripe_payment_intent_id = NULL WHERE order_id = :id", id=paid_order.id)

    response = cancel(paid_order.id, store.customer)

    assert response.status_code == 409
    assert response.json()["detail"] == "This order has no payment to refund. Please contact support."
    assert read_order(paid_order.id)["order_status"] == "paid"
    assert read_stock(paid_order.product_id) == 8
    assert refund_create.call_count == 0
