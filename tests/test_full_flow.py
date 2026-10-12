from types import SimpleNamespace

from tests.conftest import make_event


def test_the_whole_store_through_the_api(
    client, create_user, create_category, auth_headers, stripe_create, post_webhook, refund_create, read_stock, read_order
):
    # An admin makes the category (admins come from the seed, they cannot register)
    create_user("admin@example.com", role="admin")
    admin = auth_headers("admin@example.com")
    category = client.post("/categories", json={"name": "Books"}, headers=admin)
    assert category.status_code == 201

    # A seller registers, logs in and creates a product with 5 in stock
    response = client.post(
        "/auth/register",
        json={"email": "seller@example.com", "password": "Password@123", "full_name": "Sam Seller", "role": "seller"},
    )
    assert response.status_code == 201
    seller = auth_headers("seller@example.com")
    product = client.post(
        "/products",
        json={
            "name": "Python Book",
            "description": "Learn Python step by step",
            "price": 25000,
            "stock": 5,
            "category_id": category.json()["id"],
        },
        headers=seller,
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    # A customer registers, logs in and adds an address
    response = client.post(
        "/auth/register",
        json={"email": "customer@example.com", "password": "Password@123", "full_name": "Cathy Customer"},
    )
    assert response.status_code == 201
    customer = auth_headers("customer@example.com")
    address = client.post(
        "/users/me/addresses",
        json={
            "full_name": "Cathy Customer",
            "phone": "9876543210",
            "line1": "12 MG Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
        },
        headers=customer,
    )
    assert address.status_code == 201

    # The customer finds the product by searching and adds two of them to the cart
    search = client.get("/products?q=python")
    assert search.json()["total"] == 1
    added = client.post("/cart/items", json={"product_id": product_id, "quantity": 2}, headers=customer)
    assert added.json()["item_count"] == 2

    # Checkout (Stripe is patched): an order waiting for payment, and 2 items are reserved
    checkout = client.post("/orders/checkout", json={"address_id": address.json()["id"]}, headers=customer)
    assert checkout.status_code == 201
    order_id = checkout.json()["order_id"]
    assert checkout.json()["checkout_url"].startswith("https://checkout.stripe.com/")
    assert checkout.json()["total_amount"] == 50000
    assert client.get("/orders/" + str(order_id), headers=customer).json()["status"] == "pending_payment"
    assert read_stock(product_id) == 3

    # The seller does not see the order yet (it is not paid)
    assert client.get("/seller/orders", headers=seller).json()["total"] == 0

    # Stripe tells us about the payment with a signed event: the order is paid
    order = SimpleNamespace(id=order_id, total_amount=50000, session_id="cs_test_order-" + str(order_id))
    event = make_event("checkout.session.completed", order.session_id, order, payment_intent="pi_test_flow_1")
    assert post_webhook(event).status_code == 200
    assert client.get("/orders/" + str(order_id), headers=customer).json()["status"] == "paid"

    # The seller sees the order, marks it shipped, and the customer sees the change
    assert client.get("/seller/orders", headers=seller).json()["total"] == 1
    shipped = client.patch("/seller/orders/" + str(order_id) + "/status", json={"status": "shipped"}, headers=seller)
    assert shipped.status_code == 200
    assert client.get("/orders/" + str(order_id), headers=customer).json()["status"] == "shipped"

    # Then delivered
    delivered = client.patch("/seller/orders/" + str(order_id) + "/status", json={"status": "delivered"}, headers=seller)
    assert delivered.status_code == 200
    final_order = client.get("/orders/" + str(order_id), headers=customer).json()
    assert final_order["status"] == "delivered"
    assert final_order["payment"]["status"] == "succeeded"

    # A delivered order can no longer be cancelled
    assert client.post("/orders/" + str(order_id) + "/cancel", headers=customer).status_code == 409

    # A second order: one item is added, bought and paid for
    client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=customer)
    second_checkout = client.post("/orders/checkout", json={"address_id": address.json()["id"]}, headers=customer)
    second_id = second_checkout.json()["order_id"]
    assert read_stock(product_id) == 2
    second_order = SimpleNamespace(id=second_id, total_amount=25000, session_id="cs_test_order-" + str(second_id))
    second_event = make_event(
        "checkout.session.completed", second_order.session_id, second_order, payment_intent="pi_test_flow_2", event_id="evt_2"
    )
    assert post_webhook(second_event).status_code == 200
    assert read_order(second_id)["order_status"] == "paid"

    # The customer cancels the paid order: the stock comes back and the money is refunded
    cancel = client.post("/orders/" + str(second_id) + "/cancel", headers=customer)
    assert cancel.status_code == 200
    assert cancel.json() == {"order_id": second_id, "status": "cancelled", "payment_status": "refunded"}
    assert read_stock(product_id) == 3

    # Stripe was asked for exactly one full refund of that payment (with the idempotency key)
    assert refund_create.call_count == 1
    refund_arguments = refund_create.call_args.kwargs
    assert refund_arguments["payment_intent"] == "pi_test_flow_2"
    assert refund_arguments["idempotency_key"] == "cancel-refund-" + str(second_id)

    # The customer sees both orders in the list: the delivered one and the cancelled one
    orders = client.get("/orders", headers=customer).json()
    assert orders["total"] == 2
    statuses = {}
    for entry in orders["items"]:
        statuses[entry["id"]] = entry["status"]
    assert statuses == {order_id: "delivered", second_id: "cancelled"}
