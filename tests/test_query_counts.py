import pytest
from sqlalchemy import event


@pytest.fixture
def recorded_statements(test_engine):
    # A list that gets one entry for every SQL statement the test engine sends (while the test runs)
    statements = []

    def remember_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", remember_statement)
    yield statements
    event.remove(test_engine, "before_cursor_execute", remember_statement)


# In each test: the number of statements = the length of the list after the request minus before it.
# A list endpoint must send the same number of statements for 2 rows as for 12 rows (no query per row).


def test_product_list_uses_the_same_number_of_queries_for_few_and_many_rows(
    client, create_user, create_category, create_product, recorded_statements
):
    # Products of different sellers and categories (a query per product would show up here)
    seller_ids = [create_user("seller-1@example.com", role="seller"), create_user("seller-2@example.com", role="seller")]
    category_ids = [create_category("Books"), create_category("Toys"), create_category("Games")]
    for number in range(2):
        create_product(seller_ids[number % 2], category_ids[number % 3], name="Few " + str(number))

    # Two products
    start = len(recorded_statements)
    response = client.get("/products")
    few_rows = len(recorded_statements) - start
    assert response.json()["total"] == 2
    assert few_rows > 0

    # Fourteen products
    for number in range(12):
        create_product(seller_ids[number % 2], category_ids[number % 3], name="Many " + str(number))
    start = len(recorded_statements)
    response = client.get("/products")
    many_rows = len(recorded_statements) - start
    assert response.json()["total"] == 14
    assert many_rows == few_rows


def test_cart_uses_the_same_number_of_queries_for_few_and_many_lines(client, store, recorded_statements):
    product_ids = [store.product(stock=5) for number in range(12)]

    # Two lines in the cart
    for product_id in product_ids[:2]:
        client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=store.customer)
    start = len(recorded_statements)
    response = client.get("/cart", headers=store.customer)
    few_rows = len(recorded_statements) - start
    assert len(response.json()["items"]) == 2
    assert few_rows > 0

    # Twelve lines
    for product_id in product_ids[2:]:
        client.post("/cart/items", json={"product_id": product_id, "quantity": 1}, headers=store.customer)
    start = len(recorded_statements)
    response = client.get("/cart", headers=store.customer)
    many_rows = len(recorded_statements) - start
    assert len(response.json()["items"]) == 12
    assert many_rows == few_rows


def test_order_lists_use_the_same_number_of_queries_for_few_and_many_orders(
    client, store, create_user, auth_headers, pay, recorded_statements
):
    create_user("admin@example.com", role="admin")
    other_seller = create_user("seller-2@example.com", role="seller")
    lists = {
        "GET /orders": ("/orders", store.customer),
        "GET /seller/orders": ("/seller/orders", auth_headers("seller@example.com")),
        "GET /admin/orders": ("/admin/orders", auth_headers("admin@example.com")),
    }

    # Two orders. Each holds two products of two sellers and is paid (so the sellers can see it).
    for number in range(2):
        order = store.place_order([(store.product(stock=50), 1), (store.product(stock=50, seller=other_seller), 2)])
        pay(order)
    few_rows = {}
    for name, (path, headers) in lists.items():
        start = len(recorded_statements)
        response = client.get(path, headers=headers)
        few_rows[name] = len(recorded_statements) - start
        assert response.json()["total"] == 2, name
        assert few_rows[name] > 0, name

    # Twelve orders
    for number in range(10):
        order = store.place_order([(store.product(stock=50), 1), (store.product(stock=50, seller=other_seller), 2)])
        pay(order)
    for name, (path, headers) in lists.items():
        start = len(recorded_statements)
        response = client.get(path, headers=headers)
        many_rows = len(recorded_statements) - start
        assert response.json()["total"] == 12, name
        assert many_rows == few_rows[name], name
