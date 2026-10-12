from datetime import datetime, timedelta, timezone


def test_list_shows_only_active_products(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_product(seller_id, category_id, name="Visible")
    create_product(seller_id, category_id, name="Hidden", is_active=False)

    response = client.get("/products")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["name"] for item in response.json()["items"]] == ["Visible"]


def test_list_is_newest_first(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    now = datetime.now(timezone.utc)
    create_product(seller_id, category_id, name="Oldest", created_at=now - timedelta(days=2))
    create_product(seller_id, category_id, name="Newest", created_at=now)
    create_product(seller_id, category_id, name="Middle", created_at=now - timedelta(days=1))

    response = client.get("/products")

    names = [item["name"] for item in response.json()["items"]]
    assert names == ["Newest", "Middle", "Oldest"]


def test_pagination(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    for number in range(5):
        create_product(seller_id, category_id, name=f"Product {number}")

    page_one = client.get("/products?page=1&page_size=2").json()
    page_three = client.get("/products?page=3&page_size=2").json()
    page_four = client.get("/products?page=4&page_size=2").json()

    assert page_one["total"] == 5
    assert page_one["page"] == 1
    assert page_one["page_size"] == 2
    assert len(page_one["items"]) == 2
    assert len(page_three["items"]) == 1
    assert page_four["items"] == []
    assert page_four["total"] == 5

    # Invalid values are rejected
    assert client.get("/products?page=0").status_code == 422
    assert client.get("/products?page_size=101").status_code == 422


def test_category_filter(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    books = create_category("Books")
    toys = create_category("Toys")
    create_product(seller_id, books, name="A book")
    create_product(seller_id, toys, name="A toy")

    response = client.get("/products?category=books")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "A book"


def test_unknown_category_slug_returns_404(client):
    response = client.get("/products?category=nope")

    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_detail_shape_and_no_seller_email(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    product_id = create_product(seller_id, category_id, name="A book", price=49900)

    response = client.get(f"/products/{product_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["price"] == 49900
    assert body["category"] == {"id": category_id, "name": "Books", "slug": "books"}
    assert body["seller"] == {"id": seller_id, "full_name": "Test seller"}
    assert "seller@example.com" not in response.text


def test_detail_returns_404_for_missing_and_inactive(
    client, create_user, create_category, create_product
):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    inactive_id = create_product(seller_id, category_id, is_active=False)

    assert client.get("/products/999").status_code == 404
    assert client.get(f"/products/{inactive_id}").status_code == 404
