import logging

import stripe
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.repositories import order_repository, product_repository

# The idempotency key of a refund is this prefix plus the order id, so asking Stripe twice for the same
# order's refund (a retry, two clicks at once) can never refund twice.
REFUND_KEY_PREFIX = "cancel-refund-"

# Log lines never contain a Stripe key or the text of a Stripe error (it can contain part of a key)
logger = logging.getLogger(__name__)


def cancel_order(db: Session, current_user: User, order_id: int):
    # Only customers (their own orders) and admins (any order) may cancel. Sellers get 403.
    if current_user.role not in ("customer", "admin"):
        raise HTTPException(status_code=403, detail="Customer or admin access required")

    # ===== Stage 1: one database transaction =====

    # a. Find the order (a customer only finds their own) and lock its row. The status is read
    #    inside the lock, so two cancels (or a cancel and a "shipped") at the same moment take turns.
    owner_id = None
    if current_user.role == "customer":
        owner_id = current_user.id
    order = order_repository.lock_order(db, order_id, owner_id)
    if order is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Order not found")
    payment = order_repository.get_payment_by_order_id(db, order_id)
    order_items = order.items

    # What stage 2 has to do
    session_id_to_expire = None
    refund_owed = False

    # b. A shipped or delivered order can never be cancelled (there are no returns)
    if order.status == "shipped" or order.status == "delivered":
        db.rollback()
        raise HTTPException(status_code=409, detail="A shipped order can no longer be cancelled.")

    if order.status == "cancelled":
        # c. Already cancelled. If no money is waiting to be given back, a double click is harmless.
        if payment.status != "succeeded":
            db.rollback()
            return {"order_id": order.id, "status": order.status, "payment_status": payment.status}

        # The money was taken but the refund did not finish earlier: this is the "retry refund" path.
        # Refunds only work with a Stripe test key. Nothing is changed.
        if settings.STRIPE_SECRET_KEY == "" or not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
            db.rollback()
            raise HTTPException(status_code=503, detail="Refunds are not available: Stripe is not configured for test mode")
        if payment.stripe_payment_intent_id is None:
            db.rollback()
            logger.error("Cancel: order=%s is cancelled and paid but has no payment intent to refund", order_id)
            raise HTTPException(status_code=409, detail="This order has no payment to refund. Please contact support.")
        refund_owed = True

    elif order.status == "pending_payment":
        # d. Cancel the unpaid order: the payment fails and the reserved stock goes back
        order.status = "cancelled"
        payment.status = "failed"
        order.updated_at = func.now()

        # Give the stock back with one atomic increment per product, in ascending product id order
        # (the same order as checkout and the webhook, so they can never deadlock)
        stock_changes = []
        for order_item in order_items:
            stock_changes.append((order_item.product_id, order_item.quantity))
        stock_changes.sort()
        for product_id, quantity in stock_changes:
            product_repository.increase_stock(db, product_id, quantity)

        # Save it. After this no lock is held. The Stripe session is expired in stage 2.
        db.commit()
        session_id_to_expire = payment.stripe_checkout_session_id
        logger.info("Cancel: order=%s outcome=cancelled (was pending_payment), stock restored", order_id)

    else:
        # e. A paid order: check that the refund can be made BEFORE changing anything
        if settings.STRIPE_SECRET_KEY == "" or not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
            db.rollback()
            raise HTTPException(status_code=503, detail="Refunds are not available: Stripe is not configured for test mode")
        if payment.stripe_payment_intent_id is None:
            db.rollback()
            logger.error("Cancel: order=%s is paid but has no payment intent to refund", order_id)
            raise HTTPException(status_code=409, detail="This order has no payment to refund. Please contact support.")

        # The order is cancelled now. The payment stays "succeeded" until the refund is really done.
        order.status = "cancelled"
        order.updated_at = func.now()

        # Give the stock back (same atomic increments, same order as above)
        stock_changes = []
        for order_item in order_items:
            stock_changes.append((order_item.product_id, order_item.quantity))
        stock_changes.sort()
        for product_id, quantity in stock_changes:
            product_repository.increase_stock(db, product_id, quantity)

        # Save it. The cancellation stays even if the refund below fails.
        db.commit()
        refund_owed = True
        logger.info("Cancel: order=%s outcome=cancelled (was paid), stock restored, refund owed", order_id)

    # ===== Stage 2: after the commit, no transaction open =====

    # f. Expire the Stripe Checkout Session, so the customer cannot pay for a cancelled order.
    #    If this fails we only log it: when the customer still pays, the webhook refunds that
    #    late payment automatically. Only a test key is ever used.
    if session_id_to_expire is not None:
        if settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
            try:
                stripe.default_http_client = stripe.RequestsClient(timeout=10)
                stripe.checkout.Session.expire(session_id_to_expire, api_key=settings.STRIPE_SECRET_KEY)
            except stripe.StripeError as error:
                logger.warning("Cancel: order=%s could not expire the Stripe session (%s)", order_id, type(error).__name__)
        else:
            logger.warning("Cancel: order=%s Stripe session not expired (no Stripe test key)", order_id)

    # g. Give the money back (full refund). The idempotency key makes a repeated call safe.
    if refund_owed:
        refund_id = None
        refund_failed = False
        try:
            stripe.default_http_client = stripe.RequestsClient(timeout=10)
            refund = stripe.Refund.create(
                api_key=settings.STRIPE_SECRET_KEY,
                payment_intent=payment.stripe_payment_intent_id,
                idempotency_key=REFUND_KEY_PREFIX + str(order_id),
            )
            refund_id = refund.id
        except stripe.StripeError as error:
            if error.code == "charge_already_refunded":
                # Stripe says the money is already back: that is what we wanted, so it counts as success
                logger.info("Cancel: order=%s the charge was already refunded", order_id)
            else:
                # Log the kind of error only, never its text and never a key
                refund_failed = True
                logger.error("Cancel: order=%s refund failed (%s, code=%s)", order_id, type(error).__name__, error.code)

        # The order stays cancelled. The customer can press "Retry refund".
        if refund_failed:
            raise HTTPException(
                status_code=502,
                detail="Your order has been cancelled, but the refund could not be completed yet. Open the order and press Retry refund.",
            )

        # A small transaction: the payment is refunded and the refund id is saved
        order_repository.mark_payment_refunded(db, payment.id, refund_id)
        db.commit()
        logger.info("Cancel: order=%s outcome=payment refunded", order_id)
        return {"order_id": order.id, "status": "cancelled", "payment_status": "refunded"}

    # h. A cancelled unpaid order: its payment failed
    return {"order_id": order.id, "status": "cancelled", "payment_status": "failed"}


def update_order_status(db: Session, current_user: User, order_id: int, new_status: str):
    # Only sellers and admins may change the status of an order (the routers also check this)
    if current_user.role not in ("seller", "admin"):
        raise HTTPException(status_code=403, detail="Seller or admin access required")

    # a. Lock the order row and read its status inside the lock, then load the seller of every line
    #    and the payment. A cancel at the same moment waits here, and then sees the new status.
    order = order_repository.lock_order(db, order_id)
    if order is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Order not found")
    item_seller_ids = order_repository.list_item_seller_ids(db, order_id)
    payment = order_repository.get_payment_by_order_id(db, order_id)

    # b. A seller needs permission. Admins skip these checks.
    if current_user.role == "seller":
        # The seller may only know about paid orders that contain one of their products
        seller_item_count = 0
        for item_seller_id in item_seller_ids:
            if item_seller_id == current_user.id:
                seller_item_count = seller_item_count + 1
        payment_is_paid = payment is not None and payment.status in ("succeeded", "refunded")
        if not payment_is_paid or seller_item_count == 0:
            db.rollback()
            raise HTTPException(status_code=404, detail="Order not found")

        # A mixed order has one status for all sellers, so only an admin may change it
        if seller_item_count != len(item_seller_ids):
            db.rollback()
            raise HTTPException(
                status_code=403,
                detail="This order includes products from other sellers. Only an admin can update its status.",
            )

    # c. Already in the requested status: a double click is harmless
    if order.status == new_status:
        db.rollback()
        return {"order_id": order.id, "status": order.status}

    # d. Only paid -> shipped and shipped -> delivered are allowed
    is_allowed = (order.status == "paid" and new_status == "shipped") or (
        order.status == "shipped" and new_status == "delivered"
    )
    if not is_allowed:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Cannot change an order from " + order.status + " to " + new_status + "."
        )

    # e. Save the new status
    order.status = new_status
    order.updated_at = func.now()
    db.commit()
    logger.info("Order status: order=%s outcome=%s", order_id, new_status)
    return {"order_id": order.id, "status": new_status}
