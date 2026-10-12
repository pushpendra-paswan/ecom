import time

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.repositories import address_repository, cart_repository, order_repository, product_repository

# How long the Stripe Checkout page stays open before the session expires
CHECKOUT_SESSION_MINUTES = 30

# The biggest order total in paise. Stripe accepts at most eight digits in the smallest currency unit.
MAX_ORDER_TOTAL = 99_999_999


def checkout(db: Session, current_user: User, address_id: int):
    # Before any database work: payments must be configured, and only with a Stripe TEST key
    if settings.STRIPE_SECRET_KEY == "":
        raise HTTPException(status_code=503, detail="Payments are not configured")
    if not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        raise HTTPException(status_code=503, detail="Only Stripe test keys are allowed")

    # ===== Stage 1: one database transaction (it ends at the commit in step l) =====

    # a. Load the address, only if it belongs to the logged-in user
    address = address_repository.get_address(db, current_user.id, address_id)
    if address is None:
        raise HTTPException(status_code=404, detail="Address not found")

    # b. Lock the user's cart row. A second checkout of the same user (double click, two tabs)
    #    waits here, and finds an empty cart when the first one is done.
    cart_id = cart_repository.lock_cart(db, current_user.id)
    if cart_id is None:
        db.rollback()
        raise HTTPException(status_code=400, detail="Your cart is empty")

    # c. Load the cart items
    cart_items = cart_repository.list_cart_items(db, current_user.id)
    if len(cart_items) == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="Your cart is empty")

    # d. Lock the product rows of those items with ONE query, in ascending id order,
    #    so two checkouts with overlapping products can never deadlock
    product_ids = []
    for cart_item in cart_items:
        product_ids.append(cart_item.product_id)
    locked_products = product_repository.lock_products(db, product_ids)
    products_by_id = {}
    for locked_product in locked_products:
        products_by_id[locked_product.id] = locked_product

    # e. Check every line against the locked rows and collect the problems of ALL bad lines
    problems = []
    for cart_item in cart_items:
        product = products_by_id[cart_item.product_id]
        if not product.is_active:
            problems.append(product.name + ": no longer available")
        elif product.stock == 0:
            problems.append(product.name + ": out of stock")
        elif product.stock < cart_item.quantity:
            problems.append(product.name + ": only " + str(product.stock) + " left")
    if len(problems) > 0:
        # Nothing was changed. Roll back to release the locks.
        db.rollback()
        raise HTTPException(status_code=409, detail="; ".join(problems))

    # f. Work out each line from the locked product row, and the total of the order
    lines = []
    total_amount = 0
    for cart_item in cart_items:
        product = products_by_id[cart_item.product_id]
        lines.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "unit_price": product.price,
                "quantity": cart_item.quantity,
            }
        )
        total_amount = total_amount + product.price * cart_item.quantity

    # f2. A total that is too big for Stripe is refused. Nothing was written yet, so just let go of the locks.
    if total_amount > MAX_ORDER_TOTAL:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Order total is too large (maximum ₹9,99,999.99 per order). Remove some items and try again.",
        )

    # g. Create the order, with a copy of the shipping address
    order = order_repository.create_order(
        db,
        {
            "user_id": current_user.id,
            "status": "pending_payment",
            "total_amount": total_amount,
            "shipping_full_name": address.full_name,
            "shipping_phone": address.phone,
            "shipping_line1": address.line1,
            "shipping_line2": address.line2,
            "shipping_city": address.city,
            "shipping_state": address.state,
            "shipping_postal_code": address.postal_code,
            "shipping_country": address.country,
        },
    )

    # h. Create the order items (the name and price are snapshots)
    order_items = order_repository.create_order_items(db, order.id, lines)

    # i. Take the quantities out of the stock (this reserves them for the buyer)
    for cart_item in cart_items:
        product = products_by_id[cart_item.product_id]
        product.stock = product.stock - cart_item.quantity

    # j. Create the payment row, still pending
    payment = order_repository.create_payment(
        db,
        {
            "order_id": order.id,
            "amount": total_amount,
            "currency": settings.STRIPE_CURRENCY,
            "status": "pending",
        },
    )

    # k. Empty the cart (the cart row stays)
    cart_repository.delete_all_cart_items(db, current_user.id)

    # l. Save everything at once. After this no database lock is held.
    db.commit()

    # ===== Stage 2: the Stripe call, outside any transaction =====

    # m. Create the Stripe Checkout Session. Everything comes from the order we just saved.
    stripe_line_items = []
    for order_item in order_items:
        stripe_line_items.append(
            {
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY,
                    "unit_amount": order_item.unit_price,
                    "product_data": {"name": order_item.product_name},
                },
                "quantity": order_item.quantity,
            }
        )
    # Stripe needs at least 30 minutes between creating the session and its expiry. The request
    # takes a moment to arrive, so one extra minute keeps us safely above the minimum.
    expires_at = int(time.time()) + CHECKOUT_SESSION_MINUTES * 60 + 60
    # Give the Stripe call a network timeout of 10 seconds
    stripe.default_http_client = stripe.RequestsClient(timeout=10)
    try:
        checkout_session = stripe.checkout.Session.create(
            api_key=settings.STRIPE_SECRET_KEY,
            mode="payment",
            line_items=stripe_line_items,
            client_reference_id=str(order.id),
            metadata={"order_id": str(order.id)},
            customer_email=current_user.email,
            success_url=settings.FRONTEND_BASE_URL + "/order-success.html?order_id=" + str(order.id),
            cancel_url=settings.FRONTEND_BASE_URL + "/order-cancelled.html?order_id=" + str(order.id),
            expires_at=expires_at,
            idempotency_key="order-" + str(order.id),
        )
    except stripe.StripeError:
        # Failure path: ONE transaction that gives everything back to the customer.
        # Same lock order as stage 1: the cart row first, then the product rows in ascending id order.
        cart_repository.lock_cart(db, current_user.id)
        failed_product_ids = []
        for order_item in order_items:
            failed_product_ids.append(order_item.product_id)
        failed_products = product_repository.lock_products(db, failed_product_ids)
        failed_products_by_id = {}
        for failed_product in failed_products:
            failed_products_by_id[failed_product.id] = failed_product

        # Cancel the order and fail the payment
        order.status = "cancelled"
        payment.status = "failed"

        # Give the stock back and put the items back into the cart
        for order_item in order_items:
            failed_product = failed_products_by_id[order_item.product_id]
            failed_product.stock = failed_product.stock + order_item.quantity
            cart_repository.upsert_cart_item(db, cart_id, order_item.product_id, order_item.quantity)
        db.commit()

        # The Stripe error text is not sent to the client
        raise HTTPException(
            status_code=502,
            detail="Payment service is unavailable. Your cart has not been changed. Please try again.",
        )

    # n. In a second small transaction, save the session id on the payment
    payment.stripe_checkout_session_id = checkout_session.id
    db.commit()

    return {
        "order_id": order.id,
        "checkout_url": checkout_session.url,
        "total_amount": total_amount,
    }
