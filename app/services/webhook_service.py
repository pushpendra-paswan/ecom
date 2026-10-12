import logging

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import order_repository, product_repository

# Log lines contain only the event id, the event type, the order id and the outcome.
# Never the request body, the signature header or any secret.
logger = logging.getLogger(__name__)


def handle_stripe_event(db: Session, payload: bytes, signature_header: str | None):
    # a. Without a signing secret nothing can be verified, so nothing is processed
    if settings.STRIPE_WEBHOOK_SECRET == "":
        raise HTTPException(status_code=503, detail="Webhooks are not configured")

    # b. Verify the signature on the exact raw bytes (default tolerance: 5 minutes).
    #    A missing header, a wrong signature, an old timestamp or a body that is not valid JSON all give 400.
    #    The message is generic on purpose.
    try:
        event = stripe.Webhook.construct_event(payload, signature_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        logger.warning("Stripe webhook rejected: invalid signature or body")
        raise HTTPException(status_code=400, detail="Invalid webhook request")

    # The event is trusted from here on. Turn it into plain dictionaries.
    event_data = event.to_dict()
    event_id = event_data.get("id")
    event_type = event_data.get("type")

    # c. Every event type we do not handle is acknowledged and ignored
    if event_type != "checkout.session.completed" and event_type != "checkout.session.expired":
        logger.info("Stripe webhook: event=%s type=%s outcome=ignored (event type not handled)", event_id, event_type)
        return {"received": True}

    # d. Read the Checkout Session out of the event
    session = event_data.get("data", {}).get("object", {})
    session_id = session.get("id")
    payment_status = session.get("payment_status")
    amount_total = session.get("amount_total")
    currency = session.get("currency")
    payment_intent_id = session.get("payment_intent")
    metadata = session.get("metadata") or {}
    if not isinstance(session_id, str) or session_id == "":
        logger.warning("Stripe webhook: event=%s type=%s outcome=ignored (no session id)", event_id, event_type)
        return {"received": True}

    # Everything below runs in one database transaction. Any unexpected error rolls it back,
    # and the error becomes a 500, so Stripe delivers the event again later.
    order_id = None
    try:
        # e. Find the payment, first by the Stripe session id
        payment = order_repository.get_payment_by_session_id(db, session_id)
        found_by_order_id = False

        # Fallback: the order id from the metadata. It matters because checkout stage 2 can fail
        # after the Stripe session exists, which leaves the payment without a session id.
        if payment is None:
            order_id_text = metadata.get("order_id")
            is_whole_number = (
                isinstance(order_id_text, str)
                and order_id_text.isascii()
                and order_id_text.isdigit()
                and len(order_id_text) <= 10
                and int(order_id_text) <= 2147483647
            )
            if not is_whole_number:
                logger.warning(
                    "Stripe webhook: event=%s type=%s outcome=ignored (unknown session, no usable order id)",
                    event_id,
                    event_type,
                )
                return {"received": True}
            payment = order_repository.get_payment_by_order_id(db, int(order_id_text))
            found_by_order_id = True

        # No payment at all: not our problem to retry
        if payment is None:
            logger.warning("Stripe webhook: event=%s type=%s outcome=ignored (unknown order)", event_id, event_type)
            return {"received": True}
        order_id = payment.order_id

        # A payment that already belongs to a different Stripe session is not this event's payment
        if (
            found_by_order_id
            and payment.stripe_checkout_session_id is not None
            and payment.stripe_checkout_session_id != session_id
        ):
            logger.warning(
                "Stripe webhook: event=%s type=%s order=%s outcome=ignored (order has a different session)",
                event_id,
                event_type,
                order_id,
            )
            return {"received": True}

        # f. Lock the order row and read its status inside the lock. A second delivery of the same
        #    event waits here, and then sees the status that the first one left behind.
        order = order_repository.lock_order(db, order_id)
        if order is None:
            db.rollback()
            logger.warning("Stripe webhook: event=%s type=%s order=%s outcome=ignored (order missing)", event_id, event_type, order_id)
            return {"received": True}

        # The order was found by its id: remember the session id on the payment (saved by the commit below)
        if found_by_order_id and payment.stripe_checkout_session_id is None:
            payment.stripe_checkout_session_id = session_id

        if event_type == "checkout.session.completed":
            # g. The customer paid. Ignore it if Stripe does not say "paid".
            if payment_status != "paid":
                db.rollback()
                logger.info(
                    "Stripe webhook: event=%s type=%s order=%s outcome=ignored (payment_status is not paid)",
                    event_id,
                    event_type,
                    order_id,
                )
                return {"received": True}

            # The amount and currency Stripe charged must match what we stored. A mismatch is a bug
            # to investigate, not something Stripe should retry, so answer 200 and change nothing.
            if amount_total != payment.amount or str(currency).lower() != payment.currency.lower():
                db.rollback()
                logger.error(
                    "Stripe webhook: event=%s type=%s order=%s outcome=ignored (amount or currency mismatch)",
                    event_id,
                    event_type,
                    order_id,
                )
                return {"received": True}

            if order.status == "pending_payment":
                # The normal case: the order is paid
                order.status = "paid"
                payment.status = "succeeded"
                payment.stripe_payment_intent_id = payment_intent_id
                db.commit()
                logger.info("Stripe webhook: event=%s type=%s order=%s outcome=order paid", event_id, event_type, order_id)
                return {"received": True}

            if order.status == "cancelled":
                # A late payment for an order we already cancelled. If the money was already given back
                # (by an earlier delivery of this event, or by the customer's cancel), there is nothing to do.
                if payment.status == "refunded":
                    db.rollback()
                    logger.info(
                        "Stripe webhook: event=%s type=%s order=%s outcome=no change (payment already refunded)",
                        event_id,
                        event_type,
                        order_id,
                    )
                    return {"received": True}

                # Do NOT bring the order back. Save the payment intent, then give the money back.
                if not isinstance(payment_intent_id, str) or payment_intent_id == "":
                    db.rollback()
                    logger.error(
                        "Stripe webhook: event=%s type=%s order=%s outcome=ignored (late payment without payment intent)",
                        event_id,
                        event_type,
                        order_id,
                    )
                    return {"received": True}
                payment.stripe_payment_intent_id = payment_intent_id
                db.commit()
                logger.warning(
                    "Stripe webhook: event=%s type=%s order=%s outcome=late payment for a cancelled order, refunding",
                    event_id,
                    event_type,
                    order_id,
                )

                # The refund is a network call, so it happens after the commit (no lock is held).
                # The idempotency key makes a repeated refund safe. If it fails we answer 500, and
                # Stripe delivers the event again, which reaches this same code and tries again.
                # The stock stays as it is: it was already given back when the order was cancelled.
                refund_id = None
                try:
                    refund = stripe.Refund.create(
                        api_key=settings.STRIPE_SECRET_KEY,
                        payment_intent=payment_intent_id,
                        idempotency_key="late-payment-refund-" + str(order_id),
                    )
                    refund_id = refund.id
                except stripe.StripeError as error:
                    if error.code != "charge_already_refunded":
                        logger.error(
                            "Stripe webhook: event=%s type=%s order=%s outcome=late payment refund failed",
                            event_id,
                            event_type,
                            order_id,
                        )
                        raise HTTPException(status_code=500, detail="Refund failed, please retry")
                    # Stripe says the money is already back (for example the customer's cancel refunded it): success

                # A small transaction: the payment is refunded and the refund id is saved
                order_repository.mark_payment_refunded(db, payment.id, refund_id)
                db.commit()
                return {"received": True}

            # Already paid (a duplicate delivery), shipped or delivered: nothing to change
            db.rollback()
            logger.info(
                "Stripe webhook: event=%s type=%s order=%s outcome=no change (order is %s)",
                event_id,
                event_type,
                order_id,
                order.status,
            )
            return {"received": True}

        else:
            # h. The checkout session expired without payment
            if order.status != "pending_payment":
                db.rollback()
                logger.info(
                    "Stripe webhook: event=%s type=%s order=%s outcome=no change (order is %s)",
                    event_id,
                    event_type,
                    order_id,
                    order.status,
                )
                return {"received": True}

            # Cancel the order and fail the payment
            order.status = "cancelled"
            payment.status = "failed"

            # Give the stock back with one atomic increment per product, in ascending product id
            # order (checkout locks products in the same order, so the two can never deadlock)
            stock_changes = []
            for order_item in order.items:
                stock_changes.append((order_item.product_id, order_item.quantity))
            stock_changes.sort()
            for product_id, quantity in stock_changes:
                product_repository.increase_stock(db, product_id, quantity)

            db.commit()
            logger.info("Stripe webhook: event=%s type=%s order=%s outcome=order cancelled, stock restored", event_id, event_type, order_id)
            return {"received": True}

    except Exception:
        # i. Undo everything and let the error become a 500
        db.rollback()
        logger.error("Stripe webhook: event=%s type=%s order=%s outcome=error", event_id, event_type, order_id)
        raise
