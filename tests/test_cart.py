import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.catalog import Product


@pytest.fixture
def shop(create_user, create_category, create_product, auth_headers):
    # A seller, a category, a logged-in customer and a function that makes products
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_user("customer@example.com")

    class Shop:
        customer = auth_headers("customer@example.com")

        def product(self, **changes):
            return create_product(seller_id, category_id, **changes)

    return Shop()


@pytest.fixture
def change_product(test_engine):
    # Returns a function that changes a product straight in the test database
    def change(product_id, **values):
        with Session(test_engine) as session:
            product = session.get(Product, product_id)
            for field, value in values.items():
                setattr(product, field, value)
            session.commit()

    return change


@pytest.fixture
def table_snapshot(test_engine):
    # Returns a function that reads the carts and cart_items tables as plain rows
    def snapshot():
        with test_engine.connect() as connection:
            carts = connection.execute(text("SELECT * FROM carts ORDER BY id")).fetchall()
            items = connection.execute(text("SELECT * FROM cart_items ORDER BY id")).fetchall()
        return carts, items

    return snapshot


# ---------- access ----------


def test_every_cart_endpoint_needs_a_customer(client, create_user, auth_headers):
    create_user("seller@example.com", role="seller")
    create_user("admin@example.com", role="admin")
    calls = [
        ("get", "/cart", None),
        ("get", "/cart/count", None),
        ("post", "/cart/items", {"product_id": 1}),
        ("patch", "/cart/items/1", {"quantity": 1}),
        ("delete", "/cart/items/1", None),
        ("delete", "/cart", None),
    ]

    for method, path, body in calls:
        # No token: 401
        response = client.request(method, path, json=body)
        assert response.status_code == 401, (method, path)

        # A seller or an admin: 403
        for email in ("seller@example.com", "admin@example.com"):
            response = client.request(method, path, json=body, headers=auth_headers(email))
            assert response.status_code == 403, (method, path, email)


# ---------- reading ----------


def test_empty_cart_is_empty_and_creates_no_row(client, shop, table_snapshot):
    response = client.get("/cart", headers=shop.customer)
    assert response.status_code == 200
    assert response.json() == {"items": [], "item_count": 0, "subtotal": 0, "has_problems": False}

    # Reading did not create a cart row
    assert table_snapshot() == ([], [])

    count = client.get("/cart/count", headers=shop.customer)
    assert count.json() == {"item_count": 0}


# ---------- adding ----------


def test_add_item_then_add_it_again(client, shop):
    product_id = shop.product(price=25000, stock=20)

    first = client.post("/cart/items", json={"product_id": product_id, "quantity": 2}, headers=shop.customer)
    assert first.status_code == 200
    assert first.json() == {"product_id": product_id, "quantity": 2, "item_count": 2}

    # The quantity defaults to 1 and is added to the existing line
    second = client.post("/cart/items", json={"product_id": product_id}, headers=shop.customer)
    assert second.json() == {"product_id": product_id, "quantity": 3, "item_count": 3}

    cart = client.get("/cart", headers=shop.customer).json()
    assert len(cart["items"]) == 1
    line = cart["items"][0]
    assert line["quantity"] == 3
    assert line["unit_price"] == 25000
    assert line["line_total"] == 75000
    assert line["available"] is True
    assert line["problem"] is None
    assert cart["subtotal"] == 75000
    assert cart["item_count"] == 3
    assert cart["has_problems"] is False


def test_cannot_add_missing_inactive_or_sold_out_products(client, shop):
    inactive_id = shop.product(is_active=False)
    sold_out_id = shop.product(stock=0)

    missing = client.post("/cart/items", json={"product_id": 9999}, headers=shop.customer)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Product not found"

    inactive = client.post("/cart/items", json={"product_id": inactive_id}, headers=shop.customer)
    assert inactive.status_code == 404

    sold_out = client.post("/cart/items", json={"product_id": sold_out_id}, headers=shop.customer)
    assert sold_out.status_code == 409
    assert sold_out.json()["detail"] == "Out of stock"

    # Nothing was added
    assert client.get("/cart/count", headers=shop.customer).json() == {"item_count": 0}


def test_refused_add_leaves_the_cart_unchanged(client, shop):
    product_id = shop.product(stock=3)

    ok = client.post("/cart/items", json={"product_id": product_id, "quantity": 2}, headers=shop.customer)
    assert ok.status_code == 200

    # 2 + 2 is more than the stock of 3
    refused = client.post("/cart/items", json={"product_id": product_id, "quantity": 2}, headers=shop.customer)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Maximum quantity for this product is 3"

    # The rollback kept the quantity at 2
    cart = client.get("/cart", headers=shop.customer).json()
    assert cart["items"][0]["quantity"] == 2
    assert cart["item_count"] == 2


def test_refused_first_add_creates_no_line(client, shop, table_snapshot):
    product_id = shop.product(stock=1)

    refused = client.post("/cart/items", json={"product_id": product_id, "quantity": 2}, headers=shop.customer)
    assert refused.status_code == 409

    # Not even the cart row was kept
    assert table_snapshot() == ([], [])


def test_never_more_than_ten_of_one_product(client, shop):
    product_id = shop.product(stock=50)

    ok = client.post("/cart/items", json={"product_id": product_id, "quantity": 10}, headers=shop.customer)
    assert ok.status_code == 200

    too_many = client.post("/cart/items", json={"product_id": product_id}, headers=shop.customer)
    assert too_many.status_code == 409
    assert too_many.json()["detail"] == "Maximum quantity for this product is 10"
    assert client.get("/cart/count", headers=shop.customer).json() == {"item_count": 10}


def test_add_body_is_validated(client, shop):
    product_id = shop.product()

    for body in (
        {"product_id": product_id, "quantity": 0},
        {"product_id": product_id, "quantity": 11},
        {"quantity": 1},
        {"product_id": 0},
        {"product_id": "abc"},
    ):
        response = client.post("/cart/items", json=body, headers=shop.customer)
        assert response.status_code == 422, body


# ---------- changing and removing ----------


def test_patch_sets_the_exact_quantity(client, shop):
    product_id = shop.product(stock=20)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 5}, headers=shop.customer)

    response = client.patch(f"/cart/items/{product_id}", json={"quantity": 2}, headers=shop.customer)
    assert response.status_code == 200
    assert response.json() == {"product_id": product_id, "quantity": 2, "item_count": 2}
    assert client.get("/cart", headers=shop.customer).json()["items"][0]["quantity"] == 2


def test_patch_errors(client, shop, change_product):
    product_id = shop.product(stock=4)
    other_id = shop.product(stock=4)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 2}, headers=shop.customer)

    # Not in the cart
    not_in_cart = client.patch(f"/cart/items/{other_id}", json={"quantity": 1}, headers=shop.customer)
    assert not_in_cart.status_code == 404

    # Above the stock
    too_many = client.patch(f"/cart/items/{product_id}", json={"quantity": 5}, headers=shop.customer)
    assert too_many.status_code == 409
    assert too_many.json()["detail"] == "Maximum quantity for this product is 4"

    # Zero is not allowed (use DELETE)
    zero = client.patch(f"/cart/items/{product_id}", json={"quantity": 0}, headers=shop.customer)
    assert zero.status_code == 422

    # An inactive product
    change_product(product_id, is_active=False)
    inactive = client.patch(f"/cart/items/{product_id}", json={"quantity": 1}, headers=shop.customer)
    assert inactive.status_code == 409
    assert inactive.json()["detail"] == "This product is no longer available"

    # The refused requests changed nothing
    assert client.get("/cart/count", headers=shop.customer).json() == {"item_count": 2}


def test_delete_one_line_twice(client, shop):
    first_id = shop.product()
    second_id = shop.product()
    client.post("/cart/items", json={"product_id": first_id}, headers=shop.customer)
    client.post("/cart/items", json={"product_id": second_id}, headers=shop.customer)

    assert client.delete(f"/cart/items/{first_id}", headers=shop.customer).status_code == 204
    assert client.delete(f"/cart/items/{first_id}", headers=shop.customer).status_code == 204

    cart = client.get("/cart", headers=shop.customer).json()
    assert [item["product_id"] for item in cart["items"]] == [second_id]


def test_clear_cart(client, shop, table_snapshot):
    # With no cart at all it still answers 204
    assert client.delete("/cart", headers=shop.customer).status_code == 204

    first_id = shop.product()
    second_id = shop.product()
    client.post("/cart/items", json={"product_id": first_id}, headers=shop.customer)
    client.post("/cart/items", json={"product_id": second_id}, headers=shop.customer)

    assert client.delete("/cart", headers=shop.customer).status_code == 204
    assert client.get("/cart", headers=shop.customer).json()["items"] == []

    # The lines are gone, the cart row stays
    carts, items = table_snapshot()
    assert len(carts) == 1
    assert items == []


# ---------- products that changed after they were added ----------


def test_items_are_ordered_by_when_they_were_added(client, shop):
    first_id = shop.product(name="First")
    second_id = shop.product(name="Second")
    client.post("/cart/items", json={"product_id": second_id}, headers=shop.customer)
    client.post("/cart/items", json={"product_id": first_id}, headers=shop.customer)
    client.post("/cart/items", json={"product_id": second_id}, headers=shop.customer)

    names = [item["name"] for item in client.get("/cart", headers=shop.customer).json()["items"]]
    assert names == ["Second", "First"]


def test_subtotal_with_two_prices(client, shop):
    cheap_id = shop.product(price=9900)
    dear_id = shop.product(price=150050)
    client.post("/cart/items", json={"product_id": cheap_id, "quantity": 3}, headers=shop.customer)
    client.post("/cart/items", json={"product_id": dear_id, "quantity": 2}, headers=shop.customer)

    cart = client.get("/cart", headers=shop.customer).json()
    assert cart["subtotal"] == 3 * 9900 + 2 * 150050
    assert cart["item_count"] == 5


def test_inactive_product_is_reported_and_left_out(client, shop, change_product):
    kept_id = shop.product(price=10000)
    gone_id = shop.product(price=20000)
    client.post("/cart/items", json={"product_id": kept_id}, headers=shop.customer)
    client.post("/cart/items", json={"product_id": gone_id, "quantity": 2}, headers=shop.customer)
    change_product(gone_id, is_active=False)

    cart = client.get("/cart", headers=shop.customer).json()
    gone_line = cart["items"][1]
    assert gone_line["available"] is False
    assert gone_line["problem"] == "No longer available"
    assert gone_line["is_active"] is False
    assert cart["items"][0]["available"] is True
    assert cart["subtotal"] == 10000
    assert cart["has_problems"] is True
    # Every line is counted in item_count
    assert cart["item_count"] == 3


def test_stock_below_quantity_and_stock_zero(client, shop, change_product):
    low_id = shop.product(stock=10)
    empty_id = shop.product(stock=10)
    client.post("/cart/items", json={"product_id": low_id, "quantity": 4}, headers=shop.customer)
    client.post("/cart/items", json={"product_id": empty_id, "quantity": 2}, headers=shop.customer)
    change_product(low_id, stock=3)
    change_product(empty_id, stock=0)

    cart = client.get("/cart", headers=shop.customer).json()
    assert cart["items"][0]["problem"] == "Only 3 left"
    assert cart["items"][0]["available"] is False
    assert cart["items"][1]["problem"] == "Out of stock"
    assert cart["items"][1]["available"] is False
    assert cart["subtotal"] == 0
    assert cart["has_problems"] is True

    # The count still includes both lines
    assert client.get("/cart/count", headers=shop.customer).json() == {"item_count": 6}


def test_reading_the_cart_changes_nothing(client, shop, change_product, table_snapshot):
    product_id = shop.product(stock=10)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 5}, headers=shop.customer)
    change_product(product_id, stock=2, is_active=False)

    before = table_snapshot()
    client.get("/cart", headers=shop.customer)
    client.get("/cart/count", headers=shop.customer)
    assert table_snapshot() == before


# ---------- isolation ----------


def test_customers_cannot_see_or_change_each_others_carts(client, shop, create_user, auth_headers):
    create_user("other@example.com")
    other = auth_headers("other@example.com")
    product_id = shop.product(stock=10)
    client.post("/cart/items", json={"product_id": product_id, "quantity": 3}, headers=shop.customer)

    # The other customer sees an empty cart
    assert client.get("/cart", headers=other).json()["items"] == []
    assert client.get("/cart/count", headers=other).json() == {"item_count": 0}

    # The other customer cannot change or delete that line
    patched = client.patch(f"/cart/items/{product_id}", json={"quantity": 1}, headers=other)
    assert patched.status_code == 404
    assert client.delete(f"/cart/items/{product_id}", headers=other).status_code == 204
    assert client.delete("/cart", headers=other).status_code == 204

    # The first cart is untouched
    assert client.get("/cart", headers=shop.customer).json()["items"][0]["quantity"] == 3
