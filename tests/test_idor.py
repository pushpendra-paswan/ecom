from tests.conftest import make_event

ADDRESS = {
    "full_name": "Customer A",
    "phone": "9876543210",
    "line1": "1 Secret Street",
    "city": "Pune",
    "state": "Maharashtra",
    "postal_code": "411001",
}


def test_customer_cannot_touch_another_customers_address(client, create_user, auth_headers, query_database):
    # Customer A has an address
    create_user("a@example.com")
    create_user("b@example.com")
    headers_a = auth_headers("a@example.com")
    headers_b = auth_headers("b@example.com")
    address_id = client.post("/users/me/addresses", json=ADDRESS, headers=headers_a).json()["id"]

    # Customer B cannot update it or delete it: both look like "not found"
    changed = dict(ADDRESS, line1="Hacked line")
    assert client.put("/users/me/addresses/" + str(address_id), json=changed, headers=headers_b).status_code == 404
    assert client.delete("/users/me/addresses/" + str(address_id), headers=headers_b).status_code == 404

    # B does not see it in the list either
    assert client.get("/users/me/addresses", headers=headers_b).json() == []

    # Nothing changed in the database
    rows = query_database("SELECT line1 FROM addresses WHERE id = :id", id=address_id)
    assert rows == [{"line1": "1 Secret Street"}]


def test_customer_cannot_read_or_cancel_another_customers_order(client, store, create_user, auth_headers, read_order, read_stock):
    # Customer A places an order
    product_id = store.product(stock=5)
    order = store.place_order([(product_id, 2)])

    # Customer B logs in
    create_user("b@example.com")
    headers_b = auth_headers("b@example.com")

    # B can neither read nor cancel it: both look like "not found"
    assert client.get("/orders/" + str(order.id), headers=headers_b).status_code == 404
    assert client.post("/orders/" + str(order.id) + "/cancel", headers=headers_b).status_code == 404
    assert client.get("/orders", headers=headers_b).json()["items"] == []

    # Nothing changed: the order is still waiting for payment and the stock is still reserved
    assert read_order(order.id)["order_status"] == "pending_payment"
    assert read_stock(product_id) == 3


def test_customer_cart_is_private(client, store, create_user, auth_headers, query_database):
    # Customer A has a line in the cart
    product_id = store.product(stock=5)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 2}, headers=store.customer)

    # Customer B sees an empty cart and cannot remove or change A's line
    create_user("b@example.com")
    headers_b = auth_headers("b@example.com")
    assert client.get("/cart", headers=headers_b).json()["items"] == []
    assert client.get("/cart/count", headers=headers_b).json() == {"item_count": 0}
    assert client.patch("/cart/items/" + str(product_id), json={"quantity": 1}, headers=headers_b).status_code == 404
    assert client.delete("/cart/items/" + str(product_id), headers=headers_b).status_code == 204
    assert client.delete("/cart", headers=headers_b).status_code == 204

    # A's line is untouched
    rows = query_database("SELECT quantity FROM cart_items")
    assert rows == [{"quantity": 2}]


def test_customer_cannot_checkout_with_another_customers_address(client, store, create_user, auth_headers, query_database):
    # Customer A has an address, customer B has a product in the cart
    address_id = client.post("/users/me/addresses", json=ADDRESS, headers=store.customer).json()["id"]
    create_user("b@example.com")
    headers_b = auth_headers("b@example.com")
    product_id = store.product(stock=5)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers_b)

    # B cannot ship to A's address
    response = client.post("/orders/checkout", json={"address_id": address_id}, headers=headers_b)
    assert response.status_code == 404

    # No order was made, and B's cart is unchanged
    assert query_database("SELECT count(*) AS total FROM orders") == [{"total": 0}]
    assert query_database("SELECT quantity FROM cart_items") == [{"quantity": 1}]


def test_seller_cannot_touch_another_sellers_product(client, store, create_user, auth_headers, query_database):
    # Seller A owns a product
    product_id = store.product(stock=5)

    # Seller B logs in
    create_user("seller-b@example.com", role="seller")
    headers_b = auth_headers("seller-b@example.com")

    # B cannot read it through the seller endpoint, edit it or deactivate it: all look like "not found"
    assert client.get("/seller/products/" + str(product_id), headers=headers_b).status_code == 404
    assert client.patch("/products/" + str(product_id), json={"name": "Hacked"}, headers=headers_b).status_code == 404
    assert client.delete("/products/" + str(product_id), headers=headers_b).status_code == 404
    assert client.get("/seller/products", headers=headers_b).json()["items"] == []

    # Nothing changed
    rows = query_database("SELECT name, is_active, stock FROM products WHERE id = :id", id=product_id)
    assert rows == [{"name": "Test product", "is_active": True, "stock": 5}]


def test_seller_cannot_see_or_change_an_order_with_only_another_sellers_products(
    client, store, create_user, auth_headers, pay, read_order
):
    # An order that holds only seller A's product, and it is paid
    product_id = store.product(stock=5)
    order = store.place_order([(product_id, 1)])
    pay(order)

    # Seller A can see it, seller B cannot
    create_user("seller-b@example.com", role="seller")
    headers_b = auth_headers("seller-b@example.com")
    seller_a_headers = auth_headers("seller@example.com")
    assert client.get("/seller/orders/" + str(order.id), headers=seller_a_headers).status_code == 200
    assert client.get("/seller/orders/" + str(order.id), headers=headers_b).status_code == 404
    assert client.get("/seller/orders", headers=headers_b).json()["items"] == []

    # B cannot change its status
    response = client.patch(
        "/seller/orders/" + str(order.id) + "/status", json={"status": "shipped"}, headers=headers_b
    )
    assert response.status_code == 404

    # The order is still paid
    assert read_order(order.id)["order_status"] == "paid"


def test_customer_cannot_see_an_inactive_product(client, store, change_database):
    # An inactive product is hidden from customers (and from everyone who is not its seller)
    product_id = store.product(stock=5)
    change_database("UPDATE products SET is_active = false WHERE id = :id", id=product_id)

    assert client.get("/products/" + str(product_id), headers=store.customer).status_code == 404
    assert client.get("/products").json()["total"] == 0
    assert client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=store.customer).status_code == 404


def test_webhook_event_for_another_session_does_not_pay_an_order(client, store, post_webhook, read_order):
    # A signed event whose session id belongs to a different order does not mark this order as paid
    first_order = store.place_order([(store.product(stock=5), 1)])
    second_order = store.place_order([(store.product(stock=5), 1)])

    # The event says "second order's session", but its metadata names the first order
    event = make_event("checkout.session.completed", second_order.session_id, first_order)
    assert post_webhook(event).status_code == 200

    # The payment is found by session id, so only the second order is paid
    assert read_order(first_order.id)["order_status"] == "pending_payment"
