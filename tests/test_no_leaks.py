import pytest

from app.core.config import settings
from tests.test_endpoint_security import ALLOWED_ROLES, ENDPOINTS

# Real-looking Stripe ids that are put into the payment row. None of them may ever appear in a response.
SESSION_ID = "cs_test_a1B2c3D4e5F6g7H8i9J0kLmNoP"
PAYMENT_INTENT_ID = "pi_3NxYz0123456789ABCDEFghij"
REFUND_ID = "re_3NxYz0123456789ABCDEFklmn"

CUSTOMER_EMAIL = "customer-private@example.com"
OTHER_CUSTOMER_EMAIL = "other-customer@example.com"

ADDRESS = {
    "full_name": "Private Customer",
    "phone": "9876543210",
    "line1": "1 Private Road",
    "city": "Pune",
    "state": "Maharashtra",
    "postal_code": "411001",
}


@pytest.fixture
def scenario(client, create_user, create_category, create_product, auth_headers, stripe_create, pay, change_database):
    # Two sellers, a customer, another customer and an admin
    seller_one = create_user("seller-one@example.com", role="seller")
    seller_two = create_user("seller-two@example.com", role="seller")
    create_user(CUSTOMER_EMAIL)
    create_user(OTHER_CUSTOMER_EMAIL)
    create_user("admin@example.com", role="admin")
    headers = {
        "customer": auth_headers(CUSTOMER_EMAIL),
        "other_customer": auth_headers(OTHER_CUSTOMER_EMAIL),
        "seller": auth_headers("seller-one@example.com"),
        "seller_two": auth_headers("seller-two@example.com"),
        "admin": auth_headers("admin@example.com"),
    }

    # One product for each seller
    category_id = create_category("Books")
    product_one = create_product(seller_one, category_id, name="Product One")
    product_two = create_product(seller_two, category_id, name="Product Two")

    # The customer has an address, and one product in the cart
    address_id = client.post("/users/me/addresses", json=ADDRESS, headers=headers["customer"]).json()["id"]
    for product_id in [product_one, product_two]:
        client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers["customer"])
    response = client.post("/orders/checkout", json={"address_id": address_id}, headers=headers["customer"])
    order_id = response.json()["order_id"]

    # The order is paid through the signed webhook, then the payment row gets real-looking Stripe ids
    class Order:
        id = order_id
        total_amount = response.json()["total_amount"]
        session_id = "cs_test_order-" + str(order_id)

    pay(Order)
    change_database(
        "UPDATE payments SET stripe_checkout_session_id = :session, stripe_payment_intent_id = :intent,"
        " stripe_refund_id = :refund WHERE order_id = :order_id",
        session=SESSION_ID,
        intent=PAYMENT_INTENT_ID,
        refund=REFUND_ID,
        order_id=order_id,
    )

    # The customer keeps one product in the cart so the cart response has a line
    client.post("/cart/items", json={"product_id": product_one, "quantity": 1}, headers=headers["customer"])

    return {
        "headers": headers,
        "order_id": order_id,
        "product_id": product_one,
        "address_id": address_id,
    }


def test_no_response_contains_a_secret(client, scenario):
    forbidden_texts = [
        "password_hash",
        "stripe_checkout_session_id",
        "stripe_payment_intent_id",
        "stripe_refund_id",
        SESSION_ID,
        PAYMENT_INTENT_ID,
        REFUND_ID,
        "$2b$",
        settings.JWT_SECRET,
    ]

    # Which header sets to use for each role (public endpoints are also called without a token)
    role_headers = {
        "customer": scenario["headers"]["customer"],
        "seller": scenario["headers"]["seller"],
        "admin": scenario["headers"]["admin"],
    }

    calls_made = 0
    problems = []
    for method, path, access in ENDPOINTS:
        if method != "GET":
            continue
        url = (
            path.replace("{order_id}", str(scenario["order_id"]))
            .replace("{product_id}", str(scenario["product_id"]))
        )

        # Every way of calling this endpoint that its rule allows
        callers = []
        if access == "public":
            callers.append(("anonymous", None))
        for role, role_header in role_headers.items():
            if access == "public" or role in ALLOWED_ROLES[access]:
                callers.append((role, role_header))

        for caller, caller_headers in callers:
            response = client.get(url, headers=caller_headers)
            calls_made = calls_made + 1
            assert response.status_code == 200, (url, caller, response.status_code)
            for forbidden_text in forbidden_texts:
                if forbidden_text in response.text:
                    problems.append((url, caller, forbidden_text))
    assert calls_made > 20
    assert problems == []


def test_customer_email_stays_private(client, scenario):
    # The customer's email may appear in /users/me and in admin responses, nowhere else
    allowed_places = [
        ("customer", "/users/me"),
        ("admin", "/admin/users"),
        ("admin", "/admin/orders"),
        ("admin", "/admin/orders/" + str(scenario["order_id"])),
    ]
    order_url = str(scenario["order_id"])
    urls_to_check = [
        "/users/me",
        "/users/me/addresses",
        "/categories",
        "/products",
        "/products/" + str(scenario["product_id"]),
        "/seller/products",
        "/seller/products/" + str(scenario["product_id"]),
        "/seller/orders",
        "/seller/orders/" + order_url,
        "/cart",
        "/cart/count",
        "/orders",
        "/orders/" + order_url,
        "/admin/users",
        "/admin/orders",
        "/admin/orders/" + order_url,
        "/health",
    ]

    # Anonymous visitors, the other customer, both sellers and the customer themself
    for caller in ["anonymous", "other_customer", "seller", "seller_two", "customer", "admin"]:
        caller_headers = scenario["headers"].get(caller)
        for url in urls_to_check:
            response = client.get(url, headers=caller_headers)
            if response.status_code != 200:
                continue
            if CUSTOMER_EMAIL in response.text:
                assert (caller, url) in allowed_places, (caller, url)


def test_the_scenario_really_shows_the_data(client, scenario):
    # A safety check for the tests above: the customer's own pages do show the order, and the seller
    # sees the order too, so the tests above are not passing just because everything is empty
    order_url = "/orders/" + str(scenario["order_id"])
    assert client.get(order_url, headers=scenario["headers"]["customer"]).json()["payment"]["status"] == "succeeded"
    seller_orders = client.get("/seller/orders", headers=scenario["headers"]["seller"]).json()
    assert seller_orders["total"] == 1
    admin_order = client.get("/admin/orders/" + str(scenario["order_id"]), headers=scenario["headers"]["admin"]).json()
    assert admin_order["customer_email"] == CUSTOMER_EMAIL
    assert client.get("/cart", headers=scenario["headers"]["customer"]).json()["item_count"] == 1
