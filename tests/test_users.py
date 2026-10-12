def make_address_body(city="Pune", is_default=False):
    # A complete, valid address body
    return {
        "full_name": "Test Person",
        "phone": "9876543210",
        "line1": "12 Main Road",
        "city": city,
        "state": "Maharashtra",
        "postal_code": "411001",
        "is_default": is_default,
    }


def test_read_and_update_profile(client, create_user, auth_headers):
    create_user("me@example.com", role="seller")
    headers = auth_headers("me@example.com")

    profile = client.get("/users/me", headers=headers).json()
    assert profile["email"] == "me@example.com"
    assert profile["role"] == "seller"
    assert "password_hash" not in profile

    # Only the name changes, even if other fields are sent
    response = client.patch(
        "/users/me", headers=headers, json={"full_name": "New Name", "role": "admin"}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"
    assert response.json()["role"] == "seller"
    assert client.get("/users/me", headers=headers).json()["full_name"] == "New Name"


def test_address_create_list_update_delete(client, create_user, auth_headers):
    create_user("a@example.com")
    headers = auth_headers("a@example.com")

    # Create
    created = client.post("/users/me/addresses", headers=headers, json=make_address_body())
    assert created.status_code == 201
    address_id = created.json()["id"]

    # List
    listed = client.get("/users/me/addresses", headers=headers).json()
    assert [address["id"] for address in listed] == [address_id]

    # Update
    updated = client.put(
        f"/users/me/addresses/{address_id}", headers=headers, json=make_address_body(city="Delhi")
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Delhi"

    # Delete
    deleted = client.delete(f"/users/me/addresses/{address_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/users/me/addresses", headers=headers).json() == []


def test_first_address_is_default(client, create_user, auth_headers):
    create_user("a@example.com")
    headers = auth_headers("a@example.com")

    # The first address is the default even though is_default was false
    first = client.post("/users/me/addresses", headers=headers, json=make_address_body())
    second = client.post("/users/me/addresses", headers=headers, json=make_address_body())

    assert first.json()["is_default"] is True
    assert second.json()["is_default"] is False


def test_new_default_clears_the_old_default(client, create_user, auth_headers):
    create_user("a@example.com")
    headers = auth_headers("a@example.com")
    first = client.post("/users/me/addresses", headers=headers, json=make_address_body()).json()

    # Creating a new default address
    second = client.post(
        "/users/me/addresses", headers=headers, json=make_address_body(is_default=True)
    ).json()
    addresses = {a["id"]: a for a in client.get("/users/me/addresses", headers=headers).json()}
    assert addresses[first["id"]]["is_default"] is False
    assert addresses[second["id"]]["is_default"] is True

    # Updating the first address to be the default again
    client.put(
        f"/users/me/addresses/{first['id']}", headers=headers, json=make_address_body(is_default=True)
    )
    addresses = {a["id"]: a for a in client.get("/users/me/addresses", headers=headers).json()}
    assert addresses[first["id"]]["is_default"] is True
    assert addresses[second["id"]]["is_default"] is False


def test_deleting_the_default_does_not_promote_another(client, create_user, auth_headers):
    create_user("a@example.com")
    headers = auth_headers("a@example.com")
    first = client.post("/users/me/addresses", headers=headers, json=make_address_body()).json()
    client.post("/users/me/addresses", headers=headers, json=make_address_body())

    client.delete(f"/users/me/addresses/{first['id']}", headers=headers)

    remaining = client.get("/users/me/addresses", headers=headers).json()
    assert len(remaining) == 1
    assert remaining[0]["is_default"] is False


def test_other_users_address_gives_404(client, create_user, auth_headers):
    create_user("owner@example.com")
    create_user("other@example.com")
    owner_headers = auth_headers("owner@example.com")
    other_headers = auth_headers("other@example.com")
    address_id = client.post(
        "/users/me/addresses", headers=owner_headers, json=make_address_body()
    ).json()["id"]

    # The second user cannot update or delete it, and it is not in their list
    update = client.put(
        f"/users/me/addresses/{address_id}", headers=other_headers, json=make_address_body()
    )
    delete = client.delete(f"/users/me/addresses/{address_id}", headers=other_headers)
    listed = client.get("/users/me/addresses", headers=other_headers)

    assert update.status_code == 404
    assert delete.status_code == 404
    assert listed.json() == []

    # The owner's address is untouched
    assert len(client.get("/users/me/addresses", headers=owner_headers).json()) == 1
