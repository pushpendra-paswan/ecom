def test_public_list_has_product_count_of_active_products_only(
    client, create_user, create_category, create_product
):
    seller_id = create_user("seller@example.com", role="seller")
    books = create_category("Books")
    toys = create_category("Toys")
    create_category("Empty")
    create_product(seller_id, books, name="Active book 1")
    create_product(seller_id, books, name="Active book 2")
    create_product(seller_id, books, name="Inactive book", is_active=False)
    create_product(seller_id, toys, name="Only inactive toy", is_active=False)

    # No token is needed
    response = client.get("/categories")

    assert response.status_code == 200
    counts = {item["name"]: item["product_count"] for item in response.json()}
    assert counts == {"Books": 2, "Empty": 0, "Toys": 0}
    # Sorted by name
    assert [item["name"] for item in response.json()] == ["Books", "Empty", "Toys"]
    assert set(response.json()[0]) == {"id", "name", "slug", "description", "product_count"}


def test_admin_can_create_rename_and_delete(client, create_user, auth_headers):
    create_user("admin@example.com", role="admin")
    headers = auth_headers("admin@example.com")

    # Create
    created = client.post(
        "/categories", json={"name": "  Garden  ", "description": "Plants"}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Garden"
    assert created.json()["slug"] == "garden"
    category_id = created.json()["id"]

    # Rename (the slug follows the name)
    renamed = client.put(
        f"/categories/{category_id}", json={"name": "Home Garden"}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["slug"] == "home-garden"
    assert renamed.json()["description"] is None

    # Delete
    deleted = client.delete(f"/categories/{category_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/categories").json() == []


def test_slug_is_generated_from_the_name(client, create_user, auth_headers):
    create_user("admin@example.com", role="admin")
    headers = auth_headers("admin@example.com")

    names_and_slugs = {
        "Home & Kitchen": "home-kitchen",
        "Toys_and   Games": "toys-and-games",
        "Beauty (Care) 2024!": "beauty-care-2024",
    }
    for name, expected_slug in names_and_slugs.items():
        response = client.post("/categories", json={"name": name}, headers=headers)
        assert response.status_code == 201
        assert response.json()["slug"] == expected_slug


def test_duplicate_name_or_slug_returns_409(client, create_user, auth_headers):
    create_user("admin@example.com", role="admin")
    headers = auth_headers("admin@example.com")
    client.post("/categories", json={"name": "Books"}, headers=headers)
    other = client.post("/categories", json={"name": "Toys"}, headers=headers).json()

    # Same name
    same_name = client.post("/categories", json={"name": "Books"}, headers=headers)
    assert same_name.status_code == 409

    # Different name, same slug
    same_slug = client.post("/categories", json={"name": "books!"}, headers=headers)
    assert same_slug.status_code == 409

    # Renaming to an existing name
    rename = client.put(f"/categories/{other['id']}", json={"name": "Books"}, headers=headers)
    assert rename.status_code == 409


def test_name_without_letters_or_digits_returns_422(client, create_user, auth_headers):
    create_user("admin@example.com", role="admin")
    headers = auth_headers("admin@example.com")

    response = client.post("/categories", json={"name": "!!!"}, headers=headers)

    assert response.status_code == 422


def test_missing_category_returns_404(client, create_user, auth_headers):
    create_user("admin@example.com", role="admin")
    headers = auth_headers("admin@example.com")

    assert client.put("/categories/999", json={"name": "X"}, headers=headers).status_code == 404
    assert client.delete("/categories/999", headers=headers).status_code == 404


def test_cannot_delete_category_with_products_even_inactive(
    client, create_user, create_category, create_product, auth_headers
):
    seller_id = create_user("seller@example.com", role="seller")
    create_user("admin@example.com", role="admin")
    category_id = create_category("Books")
    create_product(seller_id, category_id, is_active=False)

    response = client.delete(
        f"/categories/{category_id}", headers=auth_headers("admin@example.com")
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Category has products"


def test_write_endpoints_need_an_admin(client, create_user, create_category, auth_headers):
    create_user("customer@example.com", role="customer")
    create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    body = {"name": "New name"}

    # No token: 401
    assert client.post("/categories", json=body).status_code == 401
    assert client.put(f"/categories/{category_id}", json=body).status_code == 401
    assert client.delete(f"/categories/{category_id}").status_code == 401

    # Customer and seller: 403
    for email in ("customer@example.com", "seller@example.com"):
        headers = auth_headers(email)
        assert client.post("/categories", json=body, headers=headers).status_code == 403
        assert client.put(f"/categories/{category_id}", json=body, headers=headers).status_code == 403
        assert client.delete(f"/categories/{category_id}", headers=headers).status_code == 403
