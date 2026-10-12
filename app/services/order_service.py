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
