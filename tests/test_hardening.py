import os
from unittest.mock import patch

import bcrypt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app
from app.services.checkout_service import MAX_ORDER_TOTAL
from tests.conftest import make_event

SECURITY_HEADER_NAMES = ["x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy"]

VALID_ADDRESS = {
    "full_name": "Test User",
    "phone": "9876543210",
    "line1": "1 Test Road",
    "city": "Pune",
    "state": "Maharashtra",
    "postal_code": "411001",
}


@pytest.fixture
def people(create_user, auth_headers, create_category):
    # A customer, a seller, an admin (all logged in) and one category
    create_user("customer@example.com", role="customer")
    create_user("seller@example.com", role="seller")
    create_user("admin@example.com", role="admin")
    return {
        "customer": auth_headers("customer@example.com"),
        "seller": auth_headers("seller@example.com"),
        "admin": auth_headers("admin@example.com"),
        "category_id": create_category("Books"),
    }


# ---------- security headers and the body size limit ----------


@pytest.mark.parametrize("path", ["/", "/products", "/does-not-exist.html", "/static/css/style.css"])
def test_security_headers_and_csp_are_on_pages_api_responses_and_404s(client, path):
    response = client.get(path)
    for header_name in SECURITY_HEADER_NAMES:
        assert header_name in response.headers, header_name
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "strict-transport-security" not in response.headers


def test_csp_is_missing_on_the_docs_but_the_docs_still_load(client):
    for path in ["/docs", "/redoc", "/openapi.json"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "content-security-policy" not in response.headers, path
        # The other headers are still there
        assert response.headers["x-content-type-options"] == "nosniff"


def test_a_big_content_length_is_refused_with_413(client):
    response = client.post("/auth/login", content=b"x" * 1_000_001, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_name_of_one_megabyte_is_never_a_500(client):
    body = {"email": "big@example.com", "password": "Password@123", "full_name": "a" * 1_000_000}
    response = client.post("/auth/register", json=body)
    assert response.status_code in (413, 422)


# ---------- unexpected errors ----------


def test_an_unexpected_error_gives_a_plain_500_without_details(client, caplog):
    # Add a route that fails, and always remove it again
    def broken_route():
        raise RuntimeError("secret detail: SELECT * FROM users at /app/secret/path.py")

    app.add_api_route("/broken-route-for-the-test", broken_route)
    # (new routes land after the "/" frontend mount, which would answer 404 first, so move it to the front)
    app.router.routes.insert(0, app.router.routes.pop())
    try:
        quiet_client = TestClient(app, raise_server_exceptions=False)
        response = quiet_client.get("/broken-route-for-the-test")
    finally:
        app.router.routes[:] = [
            route for route in app.router.routes if getattr(route, "path", None) != "/broken-route-for-the-test"
        ]
        app.openapi_schema = None

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    for secret_text in ["secret detail", "SELECT", "Traceback", "RuntimeError", ".py"]:
        assert secret_text not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"

    # The details went to the log only
    assert "secret detail" in caplog.text


def test_a_failed_request_does_not_leak_a_database_connection(client, test_engine, people):
    # A NUL character makes the database refuse the value (an error in the middle of the request)
    response = client.post("/users/me/addresses", json=dict(VALID_ADDRESS, line1="a\x00b"), headers=people["customer"])
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid input"}

    # No connection stays checked out of the pool, and the app still works
    assert test_engine.pool.checkedout() == 0
    assert client.get("/users/me", headers=people["customer"]).status_code == 200


# ---------- odd input never gives a 500 ----------


def test_nul_character_is_a_clean_4xx_everywhere(client, people):
    nul = "a\x00b"
    responses = {
        "register name": client.post(
            "/auth/register", json={"email": "nul@example.com", "password": "Password@123", "full_name": nul}
        ),
        "register email": client.post(
            "/auth/register", json={"email": nul + "@example.com", "password": "Password@123", "full_name": "Nul"}
        ),
        "register password": client.post(
            "/auth/register", json={"email": "nul2@example.com", "password": "Pass\x00word@123", "full_name": "Nul"}
        ),
        "login email": client.post("/auth/login", json={"email": nul, "password": "Password@123"}),
        "profile name": client.patch("/users/me", json={"full_name": nul}, headers=people["customer"]),
        "address line": client.post("/users/me/addresses", json=dict(VALID_ADDRESS, line1=nul), headers=people["customer"]),
        "address city": client.post("/users/me/addresses", json=dict(VALID_ADDRESS, city=nul), headers=people["customer"]),
        "product name": client.post(
            "/products",
            json={"name": nul, "description": "d", "price": 100, "stock": 1, "category_id": people["category_id"]},
            headers=people["seller"],
        ),
        "product description": client.post(
            "/products",
            json={"name": "n", "description": nul, "price": 100, "stock": 1, "category_id": people["category_id"]},
            headers=people["seller"],
        ),
        "category name": client.post("/categories", json={"name": nul}, headers=people["admin"]),
        "category description": client.post(
            "/categories", json={"name": "Fine", "description": nul}, headers=people["admin"]
        ),
        "category filter": client.get("/products?category=%00"),
    }
    for name, response in responses.items():
        assert 400 <= response.status_code < 500, name + " gave " + str(response.status_code)

    # A search with a NUL character is a normal (empty) result
    search = client.get("/products?q=%00")
    assert search.status_code == 200
    assert search.json()["items"] == []
    assert client.get("/products?q=ab%00cd").status_code == 200


def test_huge_numbers_are_a_clean_422(client, people):
    huge = 99999999999
    responses = {
        "product id": client.get("/products/" + str(huge)),
        "product id (seller)": client.get("/seller/products/" + str(huge), headers=people["seller"]),
        "product patch": client.patch("/products/" + str(huge), json={"name": "x"}, headers=people["seller"]),
        "product delete": client.delete("/products/" + str(huge), headers=people["seller"]),
        "category put": client.put("/categories/" + str(huge), json={"name": "x"}, headers=people["admin"]),
        "category delete": client.delete("/categories/" + str(huge), headers=people["admin"]),
        "address put": client.put("/users/me/addresses/" + str(huge), json=VALID_ADDRESS, headers=people["customer"]),
        "address delete": client.delete("/users/me/addresses/" + str(huge), headers=people["customer"]),
        "order id": client.get("/orders/" + str(huge), headers=people["customer"]),
        "order cancel": client.post("/orders/" + str(huge) + "/cancel", headers=people["customer"]),
        "seller order": client.get("/seller/orders/" + str(huge), headers=people["seller"]),
        "admin order": client.get("/admin/orders/" + str(huge), headers=people["admin"]),
        "cart product id": client.post("/cart/items", json={"product_id": huge, "quantity": 1}, headers=people["customer"]),
        "cart quantity": client.post("/cart/items", json={"product_id": 1, "quantity": huge}, headers=people["customer"]),
        "cart patch": client.patch("/cart/items/" + str(huge), json={"quantity": 1}, headers=people["customer"]),
        "checkout address": client.post("/orders/checkout", json={"address_id": huge}, headers=people["customer"]),
        "page": client.get("/products?page=" + str(huge)),
        "orders page": client.get("/orders?page=" + str(huge), headers=people["customer"]),
        "admin users page": client.get("/admin/users?page=" + str(huge), headers=people["admin"]),
        "page size": client.get("/products?page_size=" + str(huge)),
        "min price": client.get("/products?min_price=" + str(huge)),
        "max price": client.get("/products?max_price=" + str(huge)),
        "price": client.post(
            "/products",
            json={"name": "n", "description": "d", "price": huge, "stock": 1, "category_id": people["category_id"]},
            headers=people["seller"],
        ),
        "category id in product": client.post(
            "/products",
            json={"name": "n", "description": "d", "price": 100, "stock": 1, "category_id": huge},
            headers=people["seller"],
        ),
    }
    for name, response in responses.items():
        assert response.status_code == 422, name + " gave " + str(response.status_code)


def test_the_price_and_stock_caps(client, people):
    base = {"name": "Capped", "description": "d", "category_id": people["category_id"]}

    # Exactly at the cap is fine, one above is a 422
    at_cap = client.post("/products", json=dict(base, price=10_000_000, stock=1_000_000), headers=people["seller"])
    assert at_cap.status_code == 201
    assert client.post("/products", json=dict(base, price=10_000_001, stock=1), headers=people["seller"]).status_code == 422
    assert client.post("/products", json=dict(base, price=100, stock=1_000_001), headers=people["seller"]).status_code == 422

    # The same caps apply when a product is edited
    product_id = at_cap.json()["id"]
    assert client.patch("/products/" + str(product_id), json={"price": 10_000_001}, headers=people["seller"]).status_code == 422
    assert client.patch("/products/" + str(product_id), json={"stock": 1_000_001}, headers=people["seller"]).status_code == 422

    # The price filter caps
    assert client.get("/products?max_price=1000000000").status_code == 200
    assert client.get("/products?max_price=1000000001").status_code == 422
    assert client.get("/products?page=100000").status_code == 200
    assert client.get("/products?page=100001").status_code == 422


def test_very_long_strings_are_a_clean_422(client, people):
    long_text = "a" * 100_000
    responses = {
        "register name": client.post(
            "/auth/register", json={"email": "long@example.com", "password": "Password@123", "full_name": long_text}
        ),
        "register email": client.post(
            "/auth/register", json={"email": long_text + "@example.com", "password": "Password@123", "full_name": "Long"}
        ),
        "register password": client.post(
            "/auth/register", json={"email": "long@example.com", "password": long_text, "full_name": "Long"}
        ),
        "login email": client.post("/auth/login", json={"email": long_text, "password": "Password@123"}),
        "login password": client.post("/auth/login", json={"email": "customer@example.com", "password": long_text}),
        "profile name": client.patch("/users/me", json={"full_name": long_text}, headers=people["customer"]),
        "address line": client.post("/users/me/addresses", json=dict(VALID_ADDRESS, line1=long_text), headers=people["customer"]),
        "address phone": client.post("/users/me/addresses", json=dict(VALID_ADDRESS, phone="1" * 21), headers=people["customer"]),
        "address postal code": client.post(
            "/users/me/addresses", json=dict(VALID_ADDRESS, postal_code="1" * 13), headers=people["customer"]
        ),
        "product name": client.post(
            "/products",
            json={"name": long_text, "description": "d", "price": 100, "stock": 1, "category_id": people["category_id"]},
            headers=people["seller"],
        ),
        "product description": client.post(
            "/products",
            json={"name": "n", "description": long_text, "price": 100, "stock": 1, "category_id": people["category_id"]},
            headers=people["seller"],
        ),
        "category name": client.post("/categories", json={"name": long_text}, headers=people["admin"]),
        "category description": client.post(
            "/categories", json={"name": "Fine", "description": long_text}, headers=people["admin"]
        ),
        # (a URL has a length limit of its own, so the query strings use 10,000 characters)
        "search": client.get("/products?q=" + "a" * 10_000),
        "category filter": client.get("/products?category=" + "a" * 10_000),
    }
    for name, response in responses.items():
        assert response.status_code == 422, name + " gave " + str(response.status_code)

    # The boundaries themselves are accepted
    assert client.patch("/users/me", json={"full_name": "a" * 200}, headers=people["customer"]).status_code == 200
    assert client.patch("/users/me", json={"full_name": "a" * 201}, headers=people["customer"]).status_code == 422


def test_emoji_and_right_to_left_text_are_stored_and_returned(client, people):
    emoji_name = "Café ☕ 😀 naïve 日本語"
    arabic_name = "مرحبا بالعالم עברית"

    # A product name, a category name and an address line round-trip unchanged
    product = client.post(
        "/products",
        json={"name": emoji_name, "description": arabic_name, "price": 100, "stock": 1, "category_id": people["category_id"]},
        headers=people["seller"],
    )
    assert product.status_code == 201
    shown = client.get("/products/" + str(product.json()["id"])).json()
    assert shown["name"] == emoji_name
    assert shown["description"] == arabic_name

    category = client.post("/categories", json={"name": arabic_name + " Shop 😀"}, headers=people["admin"])
    assert category.status_code == 201
    assert category.json()["name"] == arabic_name + " Shop 😀"

    address = client.post(
        "/users/me/addresses", json=dict(VALID_ADDRESS, line1=emoji_name, full_name=arabic_name), headers=people["customer"]
    )
    assert address.status_code == 201
    saved = client.get("/users/me/addresses", headers=people["customer"]).json()[0]
    assert saved["line1"] == emoji_name
    assert saved["full_name"] == arabic_name

    # A search for these words is a normal result
    assert client.get("/products?q=" + "😀").status_code == 200
    assert client.get("/products?q=" + arabic_name).status_code == 200


def test_wrong_types_are_a_422(client, people):
    customer = people["customer"]
    seller = people["seller"]
    category_id = people["category_id"]
    for wrong_value in ["ten", [1], None, {"a": 1}]:
        assert client.post("/cart/items", json={"product_id": wrong_value, "quantity": 1}, headers=customer).status_code == 422
        assert client.post("/cart/items", json={"product_id": 1, "quantity": wrong_value}, headers=customer).status_code == 422
        assert client.post("/orders/checkout", json={"address_id": wrong_value}, headers=customer).status_code == 422
        product = {"name": "n", "description": "d", "price": wrong_value, "stock": 1, "category_id": category_id}
        assert client.post("/products", json=product, headers=seller).status_code == 422
        product = {"name": "n", "description": "d", "price": 100, "stock": wrong_value, "category_id": category_id}
        assert client.post("/products", json=product, headers=seller).status_code == 422

    # A text value where a number is expected in the query string
    assert client.get("/products?page=abc").status_code == 422
    assert client.get("/products?min_price=1.5").status_code == 422
    assert client.get("/products?in_stock=maybe").status_code == 422
    assert client.get("/products/abc").status_code == 422

    # A body that is not JSON, or JSON of the wrong shape
    assert client.post("/auth/login", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/auth/login", json=["a", "list"]).status_code == 422
    assert client.post("/auth/login", json={"email": None, "password": None}).status_code == 422


# ---------- login timing, settings, CORS ----------


def test_login_with_an_unknown_email_still_does_one_bcrypt_check(client, create_user):
    create_user("real@example.com")
    real_checkpw = bcrypt.checkpw
    calls = []

    def counting_checkpw(password, hashed):
        calls.append(1)
        return real_checkpw(password, hashed)

    # Wrong password for a real account
    with patch("bcrypt.checkpw", side_effect=counting_checkpw):
        wrong_password = client.post("/auth/login", json={"email": "real@example.com", "password": "Wrong@12345"})
    assert wrong_password.status_code == 401
    calls_for_wrong_password = len(calls)

    # Unknown email
    calls.clear()
    with patch("bcrypt.checkpw", side_effect=counting_checkpw):
        unknown_email = client.post("/auth/login", json={"email": "nobody@example.com", "password": "Wrong@12345"})
    assert unknown_email.status_code == 401
    calls_for_unknown_email = len(calls)

    # Same number of checks and the same message
    assert calls_for_wrong_password == 1
    assert calls_for_unknown_email == calls_for_wrong_password
    assert unknown_email.json() == wrong_password.json()


def test_a_weak_jwt_secret_is_refused():
    # The env file is passed as None so the test never reads the real .env
    with pytest.raises(ValidationError):
        Settings(_env_file=None, JWT_SECRET="short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, JWT_SECRET="")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, JWT_SECRET="x" * 31)
    assert Settings(_env_file=None, JWT_SECRET="x" * 32).JWT_SECRET == "x" * 32

    # A missing secret is refused too (the variable is removed for this check)
    with patch.dict(os.environ):
        os.environ.pop("JWT_SECRET", None)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


def test_there_is_no_cors(client):
    # A request from another origin gets no permission headers
    response = client.get("/products", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

    # A preflight request is not answered with permission either
    preflight = client.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in preflight.headers
    assert "access-control-allow-methods" not in preflight.headers


# ---------- checkout total cap and the webhook order id ----------


def test_checkout_refuses_a_total_above_the_cap_and_changes_nothing(client, store, query_database, read_stock):
    # A product at the maximum price, ten of them: 100,000,000 paise, one more than Stripe accepts
    product_id = store.product(stock=20, price=10_000_000)
    address_id = client.post("/users/me/addresses", json=VALID_ADDRESS, headers=store.customer).json()["id"]
    assert client.post("/cart/items", json={"product_id": product_id, "quantity": 10}, headers=store.customer).status_code == 200
    assert 10 * 10_000_000 > MAX_ORDER_TOTAL

    response = client.post("/orders/checkout", json={"address_id": address_id}, headers=store.customer)
    assert response.status_code == 409
    assert "Order total is too large" in response.json()["detail"]

    # No order, no payment, the stock is unchanged and the cart still has its line
    assert query_database("SELECT count(*) AS total FROM orders") == [{"total": 0}]
    assert query_database("SELECT count(*) AS total FROM payments") == [{"total": 0}]
    assert read_stock(product_id) == 20
    assert query_database("SELECT quantity FROM cart_items") == [{"quantity": 10}]

    # Nine of them (90,000,000) is fine
    assert client.patch("/cart/items/" + str(product_id), json={"quantity": 9}, headers=store.customer).status_code == 200
    assert client.post("/orders/checkout", json={"address_id": address_id}, headers=store.customer).status_code == 201


def test_webhook_with_a_huge_order_id_in_the_metadata_changes_nothing(store, post_webhook, read_order):
    order = store.place_order([(store.product(stock=5), 1)])

    # An unknown session id and an order id with 20 digits: acknowledged with 200, nothing happens
    event = make_event(
        "checkout.session.completed",
        "cs_test_unknown_session",
        order,
        metadata={"order_id": "99999999999999999999"},
    )
    assert post_webhook(event).status_code == 200
    assert read_order(order.id)["order_status"] == "pending_payment"
    assert read_order(order.id)["payment_status"] == "pending"
