def new_product_body(category_id, **changes):
    # A valid body for POST /products. Tests change only what they want to test.
    body = {
        "name": "Test product",
        "description": "A nice product",
        "price": 49900,
        "stock": 5,
        "category_id": category_id,
    }
    body.update(changes)
    return body


def test_seller_creates_product_with_own_id(client, create_user, create_category, auth_headers):
    seller_id = create_user("seller@example.com", role="seller")
    other_id = create_user("other@example.com", role="seller")
    category_id = create_category("Books")

    # A seller_id in the body is ignored
    body = new_product_body(category_id, seller_id=other_id, image_url="/static/images/a.png")
    response = client.post("/products", json=body, headers=auth_headers("seller@example.com"))

    assert response.status_code == 201
    assert response.json()["seller"]["id"] == seller_id
    assert response.json()["is_active"] is True
    assert response.json()["image_url"] == "/static/images/a.png"
    assert response.json()["category"]["slug"] == "books"


def test_only_sellers_can_create(client, create_user, create_category, auth_headers):
    create_user("customer@example.com", role="customer")
    create_user("admin@example.com", role="admin")
    category_id = create_category("Books")
    body = new_product_body(category_id)

    assert client.post("/products", json=body).status_code == 401
    customer = client.post("/products", json=body, headers=auth_headers("customer@example.com"))
    admin = client.post("/products", json=body, headers=auth_headers("admin@example.com"))
    assert customer.status_code == 403
    assert admin.status_code == 403


def test_invalid_create_bodies_are_rejected(client, create_user, create_category, auth_headers):
    create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    headers = auth_headers("seller@example.com")

    for changes in (
        {"price": 0},
        {"stock": -1},
        {"image_url": "javascript:alert(1)"},
        {"name": "   "},
    ):
        response = client.post("/products", json=new_product_body(category_id, **changes), headers=headers)
        assert response.status_code == 422

    # A category that does not exist is a 400
    response = client.post("/products", json=new_product_body(999), headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Category does not exist"


def test_seller_can_patch_own_product(client, create_user, create_category, create_product, auth_headers):
    seller_id = create_user("seller@example.com", role="seller")
    books = create_category("Books")
    toys = create_category("Toys")
    product_id = create_product(seller_id, books, name="Old name", price=1000)
    headers = auth_headers("seller@example.com")

    response = client.patch(
        f"/products/{product_id}", json={"name": "New name", "category_id": toys}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New name"
    assert response.json()["category"]["slug"] == "toys"
    # Fields that were not sent stay as they were
    assert response.json()["price"] == 1000

    # Bad values are rejected
    assert client.patch(f"/products/{product_id}", json={"price": 0}, headers=headers).status_code == 422
    assert client.patch(f"/products/{product_id}", json={"name": None}, headers=headers).status_code == 422
    assert client.patch(f"/products/{product_id}", json={"category_id": 999}, headers=headers).status_code == 400


def test_seller_cannot_touch_another_sellers_product(
    client, create_user, create_category, create_product, auth_headers
):
    owner_id = create_user("owner@example.com", role="seller")
    create_user("other@example.com", role="seller")
    category_id = create_category("Books")
    product_id = create_product(owner_id, category_id, name="Mine")
    headers = auth_headers("other@example.com")

    patch = client.patch(f"/products/{product_id}", json={"name": "Stolen"}, headers=headers)
    delete = client.delete(f"/products/{product_id}", headers=headers)

    assert patch.status_code == 404
    assert delete.status_code == 404
    # Nothing changed
    product = client.get(f"/products/{product_id}").json()
    assert product["name"] == "Mine"


def test_customer_gets_403_and_missing_product_404(
    client, create_user, create_category, create_product, auth_headers
):
    seller_id = create_user("seller@example.com", role="seller")
    create_user("customer@example.com", role="customer")
    create_user("admin@example.com", role="admin")
    product_id = create_product(seller_id, create_category("Books"))
    customer = auth_headers("customer@example.com")

    assert client.patch(f"/products/{product_id}", json={"name": "X"}).status_code == 401
    assert client.delete(f"/products/{product_id}").status_code == 401
    assert client.patch(f"/products/{product_id}", json={"name": "X"}, headers=customer).status_code == 403
    assert client.delete(f"/products/{product_id}", headers=customer).status_code == 403
    assert client.get("/seller/products", headers=customer).status_code == 403

    # A product that does not exist
    admin = auth_headers("admin@example.com")
    assert client.patch("/products/999", json={"name": "X"}, headers=admin).status_code == 404
    assert client.delete("/products/999", headers=admin).status_code == 404


def test_admin_can_patch_and_delete_any_product(
    client, create_user, create_category, create_product, auth_headers
):
    seller_id = create_user("seller@example.com", role="seller")
    create_user("admin@example.com", role="admin")
    product_id = create_product(seller_id, create_category("Books"), name="Old name")
    headers = auth_headers("admin@example.com")

    patch = client.patch(f"/products/{product_id}", json={"name": "Admin name"}, headers=headers)
    assert patch.status_code == 200
    # The seller does not change
    assert patch.json()["seller"]["id"] == seller_id
    assert patch.json()["name"] == "Admin name"

    delete = client.delete(f"/products/{product_id}", headers=headers)
    assert delete.status_code == 204
    assert client.get(f"/products/{product_id}").status_code == 404


def test_delete_is_a_soft_delete_and_can_be_undone(
    client, create_user, create_category, create_product, auth_headers
):
    seller_id = create_user("seller@example.com", role="seller")
    product_id = create_product(seller_id, create_category("Books"))
    headers = auth_headers("seller@example.com")

    # Delete (twice is fine)
    assert client.delete(f"/products/{product_id}", headers=headers).status_code == 204
    assert client.delete(f"/products/{product_id}", headers=headers).status_code == 204

    # Hidden from the public, still listed for the seller
    assert client.get("/products").json()["total"] == 0
    own = client.get("/seller/products", headers=headers).json()
    assert own["total"] == 1
    assert own["items"][0]["is_active"] is False

    # Reactivate with PATCH
    patch = client.patch(f"/products/{product_id}", json={"is_active": True}, headers=headers)
    assert patch.status_code == 200
    assert client.get("/products").json()["total"] == 1


def test_seller_products_shows_only_own_products(
    client, create_user, create_category, create_product, auth_headers
):
    first_id = create_user("first@example.com", role="seller")
    second_id = create_user("second@example.com", role="seller")
    category_id = create_category("Books")
    create_product(first_id, category_id, name="First 1")
    create_product(first_id, category_id, name="First 2", is_active=False)
    create_product(second_id, category_id, name="Second 1")

    response = client.get("/seller/products", headers=auth_headers("first@example.com"))

    assert response.status_code == 200
    assert response.json()["total"] == 2
    names = [item["name"] for item in response.json()["items"]]
    assert names == ["First 2", "First 1"]
