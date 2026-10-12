from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import cart_repository, product_repository

# The most of one product a cart can hold (also limited by the stock)
MAX_QUANTITY_PER_PRODUCT = 10


def get_cart(db: Session, current_user: User):
    # Read the lines of the cart with their products (no cart row means no lines).
    # This function only reads. It never changes data.
    cart_items = cart_repository.list_cart_items(db, current_user.id)

    # Work out every line, the item count and the subtotal
    items = []
    item_count = 0
    subtotal = 0
    has_problems = False
    for cart_item in cart_items:
        product = cart_item.product

        # A line is available when the product is active and there is enough stock
        available = product.is_active and product.stock >= cart_item.quantity
        problem = None
        if not product.is_active:
            problem = "No longer available"
        elif product.stock == 0:
            problem = "Out of stock"
        elif product.stock < cart_item.quantity:
            problem = "Only " + str(product.stock) + " left"

        # The price is always the current product price (the cart stores no price)
        line_total = product.price * cart_item.quantity

        # Only available lines are part of the subtotal, but every line is counted in item_count
        item_count = item_count + cart_item.quantity
        if available:
            subtotal = subtotal + line_total
        else:
            has_problems = True

        items.append(
            {
                "product_id": product.id,
                "name": product.name,
                "image_url": product.image_url,
                "unit_price": product.price,
                "stock": product.stock,
                "is_active": product.is_active,
                "quantity": cart_item.quantity,
                "line_total": line_total,
                "available": available,
                "problem": problem,
            }
        )

    return {
        "items": items,
        "item_count": item_count,
        "subtotal": subtotal,
        "has_problems": has_problems,
    }


def get_cart_count(db: Session, current_user: User):
    # One cheap query: the sum of all quantities
    item_count = cart_repository.count_cart_quantity(db, current_user.id)
    return {"item_count": item_count}


def add_item(db: Session, current_user: User, product_id: int, quantity: int):
    # Load the product. A missing or inactive product cannot be added.
    product = product_repository.get_product_by_id(db, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")

    # Make sure the user has a cart (atomic insert, no check-then-insert)
    cart_id = cart_repository.get_or_create_cart_id(db, current_user.id)

    # Add the item with one atomic upsert. It gives back the new quantity of the line.
    new_quantity = cart_repository.upsert_cart_item(db, cart_id, product.id, quantity)

    # Too many: undo everything this request did, so the cart stays exactly as it was
    maximum_quantity = min(product.stock, MAX_QUANTITY_PER_PRODUCT)
    if new_quantity > maximum_quantity:
        db.rollback()
        if maximum_quantity == 0:
            raise HTTPException(status_code=409, detail="Out of stock")
        raise HTTPException(
            status_code=409, detail="Maximum quantity for this product is " + str(maximum_quantity)
        )

    # Count the whole cart, save, and answer
    item_count = cart_repository.count_cart_quantity(db, current_user.id)
    db.commit()
    return {"product_id": product.id, "quantity": new_quantity, "item_count": item_count}


def update_item(db: Session, current_user: User, product_id: int, quantity: int):
    # Find the line in this user's cart. Another user's cart is never searched.
    cart_item = cart_repository.get_cart_item(db, current_user.id, product_id)
    if cart_item is None:
        raise HTTPException(status_code=404, detail="Product is not in your cart")

    # An inactive product cannot be bought any more
    product = cart_item.product
    if not product.is_active:
        raise HTTPException(status_code=409, detail="This product is no longer available")

    # Check the limit before changing anything, so a refused request changes nothing
    maximum_quantity = min(product.stock, MAX_QUANTITY_PER_PRODUCT)
    if quantity > maximum_quantity:
        if maximum_quantity == 0:
            raise HTTPException(status_code=409, detail="Out of stock")
        raise HTTPException(
            status_code=409, detail="Maximum quantity for this product is " + str(maximum_quantity)
        )

    # Set the quantity to exactly this value
    cart_item.quantity = quantity
    db.flush()

    # Count the whole cart, save, and answer
    item_count = cart_repository.count_cart_quantity(db, current_user.id)
    db.commit()
    return {"product_id": product.id, "quantity": quantity, "item_count": item_count}


def remove_item(db: Session, current_user: User, product_id: int):
    # Remove the line. It is fine if the line does not exist (for example a double click).
    cart_repository.delete_cart_item(db, current_user.id, product_id)
    db.commit()


def clear_cart(db: Session, current_user: User):
    # Remove all lines. It is fine if there is no cart. The cart row stays.
    cart_repository.delete_all_cart_items(db, current_user.id)
    db.commit()
