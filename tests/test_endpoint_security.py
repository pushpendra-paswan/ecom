from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.routing import APIRoute

from app.core.config import settings
from app.main import app

# The access rule of EVERY endpoint. Adding an endpoint without adding it here fails the first test,
# so nobody can ship an endpoint without deciding who may call it.
#   public            no login
#   signature         no login, the Stripe signature is the security (the webhook)
#   any_user          any logged-in user
#   customer / seller / admin   exactly that role
#   customer_or_admin / seller_or_admin
ENDPOINTS = [
    ("GET", "/health", "public"),
    ("POST", "/auth/register", "public"),
    ("POST", "/auth/login", "public"),
    ("GET", "/users/me", "any_user"),
    ("PATCH", "/users/me", "any_user"),
    ("GET", "/users/me/addresses", "any_user"),
    ("POST", "/users/me/addresses", "any_user"),
    ("PUT", "/users/me/addresses/{address_id}", "any_user"),
    ("DELETE", "/users/me/addresses/{address_id}", "any_user"),
    ("GET", "/admin/users", "admin"),
    ("GET", "/admin/orders", "admin"),
    ("GET", "/admin/orders/{order_id}", "admin"),
    ("PATCH", "/admin/orders/{order_id}/status", "admin"),
    ("GET", "/categories", "public"),
    ("POST", "/categories", "admin"),
    ("PUT", "/categories/{category_id}", "admin"),
    ("DELETE", "/categories/{category_id}", "admin"),
    ("GET", "/products", "public"),
    ("GET", "/products/{product_id}", "public"),
    ("POST", "/products", "seller"),
    ("PATCH", "/products/{product_id}", "seller_or_admin"),
    ("DELETE", "/products/{product_id}", "seller_or_admin"),
    ("GET", "/seller/products", "seller"),
    ("GET", "/seller/products/{product_id}", "seller"),
    ("GET", "/seller/orders", "seller"),
    ("GET", "/seller/orders/{order_id}", "seller"),
    ("PATCH", "/seller/orders/{order_id}/status", "seller"),
    ("GET", "/cart", "customer"),
    ("DELETE", "/cart", "customer"),
    ("GET", "/cart/count", "customer"),
    ("POST", "/cart/items", "customer"),
    ("PATCH", "/cart/items/{product_id}", "customer"),
    ("DELETE", "/cart/items/{product_id}", "customer"),
    ("POST", "/orders/checkout", "customer"),
    ("GET", "/orders", "customer"),
    ("GET", "/orders/{order_id}", "customer"),
    ("POST", "/orders/{order_id}/cancel", "customer_or_admin"),
    ("POST", "/webhooks/stripe", "signature"),
]

# Which roles may call an endpoint with each access rule
ALLOWED_ROLES = {
    "any_user": ["customer", "seller", "admin"],
    "customer": ["customer"],
    "seller": ["seller"],
    "admin": ["admin"],
    "customer_or_admin": ["customer", "admin"],
    "seller_or_admin": ["seller", "admin"],
}

# A minimal valid body for every endpoint that needs one, so request validation (422)
# never hides the access check
VALID_ADDRESS = {
    "full_name": "Test User",
    "phone": "9876543210",
    "line1": "1 Test Road",
    "city": "Pune",
    "state": "Maharashtra",
    "postal_code": "411001",
}
BODIES = {
    ("PATCH", "/users/me"): {"full_name": "New Name"},
    ("POST", "/users/me/addresses"): VALID_ADDRESS,
    ("PUT", "/users/me/addresses/{address_id}"): VALID_ADDRESS,
    ("PATCH", "/admin/orders/{order_id}/status"): {"status": "shipped"},
    ("POST", "/categories"): {"name": "Some Category"},
    ("PUT", "/categories/{category_id}"): {"name": "Some Category"},
    ("POST", "/products"): {
        "name": "Some product",
        "description": "Some description",
        "price": 1000,
        "stock": 5,
        "category_id": 1,
    },
    ("PATCH", "/products/{product_id}"): {"name": "New name"},
    ("PATCH", "/seller/orders/{order_id}/status"): {"status": "shipped"},
    ("POST", "/cart/items"): {"product_id": 1, "quantity": 1},
    ("PATCH", "/cart/items/{product_id}"): {"quantity": 1},
    ("POST", "/orders/checkout"): {"address_id": 1},
}

PROTECTED_ENDPOINTS = [endpoint for endpoint in ENDPOINTS if endpoint[2] not in ("public", "signature")]


# Every path id in these tests is 1 (str.format fills in the ones a path has and ignores the others)
PATH_IDS = {"address_id": 1, "order_id": 1, "category_id": 1, "product_id": 1}


def test_inventory_lists_every_endpoint():
    # The real endpoints of the app. FastAPI wraps every included router in a private object, so the
    # routes of the routers are read from the OpenAPI document (it lists every API route), and app.routes
    # is walked for anything else (the docs pages and the static mounts are not API endpoints).
    docs_paths = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]
    real_endpoints = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            real_endpoints.add((method.upper(), path))
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                real_endpoints.add((method, route.path))
        elif type(route).__name__ == "Route" and route.path not in docs_paths:
            # A plain route that is not a documented exception: it needs a decision too
            for method in route.methods:
                if method != "HEAD":
                    real_endpoints.add((method, route.path))

    listed_endpoints = set()
    for method, path, access in ENDPOINTS:
        listed_endpoints.add((method, path))

    # The failure message names the missing and the stale entries
    missing = sorted(real_endpoints - listed_endpoints)
    stale = sorted(listed_endpoints - real_endpoints)
    assert real_endpoints == listed_endpoints, (
        "Endpoints missing from ENDPOINTS (decide their access rule): "
        + str(missing)
        + " | Entries in ENDPOINTS that no longer exist: "
        + str(stale)
    )


def test_access_words_are_known():
    # A typo in the access word must not silently skip the checks
    for method, path, access in ENDPOINTS:
        assert access in list(ALLOWED_ROLES) + ["public", "signature"], method + " " + path


def test_protected_endpoints_need_a_token(client):
    failures = []
    for method, path, access in PROTECTED_ENDPOINTS:
        # No token at all
        response = client.request(method, path.format(**PATH_IDS), json=BODIES.get((method, path)))
        if response.status_code != 401:
            failures.append((method, path, "no token", response.status_code))
        # A garbage token
        response = client.request(
            method,
            path.format(**PATH_IDS),
            json=BODIES.get((method, path)),
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        if response.status_code != 401:
            failures.append((method, path, "garbage token", response.status_code))
    assert failures == []


@pytest.fixture
def role_headers(create_user, auth_headers):
    # One logged-in user of each role
    create_user("customer@example.com", role="customer")
    create_user("seller@example.com", role="seller")
    create_user("admin@example.com", role="admin")
    return {
        "customer": auth_headers("customer@example.com"),
        "seller": auth_headers("seller@example.com"),
        "admin": auth_headers("admin@example.com"),
    }


@pytest.mark.parametrize("method,path,access", PROTECTED_ENDPOINTS)
def test_each_role_gets_the_right_answer(client, role_headers, method, path, access):
    for role in ["customer", "seller", "admin"]:
        response = client.request(
            method, path.format(**PATH_IDS), json=BODIES.get((method, path)), headers=role_headers[role]
        )
        if role in ALLOWED_ROLES[access]:
            # An allowed role passes the access check (it may still get 404, 409 and so on)
            assert response.status_code not in (401, 403), role + " should be allowed: " + response.text
        else:
            assert response.status_code == 403, role + " should be refused: " + str(response.status_code)


def test_deactivated_user_token_is_refused_everywhere(client, create_user, auth_headers, change_database):
    # Log in while the account is active, then deactivate the account
    create_user("gone@example.com", role="customer")
    headers = auth_headers("gone@example.com")
    assert client.get("/users/me", headers=headers).status_code == 200
    change_database("UPDATE users SET is_active = false WHERE email = 'gone@example.com'")

    # The token is still valid, but the user is loaded from the database every time
    failures = []
    for method, path, access in PROTECTED_ENDPOINTS:
        response = client.request(method, path.format(**PATH_IDS), json=BODIES.get((method, path)), headers=headers)
        if response.status_code != 401:
            failures.append((method, path, response.status_code))
    assert failures == []


def test_bad_tokens_are_all_refused_with_the_same_message(client, create_user):
    user_id = create_user("someone@example.com")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    good_payload = {"sub": str(user_id), "exp": expires_at}

    # Each token is wrong in a different way
    bad_tokens = {
        "wrong secret": jwt.encode(good_payload, "x" * 40, algorithm="HS256"),
        "alg none": jwt.encode(good_payload, None, algorithm="none"),
        "no exp": jwt.encode({"sub": str(user_id)}, settings.JWT_SECRET, algorithm="HS256"),
        "expired": jwt.encode(
            {"sub": str(user_id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            settings.JWT_SECRET,
            algorithm="HS256",
        ),
        "non-numeric sub": jwt.encode(
            {"sub": "abc", "exp": expires_at}, settings.JWT_SECRET, algorithm="HS256"
        ),
        "no sub": jwt.encode({"exp": expires_at}, settings.JWT_SECRET, algorithm="HS256"),
        "other algorithm": jwt.encode(good_payload, settings.JWT_SECRET, algorithm="HS512"),
    }

    # The good token works, every bad one gives the same 401
    good_token = jwt.encode(good_payload, settings.JWT_SECRET, algorithm="HS256")
    assert client.get("/users/me", headers={"Authorization": "Bearer " + good_token}).status_code == 200
    for name, token in bad_tokens.items():
        response = client.get("/users/me", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 401, name
        assert response.json() == {"detail": "Not authenticated"}, name
