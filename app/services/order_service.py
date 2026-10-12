from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import order_repository


def list_orders(db: Session, current_user: User, page: int, page_size: int):
    # Work out how many rows to skip for this page
    offset = (page - 1) * page_size

    # Read the page and the total (only this user's orders)
    orders, total = order_repository.list_orders(db, current_user.id, offset, page_size)

    # Build one entry per order, with the total quantity of its items
    entries = []
    for order in orders:
        item_count = 0
        items = []
        for order_item in order.items:
            item_count = item_count + order_item.quantity
            items.append(
                {
                    "product_id": order_item.product_id,
                    "product_name": order_item.product_name,
                    "unit_price": order_item.unit_price,
                    "quantity": order_item.quantity,
                }
            )
        entries.append(
            {
                "id": order.id,
                "status": order.status,
                "total_amount": order.total_amount,
                "created_at": order.created_at,
                "item_count": item_count,
                "items": items,
            }
        )

    return {"items": entries, "total": total, "page": page, "page_size": page_size}


def get_order(db: Session, current_user: User, order_id: int):
    # Find the order among this user's orders. Someone else's order looks like "not found".
    order = order_repository.get_order(db, current_user.id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Build the items with their line totals (the snapshot prices, never the current product prices)
    items = []
    for order_item in sorted(order.items, key=lambda order_item: order_item.id):
        items.append(
            {
                "product_id": order_item.product_id,
                "product_name": order_item.product_name,
                "unit_price": order_item.unit_price,
                "quantity": order_item.quantity,
                "line_total": order_item.unit_price * order_item.quantity,
            }
        )

    # Build the shipping address from the copy stored in the order
    shipping_address = {
        "full_name": order.shipping_full_name,
        "phone": order.shipping_phone,
        "line1": order.shipping_line1,
        "line2": order.shipping_line2,
        "city": order.shipping_city,
        "state": order.shipping_state,
        "postal_code": order.shipping_postal_code,
        "country": order.shipping_country,
    }

    # Only the payment status, amount and currency. Stripe ids never leave the server.
    payment = None
    if order.payment is not None:
        payment = {
            "status": order.payment.status,
            "amount": order.payment.amount,
            "currency": order.payment.currency,
        }

    return {
        "id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at,
        "shipping_address": shipping_address,
        "items": items,
        "payment": payment,
    }


def list_seller_orders(db: Session, current_user: User, page: int, page_size: int):
    # Work out how many rows to skip for this page
    offset = (page - 1) * page_size

    # Read the page and the total (only paid orders that contain this seller's products)
    orders, total = order_repository.list_orders_for_seller(db, current_user.id, offset, page_size)

    # Build one entry per order. Only this seller's own lines are shown, never the other sellers' lines.
    entries = []
    for order in orders:
        items = []
        seller_subtotal = 0
        for order_item in sorted(order.items, key=lambda order_item: order_item.id):
            if order_item.product.seller_id != current_user.id:
                continue
            line_total = order_item.unit_price * order_item.quantity
            seller_subtotal = seller_subtotal + line_total
            items.append(
                {
                    "product_id": order_item.product_id,
                    "product_name": order_item.product_name,
                    "unit_price": order_item.unit_price,
                    "quantity": order_item.quantity,
                    "line_total": line_total,
                }
            )
        entries.append(
            {
                "id": order.id,
                "status": order.status,
                "created_at": order.created_at,
                "items": items,
                "seller_subtotal": seller_subtotal,
                # The order has more lines than this seller's lines
                "has_other_sellers": len(order.items) != len(items),
            }
        )

    return {"items": entries, "total": total, "page": page, "page_size": page_size}


def get_seller_order(db: Session, current_user: User, order_id: int):
    # Find the order only if this seller may see it. Anything else looks like "not found".
    order = order_repository.get_order_for_seller(db, current_user.id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Only this seller's own lines (the snapshot prices), never the other sellers' lines
    items = []
    seller_subtotal = 0
    for order_item in sorted(order.items, key=lambda order_item: order_item.id):
        if order_item.product.seller_id != current_user.id:
            continue
        line_total = order_item.unit_price * order_item.quantity
        seller_subtotal = seller_subtotal + line_total
        items.append(
            {
                "product_id": order_item.product_id,
                "product_name": order_item.product_name,
                "unit_price": order_item.unit_price,
                "quantity": order_item.quantity,
                "line_total": line_total,
            }
        )

    # The seller needs the shipping address to ship. The customer's email is never included.
    shipping_address = {
        "full_name": order.shipping_full_name,
        "phone": order.shipping_phone,
        "line1": order.shipping_line1,
        "line2": order.shipping_line2,
        "city": order.shipping_city,
        "state": order.shipping_state,
        "postal_code": order.shipping_postal_code,
        "country": order.shipping_country,
    }

    return {
        "id": order.id,
        "status": order.status,
        "created_at": order.created_at,
        "items": items,
        "seller_subtotal": seller_subtotal,
        "has_other_sellers": len(order.items) != len(items),
        "shipping_address": shipping_address,
    }


def list_admin_orders(db: Session, status: str | None, page: int, page_size: int):
    # Work out how many rows to skip for this page
    offset = (page - 1) * page_size

    # Read the page and the total (all orders, optionally only one status)
    rows, total = order_repository.list_orders_for_admin(db, status, offset, page_size)

    # Build one entry per order, with the total quantity of its items
    entries = []
    for order, customer_email in rows:
        item_count = 0
        for order_item in order.items:
            item_count = item_count + order_item.quantity
        entries.append(
            {
                "id": order.id,
                "status": order.status,
                "created_at": order.created_at,
                "total_amount": order.total_amount,
                "customer_email": customer_email,
                "shipping_full_name": order.shipping_full_name,
                "item_count": item_count,
            }
        )

    return {"items": entries, "total": total, "page": page, "page_size": page_size}


def get_admin_order(db: Session, order_id: int):
    # Find the order (any customer's)
    row = order_repository.get_order_for_admin(db, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order, customer_email = row

    # Build the items with their line totals, and count the total quantity
    items = []
    item_count = 0
    for order_item in sorted(order.items, key=lambda order_item: order_item.id):
        item_count = item_count + order_item.quantity
        items.append(
            {
                "product_id": order_item.product_id,
                "product_name": order_item.product_name,
                "unit_price": order_item.unit_price,
                "quantity": order_item.quantity,
                "line_total": order_item.unit_price * order_item.quantity,
            }
        )

    # Build the shipping address from the copy stored in the order
    shipping_address = {
        "full_name": order.shipping_full_name,
        "phone": order.shipping_phone,
        "line1": order.shipping_line1,
        "line2": order.shipping_line2,
        "city": order.shipping_city,
        "state": order.shipping_state,
        "postal_code": order.shipping_postal_code,
        "country": order.shipping_country,
    }

    # Only the payment status, amount and currency. Stripe ids never leave the server.
    payment = None
    if order.payment is not None:
        payment = {
            "status": order.payment.status,
            "amount": order.payment.amount,
            "currency": order.payment.currency,
        }

    return {
        "id": order.id,
        "status": order.status,
        "created_at": order.created_at,
        "total_amount": order.total_amount,
        "customer_email": customer_email,
        "shipping_full_name": order.shipping_full_name,
        "item_count": item_count,
        "user_id": order.user_id,
        "shipping_address": shipping_address,
        "items": items,
        "payment": payment,
    }
