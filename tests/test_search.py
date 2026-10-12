from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text


def test_search_finds_words_in_name_and_description(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_product(seller_id, category_id, name="Wooden Chair", description="Sturdy seat")
    create_product(seller_id, category_id, name="Desk", description="Comes with a drawer")
    create_product(seller_id, category_id, name="Lamp", description="Bright light")

    # A word in the name, in any letter case
    by_name = client.get("/products?q=CHAIR").json()
    # A word in the description
    by_description = client.get("/products?q=drawer").json()

    assert [item["name"] for item in by_name["items"]] == ["Wooden Chair"]
    assert [item["name"] for item in by_description["items"]] == ["Desk"]


def test_search_matches_word_stems(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Electronics")
    create_product(seller_id, category_id, name="Wireless Phones")

    response = client.get("/products?q=phone")

    assert [item["name"] for item in response.json()["items"]] == ["Wireless Phones"]


def test_search_with_several_words_needs_all_of_them(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Electronics")
    create_product(seller_id, category_id, name="Red Phone")
    create_product(seller_id, category_id, name="Blue Phone")
    create_product(seller_id, category_id, name="Red Chair")

    response = client.get("/products?q=red phone")

    assert [item["name"] for item in response.json()["items"]] == ["Red Phone"]


def test_websearch_syntax_works(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Electronics")
    create_product(seller_id, category_id, name="Red Phone")
    create_product(seller_id, category_id, name="Blue Phone")
    create_product(seller_id, category_id, name="Red Chair")

    # A leading minus excludes a word
    minus = client.get("/products?q=phone -red").json()
    # "or" matches either word
    either = client.get("/products?q=chair or blue").json()
    # A quoted phrase needs the words next to each other, in order
    phrase = client.get("/products", params={"q": '"red phone"'}).json()
    wrong_order = client.get("/products", params={"q": '"phone red"'}).json()

    assert [item["name"] for item in minus["items"]] == ["Blue Phone"]
    assert sorted(item["name"] for item in either["items"]) == ["Blue Phone", "Red Chair"]
    assert [item["name"] for item in phrase["items"]] == ["Red Phone"]
    assert wrong_order["items"] == []


def test_name_match_ranks_above_description_match(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Home")
    # Created first, so it has the lower id: the rank must win, not the id
    create_product(seller_id, category_id, name="Table", description="Looks great next to a lamp")
    create_product(seller_id, category_id, name="Reading Lamp", description="Bright light")

    response = client.get("/products?q=lamp&sort=relevance")

    assert [item["name"] for item in response.json()["items"]] == ["Reading Lamp", "Table"]


def test_relevance_is_the_default_sort_with_a_search(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Home")
    create_product(seller_id, category_id, name="Table", description="Looks great next to a lamp")
    create_product(seller_id, category_id, name="Reading Lamp", description="Bright light")

    response = client.get("/products?q=lamp")

    assert [item["name"] for item in response.json()["items"]] == ["Reading Lamp", "Table"]


def test_inactive_products_never_appear(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books", slug="books")
    create_product(seller_id, category_id, name="Hidden Novel", price=5000, is_active=False)

    # Every filter and sort that could match the inactive product
    queries = [
        "q=novel",
        "q=novel&sort=relevance",
        "category=books",
        "category=books&q=novel",
        "min_price=1000&max_price=9000",
        "in_stock=true",
        "q=novel&in_stock=true&min_price=1&sort=price_asc",
        "sort=name_asc",
        "sort=price_desc&category=books",
    ]
    for query in queries:
        body = client.get("/products?" + query).json()
        assert body["items"] == [], query
        assert body["total"] == 0, query


def test_editing_a_product_name_updates_the_search(
    client, create_user, create_category, create_product, auth_headers
):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    product_id = create_product(seller_id, category_id, name="Old Gadget")
    headers = auth_headers("seller@example.com")

    response = client.patch(f"/products/{product_id}", json={"name": "Shiny Widget"}, headers=headers)

    assert response.status_code == 200
    assert [item["name"] for item in client.get("/products?q=widget").json()["items"]] == ["Shiny Widget"]
    assert client.get("/products?q=gadget").json()["items"] == []


@pytest.mark.parametrize(
    "search_text",
    ["'", "&", ":*", "(", ")", "!", "'; DROP TABLE products; --", "a & b | !c", "\\", "%", "_", "a" * 100],
)
def test_odd_input_never_causes_an_error(client, create_user, create_category, create_product, search_text):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_product(seller_id, category_id, name="Plain product")

    response = client.get("/products", params={"q": search_text})

    assert response.status_code == 200
    assert response.json()["items"] == []

    # The products table is still there
    assert client.get("/products").json()["total"] == 1


def test_nul_character_in_the_search_text_is_handled(client):
    response = client.get("/products", params={"q": "a\x00b"})

    assert response.status_code == 200


def test_search_text_length_limit(client):
    assert client.get("/products", params={"q": "a" * 100}).status_code == 200
    assert client.get("/products", params={"q": "a" * 101}).status_code == 422


def test_blank_search_text_is_the_same_as_no_search(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_product(seller_id, category_id, name="First")
    create_product(seller_id, category_id, name="Second")

    response = client.get("/products?q=%20%20%20")

    assert response.status_code == 200
    assert response.json()["total"] == 2

    # Without a real search, relevance is not allowed
    assert client.get("/products?q=%20%20&sort=relevance").status_code == 422


def test_search_with_only_common_words_returns_an_empty_list(
    client, create_user, create_category, create_product
):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_product(seller_id, category_id, name="The Book of the Year")

    response = client.get("/products?q=the")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_search_and_category_combine(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    books = create_category("Books", slug="books")
    toys = create_category("Toys", slug="toys")
    create_product(seller_id, books, name="Space Book")
    create_product(seller_id, toys, name="Space Rocket")

    response = client.get("/products?q=space&category=toys")

    assert [item["name"] for item in response.json()["items"]] == ["Space Rocket"]


def test_unknown_category_still_returns_404_with_a_search(client):
    response = client.get("/products?q=space&category=nope")

    assert response.status_code == 404


def test_price_filters_are_inclusive(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_product(seller_id, category_id, name="Cheap", price=1000)
    create_product(seller_id, category_id, name="Middle", price=2000)
    create_product(seller_id, category_id, name="Expensive", price=3000)

    only_min = client.get("/products?min_price=2000&sort=price_asc").json()
    only_max = client.get("/products?max_price=2000&sort=price_asc").json()
    both = client.get("/products?min_price=2000&max_price=2000").json()
    between = client.get("/products?min_price=1001&max_price=2999").json()

    assert [item["name"] for item in only_min["items"]] == ["Middle", "Expensive"]
    assert [item["name"] for item in only_max["items"]] == ["Cheap", "Middle"]
    assert [item["name"] for item in both["items"]] == ["Middle"]
    assert [item["name"] for item in between["items"]] == ["Middle"]


def test_invalid_price_filters_are_rejected(client):
    too_low = client.get("/products?min_price=500&max_price=100")
    negative_min = client.get("/products?min_price=-1")
    negative_max = client.get("/products?max_price=-5")
    not_a_number = client.get("/products?min_price=abc")
    # More than the database column can hold
    too_big = client.get("/products?max_price=2147483648")

    assert too_low.status_code == 422
    assert "min_price" in too_low.json()["detail"]
    assert negative_min.status_code == 422
    assert negative_max.status_code == 422
    assert not_a_number.status_code == 422
    assert too_big.status_code == 422


def test_in_stock_hides_sold_out_products(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    create_product(seller_id, category_id, name="Available", stock=3)
    create_product(seller_id, category_id, name="Sold out", stock=0)

    only_available = client.get("/products?in_stock=true").json()
    everything = client.get("/products?in_stock=false").json()

    assert [item["name"] for item in only_available["items"]] == ["Available"]
    assert everything["total"] == 2


def test_sort_options(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    now = datetime.now(timezone.utc)
    create_product(seller_id, category_id, name="Banana", price=3000, created_at=now - timedelta(days=2))
    create_product(seller_id, category_id, name="Cherry", price=1000, created_at=now)
    create_product(seller_id, category_id, name="Apple", price=2000, created_at=now - timedelta(days=1))

    newest = client.get("/products?sort=newest").json()["items"]
    cheapest = client.get("/products?sort=price_asc").json()["items"]
    dearest = client.get("/products?sort=price_desc").json()["items"]
    by_name = client.get("/products?sort=name_asc").json()["items"]

    assert [item["name"] for item in newest] == ["Cherry", "Apple", "Banana"]
    assert [item["name"] for item in cheapest] == ["Cherry", "Apple", "Banana"]
    assert [item["name"] for item in dearest] == ["Banana", "Apple", "Cherry"]
    assert [item["name"] for item in by_name] == ["Apple", "Banana", "Cherry"]


def test_ties_are_broken_by_id_descending(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    same_time = datetime.now(timezone.utc)
    first_id = create_product(seller_id, category_id, name="Twin", price=1000, created_at=same_time)
    second_id = create_product(seller_id, category_id, name="Twin", price=1000, created_at=same_time)
    third_id = create_product(seller_id, category_id, name="Twin", price=1000, created_at=same_time)
    expected_ids = [third_id, second_id, first_id]

    for sort in ["newest", "price_asc", "price_desc", "name_asc"]:
        items = client.get("/products?sort=" + sort).json()["items"]
        assert [item["id"] for item in items] == expected_ids, sort

    # Same relevance (same text) also falls back to id descending
    items = client.get("/products?q=twin&sort=relevance").json()["items"]
    assert [item["id"] for item in items] == expected_ids


def test_invalid_sort_values_are_rejected(client):
    banana = client.get("/products?sort=banana")
    relevance_without_search = client.get("/products?sort=relevance")

    assert banana.status_code == 422
    assert relevance_without_search.status_code == 422
    assert "q" in relevance_without_search.json()["detail"]


def test_pagination_counts_only_filtered_products(client, create_user, create_category, create_product):
    seller_id = create_user("seller@example.com", role="seller")
    category_id = create_category("Books")
    for number in range(5):
        create_product(seller_id, category_id, name=f"Match {number}", price=1000 + number)
    create_product(seller_id, category_id, name="Other thing", price=1000)

    page_one = client.get("/products?q=match&page=1&page_size=2&sort=price_asc").json()
    page_three = client.get("/products?q=match&page=3&page_size=2&sort=price_asc").json()
    page_four = client.get("/products?q=match&page=4&page_size=2&sort=price_asc").json()

    assert page_one["total"] == 5
    assert [item["name"] for item in page_one["items"]] == ["Match 0", "Match 1"]
    assert [item["name"] for item in page_three["items"]] == ["Match 4"]
    assert page_four["items"] == []
    assert page_four["total"] == 5


def test_search_index_exists(db_session):
    # The test database is built by the real migrations
    index_name = db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'products' AND indexname = 'ix_products_search_vector'")
    ).scalar_one_or_none()

    assert index_name == "ix_products_search_vector"
