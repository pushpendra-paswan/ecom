import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def stripe_test_key(monkeypatch):
    # A dummy Stripe test key for every test in this file (the real Stripe API is never called)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_dummy")


@pytest.fixture
def shop(store, create_user, auth_headers):
    # Two sellers, a second customer, an admin, and their login headers
    seller_two_id = create_user("seller2@example.com", role="seller")
    create_user("other@example.com")
    create_user("admin@example.com", role="admin")

    class Shop:
        seller_one = auth_headers("seller@example.com")
        seller_two = auth_headers("seller2@example.com")
        admin = auth_headers("admin@example.com")
        customer = store.customer
        other_customer = auth_headers("other@example.com")

        def product_of_one(self, stock=10, price=10000):
            return store.product(stock=stock, price=price)

        def product_of_two(self, stock=10, price=10000):
            return store.product(stock=stock, price=price, seller=seller_two_id)

        def place_order(self, items, customer=None):
            return store.place_order(items, customer)

    return Shop()


@pytest.fixture
def set_status(change_database):
    # Returns a function that sets the order status straight in the database (to reach shipped and so on)
    def change(order_id, status):
        change_database("UPDATE orders SET status = :status WHERE id = :id", status=status, id=order_id)

    return change


def patch_status(client, role_path, order_id, status, headers):
    # PATCH /seller/orders/{id}/status or /admin/orders/{id}/status
    return client.patch(role_path + "/orders/" + str(order_id) + "/status", json={"status": status}, headers=headers)


# ---------- who may call what ----------


ORDER_ENDPOINTS = [
    ("GET", "/seller/orders"),
    ("GET", "/seller/orders/1"),
    ("PATCH", "/seller/orders/1/status"),
    ("GET", "/admin/orders"),
    ("GET", "/admin/orders/1"),
    ("PATCH", "/admin/orders/1/status"),
]


@pytest.mark.parametrize("method, path", ORDER_ENDPOINTS)
def test_no_token_gives_401(client, method, path):
    response = client.request(method, path, json={"status": "shipped"} if method == "PATCH" else None)
    assert response.status_code == 401


@pytest.mark.parametrize("method, path", ORDER_ENDPOINTS)
def test_a_customer_gets_403_everywhere(client, shop, method, path):
    body = {"status": "shipped"} if method == "PATCH" else None
    response = client.request(method, path, json=body, headers=shop.customer)
    assert response.status_code == 403


@pytest.mark.parametrize("method, path", [endpoint for endpoint in ORDER_ENDPOINTS if "/admin/" in endpoint[1]])
def test_a_seller_gets_403_on_admin_endpoints(client, shop, method, path):
    body = {"status": "shipped"} if method == "PATCH" else None
    response = client.request(method, path, json=body, headers=shop.seller_one)
    assert response.status_code == 403


def test_an_admin_gets_403_on_seller_endpoints(client, shop):
    assert client.get("/seller/orders", headers=shop.admin).status_code == 403


# ---------- changing the status ----------


def test_a_seller_ships_and_delivers_their_own_order(client, shop, pay, read_order):
    order = shop.place_order([(shop.product_of_one(), 1)])
    pay(order)

    shipped = patch_status(client, "/seller", order.id, "shipped", shop.seller_one)
    assert shipped.status_code == 200
    assert shipped.json() == {"order_id": order.id, "status": "shipped"}
    assert read_order(order.id)["order_status"] == "shipped"

    delivered = patch_status(client, "/seller", order.id, "delivered", shop.seller_one)
    assert delivered.status_code == 200
    assert delivered.json() == {"order_id": order.id, "status": "delivered"}
    assert read_order(order.id)["order_status"] == "delivered"


def test_wrong_transitions_give_409(client, shop, pay, set_status, read_order):
    paid_order = shop.place_order([(shop.product_of_one(), 1)])
    pay(paid_order)
    delivered_order = shop.place_order([(shop.product_of_one(), 1)])
    pay(delivered_order)
    set_status(delivered_order.id, "delivered")
    cancelled_order = shop.place_order([(shop.product_of_one(), 1)])
    pay(cancelled_order)
    assert client.post("/orders/" + str(cancelled_order.id) + "/cancel", headers=shop.customer).status_code == 200
    pending_order = shop.place_order([(shop.product_of_one(), 1)])

    # A seller: paid to delivered, delivered to shipped, cancelled (refunded) to shipped
    response = patch_status(client, "/seller", paid_order.id, "delivered", shop.seller_one)
    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot change an order from paid to delivered."
    response = patch_status(client, "/seller", delivered_order.id, "shipped", shop.seller_one)
    assert response.status_code == 409
    response = patch_status(client, "/seller", cancelled_order.id, "shipped", shop.seller_one)
    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot change an order from cancelled to shipped."

    # An admin: pending_payment to shipped (a seller cannot even see that order)
    response = patch_status(client, "/admin", pending_order.id, "shipped", shop.admin)
    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot change an order from pending_payment to shipped."

    # Nothing changed
    assert read_order(paid_order.id)["order_status"] == "paid"
    assert read_order(delivered_order.id)["order_status"] == "delivered"
    assert read_order(cancelled_order.id)["order_status"] == "cancelled"
    assert read_order(pending_order.id)["order_status"] == "pending_payment"


def test_the_same_status_again_gives_200_and_changes_nothing(client, shop, pay, read_order):
    order = shop.place_order([(shop.product_of_one(), 1)])
    pay(order)
    assert patch_status(client, "/seller", order.id, "shipped", shop.seller_one).status_code == 200
    state_after_first = read_order(order.id)

    again = patch_status(client, "/seller", order.id, "shipped", shop.seller_one)

    assert again.status_code == 200
    assert again.json() == {"order_id": order.id, "status": "shipped"}
    assert read_order(order.id) == state_after_first


@pytest.mark.parametrize("status", ["paid", "cancelled", "pending_payment", "banana"])
def test_other_status_values_give_422(client, shop, pay, read_order, status):
    order = shop.place_order([(shop.product_of_one(), 1)])
    pay(order)
    # "shipped to paid" can never be asked for: paid is not an accepted value at all
    assert patch_status(client, "/seller", order.id, status, shop.seller_one).status_code == 422
    assert patch_status(client, "/admin", order.id, status, shop.admin).status_code == 422
    assert read_order(order.id)["order_status"] == "paid"


def test_a_non_numeric_order_id_gives_422(client, shop):
    assert client.get("/seller/orders/abc", headers=shop.seller_one).status_code == 422
    assert client.get("/admin/orders/abc", headers=shop.admin).status_code == 422


# ---------- orders with products from two sellers ----------


@pytest.fixture
def mixed_order(shop, pay):
    # One paid order: 2 x (seller one, Rs 100) and 1 x (seller two, Rs 250)
    product_one = shop.product_of_one(price=10000)
    product_two = shop.product_of_two(price=25000)
    order = shop.place_order([(product_one, 2), (product_two, 1)])
    pay(order)
    order.product_one = product_one
    order.product_two = product_two
    return order


def test_each_seller_sees_only_their_own_lines(client, shop, mixed_order):
    one = client.get("/seller/orders/" + str(mixed_order.id), headers=shop.seller_one).json()
    two = client.get("/seller/orders/" + str(mixed_order.id), headers=shop.seller_two).json()

    assert [item["product_id"] for item in one["items"]] == [mixed_order.product_one]
    assert one["seller_subtotal"] == 20000
    assert one["has_other_sellers"] is True
    assert [item["product_id"] for item in two["items"]] == [mixed_order.product_two]
    assert two["seller_subtotal"] == 25000
    assert two["has_other_sellers"] is True

    # The list shows the same
    listing = client.get("/seller/orders", headers=shop.seller_two).json()
    assert listing["total"] == 1
    assert listing["items"][0]["seller_subtotal"] == 25000
    assert listing["items"][0]["has_other_sellers"] is True


def test_a_seller_cannot_change_a_mixed_order_but_an_admin_can(client, shop, mixed_order, read_order):
    for headers in (shop.seller_one, shop.seller_two):
        response = patch_status(client, "/seller", mixed_order.id, "shipped", headers)
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "This order includes products from other sellers. Only an admin can update its status."
        )
    assert read_order(mixed_order.id)["order_status"] == "paid"

    response = patch_status(client, "/admin", mixed_order.id, "shipped", shop.admin)

    assert response.status_code == 200
    assert read_order(mixed_order.id)["order_status"] == "shipped"


# ---------- what a seller may see ----------


def test_a_seller_without_products_in_the_order_gets_404(client, shop, create_user, auth_headers, pay):
    order = shop.place_order([(shop.product_of_one(), 1)])
    pay(order)
    # seller two has no product in this order
    assert client.get("/seller/orders/" + str(order.id), headers=shop.seller_two).status_code == 404
    assert patch_status(client, "/seller", order.id, "shipped", shop.seller_two).status_code == 404
    assert client.get("/seller/orders", headers=shop.seller_two).json()["total"] == 0
    # A missing order is 404 for both
    assert client.get("/seller/orders/9999", headers=shop.seller_one).status_code == 404
    assert patch_status(client, "/seller", 9999, "shipped", shop.seller_one).status_code == 404
    assert patch_status(client, "/admin", 9999, "shipped", shop.admin).status_code == 404


def test_unpaid_and_failed_orders_are_hidden_but_refunded_ones_are_shown(client, shop, pay, read_order):
    pending_order = shop.place_order([(shop.product_of_one(), 1)])
    failed_order = shop.place_order([(shop.product_of_one(), 1)])
    assert client.post("/orders/" + str(failed_order.id) + "/cancel", headers=shop.customer).status_code == 200
    refunded_order = shop.place_order([(shop.product_of_one(), 1)])
    pay(refunded_order)
    assert client.post("/orders/" + str(refunded_order.id) + "/cancel", headers=shop.customer).status_code == 200
    assert read_order(failed_order.id)["payment_status"] == "failed"
    assert read_order(refunded_order.id)["payment_status"] == "refunded"

    # Pending (payment pending) and cancelled with a failed payment: 404 on read and update
    for hidden in (pending_order, failed_order):
        assert client.get("/seller/orders/" + str(hidden.id), headers=shop.seller_one).status_code == 404
        assert patch_status(client, "/seller", hidden.id, "shipped", shop.seller_one).status_code == 404

    # Cancelled with a refunded payment: still shown, and it is the only order in the list
    assert client.get("/seller/orders/" + str(refunded_order.id), headers=shop.seller_one).status_code == 200
    listing = client.get("/seller/orders", headers=shop.seller_one).json()
    assert [entry["id"] for entry in listing["items"]] == [refunded_order.id]
    assert listing["items"][0]["status"] == "cancelled"


def test_seller_list_is_newest_first_paginated_and_leaks_nothing(
    client, shop, pay, change_database
):
    orders = []
    for number in range(3):
        order = shop.place_order([(shop.product_of_one(), 1)])
        pay(order)
        orders.append(order)
    # Give them known times: the first one is the newest
    for position, order in enumerate(orders):
        change_database(
            "UPDATE orders SET created_at = now() - make_interval(hours => :hours) WHERE id = :id",
            hours=position,
            id=order.id,
        )

    response = client.get("/seller/orders", headers=shop.seller_one)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [entry["id"] for entry in body["items"]] == [orders[0].id, orders[1].id, orders[2].id]

    # The raw text has no customer email, no password hash and no Stripe id (list and detail)
    detail = client.get("/seller/orders/" + str(orders[0].id), headers=shop.seller_one)
    assert detail.json()["shipping_address"]["full_name"] == "Rohan Gupta"
    for text in (response.text, detail.text):
        assert "customer@example.com" not in text
        assert "password" not in text
        assert "$2b$" not in text
        assert "stripe" not in text.lower()
        assert "pi_test" not in text
        assert "cs_test" not in text

    # Pagination
    first_page = client.get("/seller/orders?page=1&page_size=2", headers=shop.seller_one).json()
    second_page = client.get("/seller/orders?page=2&page_size=2", headers=shop.seller_one).json()
    assert first_page["total"] == 3
    assert [entry["id"] for entry in first_page["items"]] == [orders[0].id, orders[1].id]
    assert [entry["id"] for entry in second_page["items"]] == [orders[2].id]


# ---------- the admin views ----------


def test_admin_list_filter_and_pagination(client, shop, pay, set_status):
    pending_order = shop.place_order([(shop.product_of_one(), 1)])
    paid_order = shop.place_order([(shop.product_of_one(), 1)])
    pay(paid_order)
    shipped_order = shop.place_order([(shop.product_of_two(), 1)], shop.other_customer)
    pay(shipped_order)
    set_status(shipped_order.id, "shipped")

    everything = client.get("/admin/orders", headers=shop.admin).json()
    assert everything["total"] == 3
    # Newest first (the ids go up with the creation time)
    assert [entry["id"] for entry in everything["items"]] == [shipped_order.id, paid_order.id, pending_order.id]
    entry = everything["items"][0]
    assert entry["customer_email"] == "other@example.com"
    assert entry["shipping_full_name"] == "Rohan Gupta"
    assert entry["item_count"] == 1
    assert entry["total_amount"] == 10000

    only_paid = client.get("/admin/orders?status=paid", headers=shop.admin).json()
    assert [entry["id"] for entry in only_paid["items"]] == [paid_order.id]
    assert only_paid["total"] == 1

    assert client.get("/admin/orders?status=banana", headers=shop.admin).status_code == 422

    second_page = client.get("/admin/orders?page=2&page_size=2", headers=shop.admin).json()
    assert second_page["total"] == 3
    assert [entry["id"] for entry in second_page["items"]] == [pending_order.id]


def test_admin_detail_has_the_email_and_no_stripe_ids(client, shop, mixed_order):
    response = client.get("/admin/orders/" + str(mixed_order.id), headers=shop.admin)

    assert response.status_code == 200
    body = response.json()
    assert body["customer_email"] == "customer@example.com"
    assert body["shipping_address"]["city"] == "Bengaluru"
    assert len(body["items"]) == 2
    assert body["items"][0]["line_total"] == 20000
    assert body["payment"] == {"status": "succeeded", "amount": 45000, "currency": "inr"}
    assert body["user_id"] > 0
    assert "stripe" not in response.text.lower()
    assert "pi_test" not in response.text
    assert "cs_test" not in response.text
    assert "password" not in response.text

    assert client.get("/admin/orders/9999", headers=shop.admin).status_code == 404


# ---------- products of a seller ----------


def test_seller_product_detail(client, shop, create_product, create_category):
    inactive_product = shop.product_of_one()
    client.delete("/products/" + str(inactive_product), headers=shop.seller_one)
    other_sellers_product = shop.product_of_two()

    own = client.get("/seller/products/" + str(inactive_product), headers=shop.seller_one)
    assert own.status_code == 200
    assert own.json()["id"] == inactive_product
    assert own.json()["is_active"] is False
    assert own.json()["category"]["name"] == "Books"

    assert client.get("/seller/products/" + str(other_sellers_product), headers=shop.seller_one).status_code == 404
    assert client.get("/seller/products/9999", headers=shop.seller_one).status_code == 404
    assert client.get("/seller/products/" + str(inactive_product), headers=shop.customer).status_code == 403
    assert client.get("/seller/products/" + str(inactive_product), headers=shop.admin).status_code == 403
    assert client.get("/seller/products/" + str(inactive_product)).status_code == 401


def test_patching_a_product_still_works_with_the_row_lock(client, shop, read_stock):
    product_id = shop.product_of_one(stock=10, price=10000)

    response = client.patch(
        "/products/" + str(product_id), json={"stock": 4, "price": 12345}, headers=shop.seller_one
    )

    assert response.status_code == 200
    assert response.json()["stock"] == 4
    assert response.json()["price"] == 12345
    assert read_stock(product_id) == 4

    # Another seller still gets 404 and the product is unchanged
    other = client.patch("/products/" + str(product_id), json={"stock": 99}, headers=shop.seller_two)
    assert other.status_code == 404
    assert read_stock(product_id) == 4

    # Deactivate and activate again
    assert client.delete("/products/" + str(product_id), headers=shop.seller_one).status_code == 204
    assert client.patch("/products/" + str(product_id), json={"is_active": True}, headers=shop.seller_one).status_code == 200
