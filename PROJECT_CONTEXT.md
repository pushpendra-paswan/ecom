# PROJECT_CONTEXT.md

**Project status: complete (M0 to M10).**

Where things are: how to run and test (below), the database schema, the endpoint table, one section per milestone, then **Security model (M10)**, **Performance review (M10)**, **Hardening and audit decisions (M10)**, **Docker (M10)** and **Future work**. The root `README.md` is the guide for a newcomer.

## Project summary

An Amazon-style e-commerce web app, built for learning the full web flow from browser to database. Customers browse, search, add to cart, pay with Stripe (test mode only) and track orders. Sellers and admins manage products, inventory and orders. It is a well-built monolith; shipping is mocked. See `CLAUDE.md` for all rules (coding style, architecture, checkout and webhook rules, scope list).

## Tech stack

- Backend: Python 3.12, FastAPI, Pydantic, pydantic-settings
- ORM and migrations: SQLAlchemy 2.1 (synchronous), Alembic
- Database: PostgreSQL 16 (driver: psycopg 3)
- Frontend: plain HTML, CSS, JavaScript (served by FastAPI)
- Testing: pytest, pytest-cov and httpx (via FastAPI `TestClient`) against a real Postgres test database
- Dev environment: Docker Compose (`app` and `db`)
- Password hashing: `bcrypt` (used directly, no wrapper)
- Tokens: `PyJWT` (HS256). Email validation: `email-validator` (used by Pydantic `EmailStr`)
- Payments: `stripe` 16.0.0 (Python SDK, test mode only; added in M7, webhooks in M8)

Pinned versions are in `requirements.txt`.

## Folder structure

```
ecom/                      # project root
├── app/
│   ├── main.py            # FastAPI app: size limit, security headers and CSP middleware, error handlers, /health, static and frontend mounts
│   ├── db.py              # engine (15 s statement timeout), SessionLocal, Base, get_db
│   ├── seed.py            # demo data: python -m app.seed
│   ├── models/            # user.py, catalog.py, cart.py, order.py (__init__ imports all)
│   ├── schemas/           # user.py, address.py, category.py, product.py, cart.py, order.py
│   ├── routers/           # auth.py, users.py, admin.py, categories.py, products.py, cart.py, orders.py, seller_orders.py, webhooks.py
│   ├── services/          # auth_service.py, user_service.py, address_service.py, category_service.py, product_service.py, cart_service.py, checkout_service.py, order_service.py, order_lifecycle_service.py, webhook_service.py
│   ├── repositories/      # user_repository.py, address_repository.py, category_repository.py, product_repository.py, cart_repository.py, order_repository.py
│   └── core/
│       ├── config.py      # Settings class (reads env variables; JWT_SECRET needs 32 or more characters)
│       └── dependencies.py  # get_current_user, require_customer, require_seller, require_admin
├── alembic/               # env.py, script.py.mako, versions/ (four migrations: initial schema, M5 search, M9 refunded status, M10 order indexes)
├── alembic.ini
├── static/                # css/style.css, js/ (see the frontend map), images/ (placeholder.svg)
├── frontend/              # index.html, products.html, product.html, cart.html, login.html, register.html, addresses.html, checkout.html, order-success.html, order-cancelled.html, orders.html, order.html, seller-products.html, seller-product-form.html, seller-orders.html, seller-order.html, admin-orders.html, admin-order.html, admin-users.html, 404.html
├── tests/                 # conftest.py, test_health.py, test_schema.py, test_auth.py, test_users.py, test_roles.py, test_categories.py, test_products_public.py, test_products_write.py, test_search.py, test_cart.py, test_checkout.py, test_checkout_concurrency.py, test_webhooks.py, test_webhooks_concurrency.py, test_order_cancel.py, test_order_status.py, test_order_lifecycle_concurrency.py, test_frontend_files.py, and (M10) test_endpoint_security.py, test_idor.py, test_no_leaks.py, test_hardening.py, test_query_counts.py, test_full_flow.py, test_coverage_gaps.py
├── docker-compose.yml
├── Dockerfile
├── .dockerignore
├── pytest.ini
├── requirements.txt
├── .env.example / .env    # .env is git-ignored
├── README.md
├── CLAUDE.md
└── PROJECT_CONTEXT.md
```

## How to run

```bash
docker compose up --build
```

- App: http://localhost:8000/ (storefront home page)
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- CSS: http://localhost:8000/static/css/style.css
- Alembic: `docker compose exec app alembic current`

`.env` is a copy of `.env.example` with a real `JWT_SECRET` (`openssl rand -hex 32`; the app refuses to start with a missing or short one). Postgres is not published on the host (no `ports:` on the `db` service); use `docker compose exec db psql -U postgres ecommerce`. The app container runs as user id 1000, has a healthcheck on `/health` (`docker compose ps` shows `healthy`) and starts uvicorn with `--reload`; see "Docker (M10)". Full steps for a newcomer (Stripe CLI included) are in `README.md`.

## How to test

```bash
docker compose exec app pytest
docker compose exec app pytest --cov=app --cov-report=term-missing     # with the coverage report (pytest-cov, M10)
```

Tests use `TEST_DATABASE_URL` (database `ecommerce_test`). `tests/conftest.py` creates that database if missing, then runs `alembic downgrade base` and `alembic upgrade head` on it once per test session (so the migration itself is tested). It refuses to run if the test and dev database names are the same. The test engine uses the same 15 second `statement_timeout` as the real engine (`STATEMENT_TIMEOUT_MS` from `app/db.py`).

Fixtures:
- `db_session`: a session inside an outer transaction that is rolled back after every test (savepoint mode, so a failed statement inside `pytest.raises(IntegrityError)` does not break the test). Use this for model and repository/service tests.
- `client`: a `TestClient` whose `get_db` is overridden to use the test database. It commits for real, so after every test it runs `TRUNCATE users, categories RESTART IDENTITY CASCADE` (this empties every table). The test database is never seeded.

Helper fixtures in `conftest.py` (M2, M3):
- `create_user(email, role="customer", is_active=True, password="Password@123")`: inserts a user directly into the test database (fast bcrypt rounds) and returns the user id.
- `auth_headers(email, password="Password@123")`: logs in through `/auth/login` and returns `{"Authorization": "Bearer ..."}`.
- `create_category(name, slug=None)` (M3): inserts a category directly and returns its id. The slug defaults to the lowercased name with spaces turned into hyphens.
- `committed_data` (M7, used only by `tests/test_checkout_concurrency.py`): methods `customer(email)` (a customer with one address, returns `(user_id, address_id)`), `products(count, stock, price=10000)` (a seller, a category and several products, returns the ids) and `put_in_cart(user_id, product_id, quantity)`. Everything is committed with its own sessions, so several threads can see it. The fixture ends with `TRUNCATE users, categories RESTART IDENTITY CASCADE`, which runs even when the test fails.
- `post_webhook` (M8): sets `STRIPE_WEBHOOK_SECRET` to a test value and returns `post(event, timestamp=None, secret=<test secret>, signed_body=None)`. It turns the event dictionary into JSON bytes (or sends bytes as they are), signs them as Stripe does (`Stripe-Signature: t=<timestamp>,v1=<HMAC-SHA256 of "<timestamp>.<payload>">`) and posts the same bytes to `/webhooks/stripe`. `timestamp` and `secret` make a bad signature, `signed_body` signs a different body (tampered body). It uses the `client` fixture, so it also works from several threads.
- Shared by the order, webhook and cancel tests (moved into `conftest.py` in M9; they used to live in `test_webhooks.py`): `stripe_create` (patches `stripe.checkout.Session.create`, sets a dummy `sk_test_` key), the autouse `session_expire` and `refund_create` (patch `stripe.checkout.Session.expire` and `stripe.Refund.create`, so the real Stripe API can never be reached by any test), `query_database`, `change_database`, `store` (a seller `store.first_seller`, a category, a logged-in customer `store.customer`; `store.product(stock, price, seller=None)` and `store.place_order(items, customer=None)` go through the real checkout API), `read_order` (order status, payment status, payment intent, session id, refund id), `read_stock`, `pay` (pays an order with a signed `checkout.session.completed` webhook) and the function `make_event(...)` (import it with `from tests.conftest import make_event`).
- `create_product(seller_id, category_id, name=..., price=10000, stock=10, is_active=True, created_at=None, description="A test product")` (M3, `description` added in M5): inserts a product directly and returns its id. Pass `created_at` to control the order in tests.

M10 test files (each test builds its own data, nothing uses the seed; they reuse the fixtures above and add no new fixture to `conftest.py` except that the test engine now uses the real statement timeout):
- `test_endpoint_security.py`: `ENDPOINTS` (method, path, access) for all 38 endpoints and the five checks described in "Security model (M10)". Reads the real routes from `app.openapi()` plus `app.routes` because FastAPI 0.143 wraps included routers in a private object.
- `test_idor.py` (customer B against customer A, seller B against seller A, inactive products), `test_no_leaks.py` (one full scenario with real-looking Stripe ids; every GET endpoint for every allowed role), `test_hardening.py` (headers and CSP, 413, a route that raises, NUL / huge / long / wrong-type input, emoji and right-to-left text, login timing, weak secret, no CORS, the order total cap, the webhook order id), `test_query_counts.py` (a `before_cursor_execute` listener: the same number of SQL statements for 2 rows and for 12 rows on `GET /products`, `/cart`, `/orders`, `/seller/orders`, `/admin/orders`), `test_full_flow.py` (seller, customer, checkout, webhook, shipped, delivered, a second order paid and cancelled with the refund call checked), `test_coverage_gaps.py` (error and permission branches the other files did not reach).
- Tests that expect a 500 use `TestClient(app, raise_server_exceptions=False)`. The one test that adds a route to the app removes it again in a `finally` (the route is moved to the front because the `/` frontend mount would otherwise answer 404).

## Completed milestones

- **M0: Project setup.** Docker Compose (app + Postgres 16 with healthcheck and named volume), FastAPI skeleton with `/health`, static and frontend mounts, Alembic configured (no migrations), pytest against a separate test database.
- **M1: Database schema, models and seed data.** All 9 tables as SQLAlchemy 2.x models, one Alembic migration (`6fc51572ed70`), seed script, schema tests. No endpoints.
- **M2: Authentication, roles and user accounts.** Register, login (JWT), profile, addresses, admin user list, role dependencies, login/register pages, shared `api.js`, 32 tests passing. No schema change (no new migration).
- **M3: Catalog API.** Public category and product reads, admin category management, seller/admin product management with soft delete, `/seller/products`. No schema change (no new migration). 56 tests passing.
- **M4: Storefront frontend.** Shared navbar and footer (`layout.js`), home page, product listing page, product detail page, one product card function, one stylesheet, placeholder image. Read-only: no search, no cart. No backend or schema change. 57 tests passing (one new test that checks the frontend files are served).
- **M5: Search, filter, sort and indexes.** `GET /products` takes `q`, `category`, `min_price`, `max_price`, `in_stock`, `sort`, `page`, `page_size`. Postgres full-text search (generated `search_vector` column + GIN index), one extra partial index for the newest-first listing, the products page with a filter sidebar, a navbar search box, before/after measurements (see "Search (M5)"). One migration (`099593dc45a9`). 91 tests passing (34 new in `tests/test_search.py`).
- **M6: Cart.** Customer-only cart API (`/cart`, `/cart/count`, `/cart/items`), atomic upserts, per-line problem reporting, cart page, navbar Cart link with badge, Add to Cart on the product page, `?next=` login redirect. No schema change (no new migration; only the `CartItem.product` relationship was added). 109 tests passing (18 new in `tests/test_cart.py`).
- **M7: Checkout and orders.** `POST /orders/checkout` (two stages: one locked database transaction, then the Stripe Checkout Session), order history (`GET /orders`, `GET /orders/{id}`), checkout, addresses, orders, order detail, success and cancelled pages, navbar links "My Orders" and "Addresses", "Proceed to checkout" on the cart page. `stripe==16.0.0` added. No schema change (no new migration). 124 tests passing (12 new in `tests/test_checkout.py`, 3 in `tests/test_checkout_concurrency.py`, plus the frontend file test now covers the new pages).
- **M8: Stripe webhooks.** `POST /webhooks/stripe` (public, secured by the Stripe signature): `checkout.session.completed` marks the order paid, `checkout.session.expired` cancels it and gives the stock back, duplicates and retries are harmless, a late payment for a cancelled order is refunded. One service function, three repository functions for orders and one for products. No schema change (no new migration). 155 tests passing (31 new: 29 in `tests/test_webhooks.py`, 2 in `tests/test_webhooks_concurrency.py`; see "Webhooks (M8)").
- **M9: Order lifecycle, cancellations and dashboards.** `POST /orders/{id}/cancel` (customer own order, or admin; stock restored; Stripe session expired for an unpaid order, full Stripe refund for a paid one; "retry refund" path), `PATCH /seller/orders/{id}/status` and `PATCH /admin/orders/{id}/status` (paid to shipped to delivered), seller and admin order read endpoints, `GET /seller/products/{id}`, a row lock on product edits, a late-payment refund that now marks the payment `refunded`. One small migration (`408881ba845e`: `refunded` payment status and `payments.stripe_refund_id`). Seller pages (products, product form, orders, order detail), admin pages (orders, order detail, users), cancel and retry-refund buttons on the customer order page. 213 tests passing (58 new; see "Order lifecycle (M9)").

- **M10: Hardening and finish.** Size limit, security headers and CSP, safe error handling (`500` and `DataError` handlers), required 32 character `JWT_SECRET`, statement timeout, login timing protection, bounds on every input, order total cap, webhook order id rule, measured indexes (migration `e918e5dbff2d`), a frontend security and accessibility pass and `404.html`, the endpoint inventory test and six more test files (see "Test results (M10)"), a code and style audit, `pip-audit`, Docker polish (non-root user, healthcheck, `.dockerignore`) and the `README.md`. No new endpoints and no new tables. See "Security model (M10)", "Performance review (M10)" and "Hardening and audit decisions (M10)".

## Pending milestones

None. The project is complete (M0 to M10). Possible next steps are in "Future work".

## Database schema

Created by `alembic/versions/6fc51572ed70_create_initial_schema.py` (M1). M10 added the three order indexes (and dropped `ix_orders_user_id`) in `alembic/versions/e918e5dbff2d_add_order_list_indexes.py`; all money columns are `INTEGER` and cannot overflow, see "Input bounds" in the security model. The complete list of indexes with the reason for each is in "Performance review (M10)". M9 changed the payments status CHECK and added `payments.stripe_refund_id` in `alembic/versions/408881ba845e_payments_refunded_status_and_refund_id.py` (written by hand, because autogenerate does not see CHECK changes; the downgrade turns `refunded` rows into `succeeded` first). M5 added the `products.search_vector` column and two indexes in `alembic/versions/099593dc45a9_add_product_search_vector.py`. All tables have `id integer` primary key (auto-increment). Money columns are integers in paise. `timestamptz` columns default to `now()` on the server. `updated_at` is also refreshed by SQLAlchemy on ORM updates (`onupdate=func.now()`).

**users**: `email` varchar(255) unique not null; `password_hash` not null; `full_name` not null; `role` varchar(20) default `customer`, CHECK in (`customer`, `seller`, `admin`); `is_active` bool default true; `created_at`.

**addresses**: `user_id` FK users **ON DELETE CASCADE**; `full_name`, `phone`, `line1`, `line2` (nullable), `city`, `state`, `postal_code`, `country` (default `India`); `is_default` bool default false; `created_at`.

**categories**: `name` unique; `slug` unique; `description` (nullable); `created_at`. Flat list, no parent.

**products**: `seller_id` FK users (no action); `category_id` FK categories (no action); `name`; `description`; `price` CHECK `> 0`; `stock` CHECK `>= 0`; `image_url` (nullable); `is_active` default true; `created_at`; `updated_at`; `search_vector` (M5, `tsvector`, NOT NULL, `GENERATED ALWAYS AS (setweight(to_tsvector('english', name), 'A') || setweight(to_tsvector('english', description), 'B')) STORED`; Postgres keeps it up to date, the app never writes it). Indexes: see "Indexes on products" under "Search (M5)".

**carts**: `user_id` FK users **ON DELETE CASCADE**, UNIQUE (one cart per user); `created_at`.

**cart_items**: `cart_id` FK carts **ON DELETE CASCADE**; `product_id` FK products (no action); `quantity` CHECK `> 0`; UNIQUE (`cart_id`, `product_id`).

**orders**: `user_id` FK users **ON DELETE RESTRICT**; `status` varchar(20) default `pending_payment`, CHECK in (`pending_payment`, `paid`, `shipped`, `delivered`, `cancelled`); `total_amount` CHECK `>= 0`; shipping address copy: `shipping_full_name`, `shipping_phone`, `shipping_line1`, `shipping_line2` (nullable), `shipping_city`, `shipping_state`, `shipping_postal_code`, `shipping_country` (no FK to addresses); `created_at`; `updated_at`. Indexes: `ix_orders_status`, `ix_orders_created_at_id` (`created_at DESC, id DESC`) and `ix_orders_user_id_created_at_id` (`user_id, created_at DESC, id DESC`; M10, replaced the old `ix_orders_user_id`). `Order.items` is ordered by `OrderItem.id` in the relationship.

**order_items**: `order_id` FK orders **ON DELETE CASCADE** (index `ix_order_items_order_id`, M10); `product_id` FK products **ON DELETE RESTRICT**; `product_name` (snapshot); `unit_price` (snapshot) CHECK `> 0`; `quantity` CHECK `> 0`.

**payments**: `order_id` FK orders (no action), UNIQUE (one payment per order); `stripe_checkout_session_id` varchar(255) nullable, UNIQUE; `stripe_payment_intent_id` nullable; `stripe_refund_id` varchar(255) nullable (M9: set when a refund was made; empty when Stripe said the charge was already refunded); `amount` CHECK `>= 0`; `currency` default `inr`; `status` default `pending`, CHECK in (`pending`, `succeeded`, `failed`, `refunded`) (M9 added `refunded`); `created_at`; `updated_at`.

Constraints are named explicitly (`ck_<table>_<rule>`, `uq_cart_items_cart_id_product_id`); unique and FK constraints use Postgres default names.

ORM relationships (only these seven): `Product.category`, `Product.seller` (added in M3, no schema change), `Cart.items`, `CartItem.product` (added in M6, no schema change), `Order.items`, `Order.payment`, `OrderItem.product` (added in M9, no schema change; the seller dashboard reads the seller of every line through it). Everything else is queried by id in repositories.

## Seed data

Run (the database must be migrated first):

```bash
docker compose exec app python -m app.seed
```

If any category already exists, it prints a message and changes nothing. Dev password for every account: `Password@123`.

| Email | Role |
|---|---|
| admin@example.com | admin |
| seller1@example.com | seller |
| seller2@example.com | seller |
| customer1@example.com | customer (default address in Bengaluru) |
| customer2@example.com | customer (default address in Mumbai) |

Data: 10 categories, 120 products (12 per category, alternating between seller1 and seller2), prices from Rs 99 to Rs 74,999. Edge cases for later tests: 3 products with stock 1 ("Limited Edition Mechanical Keyboard", "Signed First Edition Novel", "Pro Carbon Tennis Racket"), 3 with stock 0 ("Winter Wool Overcoat", "Remote Control Stunt Car", "Walnut Study Desk"), 2 inactive ("Discontinued Pressure Cooker 3L", "Old Formula Face Serum"). Image URLs are `https://picsum.photos/seed/<product-slug>/400/400`.

## Reset the database

```bash
docker compose down -v          # removes the Postgres volume (all data)
docker compose up -d
docker compose exec app alembic upgrade head
docker compose exec app python -m app.seed
```

Without deleting the volume: `alembic downgrade base`, then `alembic upgrade head`, then the seed.

## Key design decisions (M0)

- Project root is the existing `ecom/` folder, not a nested `ecommerce/` folder.
- `/health` lives in `main.py` and uses the `get_db` dependency (so tests hit the test DB). Any exception from `SELECT 1` returns 503 `{"detail": "Database is unreachable"}`.
- `/static` is mounted first and `/` (frontend, `html=True`) last, so API routes always win.
- Docker Compose hardcodes the Postgres user, password and DB name (`postgres` / `postgres` / `ecommerce`); `.env` has the matching `DATABASE_URL` (host `db`) and `TEST_DATABASE_URL`.
- Postgres port is not published to the host, to avoid clashing with a local Postgres.
- `DATABASE_URL` and `TEST_DATABASE_URL` are required in `Settings`; Stripe and JWT values default to empty. `STRIPE_CURRENCY` defaults to `inr` and `FRONTEND_BASE_URL` to `http://localhost:8000`.
- `alembic/env.py` takes the URL from `settings.DATABASE_URL` (the `sqlalchemy.url` line in `alembic.ini` is removed) and uses `Base.metadata`.
- `pytest.ini` disables the pytest cache and the Dockerfile sets `PYTHONDONTWRITEBYTECODE=1`, so the container does not leave root-owned cache files in the mounted project folder.
- `.gitkeep` files keep `static/js`, `static/images` and `alembic/versions` present while empty. `tests/__init__.py` exists so test imports work.
- SQLAlchemy 2.1.4 (latest 2.x at the time) is pinned. `starlette.testclient` prints a deprecation warning about `httpx`; it is harmless.

## Key design decisions (M1)

- Integer auto-increment ids on every table (`id`), as asked.
- Money is an integer in paise everywhere (`price`, `unit_price`, `total_amount`, `amount`). Stripe gets the same numbers.
- Roles and statuses are `varchar` with a named CHECK constraint, not Postgres enums, so changing them later is a simple migration.
- `orders` stores a copy of the shipping address (no FK to `addresses`), and `order_items` stores `product_name` and `unit_price` snapshots, so old orders never change when addresses or products are edited.
- Delete rules: user deletes cascade to addresses and carts; cart deletes cascade to cart items; order deletes cascade to order items; users with orders and products with order items cannot be deleted (RESTRICT). Products referenced by a cart item, and sellers/categories referenced by products, are also blocked (default NO ACTION). Use `is_active = false` instead of deleting products.
- `app/seed.py` runs at import time (plain top-to-bottom script, no `main()` function) and commits once at the end. It hashes the dev password once and reuses the hash for all five users.
- `alembic/env.py` imports `app.models` and uses `sqlalchemy.url` from the Alembic config if one is set, otherwise `settings.DATABASE_URL`. Only the tests set it (to the test database).
- Test schema is built by running the real migration (downgrade base, upgrade head at session start), not `create_all`.
- `Order.items` and `Cart.items` have no `back_populates` (only the four relationships requested exist).
- Seed products use explicit `stock` and `is_active` per row, so the edge-case products (stock 1, stock 0, inactive) are visible in the data lists.

## API endpoints (as of M10, 38 operations; the access rules and the ownership rules are also in "Security model (M10)")

| Method and path | Access | Notes |
|---|---|---|
| GET `/health` | public | Database check |
| POST `/auth/register` | public | Returns 201 and the user. Role `customer` (default) or `seller`; `admin` gives 422 |
| POST `/auth/login` | public | JSON body `{email, password}`, returns `{access_token, token_type}` |
| GET `/users/me` | any logged-in user | |
| PATCH `/users/me` | any logged-in user | Changes only `full_name` |
| GET `/users/me/addresses` | any logged-in user | Own addresses only |
| POST `/users/me/addresses` | any logged-in user | Returns 201. First address becomes default |
| PUT `/users/me/addresses/{address_id}` | any logged-in user | Full replace. Not your address: 404 |
| DELETE `/users/me/addresses/{address_id}` | any logged-in user | Returns 204. Not your address: 404 |
| GET `/admin/users` | admin only | Paginated (see below) |
| GET `/categories` | public | All categories sorted by name, with `product_count` |
| POST `/categories` | admin only | Returns 201. Duplicate name or slug: 409. Name with no letters or digits: 422 |
| PUT `/categories/{category_id}` | admin only | Same body and rules as create. Missing: 404 |
| DELETE `/categories/{category_id}` | admin only | Returns 204. Any product (active or not) uses it: 409 `"Category has products"`. Missing: 404 |
| GET `/products` | public | Paginated (`page` up to 100,000), active products only. Search, filters and sort: see "Search (M5)" |
| GET `/products/{product_id}` | public | Missing or inactive: 404 |
| POST `/products` | seller only | Returns 201. Admin and customer get 403. Unknown `category_id`: 400. `price` 1 to 10,000,000 paise, `stock` 0 to 1,000,000 (above: 422) |
| PATCH `/products/{product_id}` | seller (own products) or admin (any) | Partial update. Customer: 403. Other seller's product or missing: 404 |
| DELETE `/products/{product_id}` | seller (own products) or admin (any) | Soft delete, returns 204 (also when already inactive). Same rules as PATCH |
| GET `/seller/products` | seller only | Paginated, the caller's own products, active or not, newest first |
| GET `/seller/products/{product_id}` | seller only (own product) | M9. The public product shape, also for inactive products. Someone else's or a missing product: 404. Customer or admin: 403 |
| GET `/cart` | customer only | The caller's cart (shape under "Cart (M6)"). Never changes data; creates no cart row |
| GET `/cart/count` | customer only | `{"item_count": N}`, one query |
| POST `/cart/items` | customer only | Returns 200. Body `{product_id, quantity (1 to 10, default 1)}`. Adds to the quantity. Missing or inactive product: 404. Over the limit: 409 |
| PATCH `/cart/items/{product_id}` | customer only | Body `{quantity (1 to 10)}`. Sets the exact quantity. Not in the cart: 404. Inactive product or over the limit: 409 |
| DELETE `/cart/items/{product_id}` | customer only | Always 204, even if the line was not there |
| DELETE `/cart` | customer only | Removes all lines, always 204. The cart row stays |
| POST `/orders/checkout` | customer only | Returns 201 `{order_id, checkout_url, total_amount}`. Body `{address_id}` only. A total above 99,999,999 paise: 409, nothing changes. See "Checkout and orders (M7)" |
| GET `/orders` | customer only | Paginated, the caller's orders, newest first (`created_at DESC, id DESC`). Each item: `id, status, total_amount, created_at, item_count, items[{product_id, product_name, unit_price, quantity}]` |
| GET `/orders/{order_id}` | customer only | `id, status, total_amount, created_at, shipping_address{...}, items[{..., line_total}], payment{status, amount, currency}`. Someone else's or a missing order: 404 `"Order not found"`. A non-numeric id: 422 |
| POST `/orders/{order_id}/cancel` | customer (own order) or admin (any order) | M9. Returns 200 `{order_id, status, payment_status}`. Seller 403, no token 401, missing or someone else's order 404 `"Order not found"`, shipped or delivered 409, refund not possible 503 or 409, refund failed 502. See "Order lifecycle (M9)" |
| GET `/seller/orders` | seller only | M9. Paginated (`page`, `page_size`), newest first. Only paid orders (payment `succeeded` or `refunded`) that contain the seller's products; only the seller's own lines. Item: `id, status, created_at, items[{product_id, product_name, unit_price, quantity, line_total}], seller_subtotal, has_other_sellers` |
| GET `/seller/orders/{order_id}` | seller only (visibility rule) | M9. Same fields plus `shipping_address`. Not visible to this seller: 404 |
| PATCH `/seller/orders/{order_id}/status` | seller only (visibility rule, and every item must be theirs) | M9. Body `{"status": "shipped" or "delivered"}` (anything else 422). 200 `{order_id, status}` |
| GET `/admin/orders` | admin only | M9. Paginated, newest first, optional `status` (one of the five, otherwise 422). Item: `id, status, created_at, total_amount, customer_email, shipping_full_name, item_count` (total quantity) |
| GET `/admin/orders/{order_id}` | admin only | M9. The list fields plus `user_id`, `shipping_address`, `items[...]`, `payment{status, amount, currency}`. Missing: 404 |
| PATCH `/admin/orders/{order_id}/status` | admin only | M9. Same body and rules as the seller endpoint, without the seller checks |
| POST `/webhooks/stripe` | public, **Stripe signature required** | Returns 200 `{"received": true}`. 400 bad signature or body, 503 secret not configured, 500 retryable failure. See "Webhooks (M8)" |

All cart endpoints, `POST /orders/checkout`, `GET /orders` and `GET /orders/{id}`: no token gives 401, a seller or admin gives 403 (`require_customer`). `POST /orders/{id}/cancel` is the one order endpoint that also allows admins.

The pages `/`, `/products.html`, `/product.html`, `/cart.html`, `/login.html`, `/register.html`, `/addresses.html`, `/checkout.html`, `/orders.html`, `/order.html`, `/order-success.html`, `/order-cancelled.html`, `/seller-products.html`, `/seller-product-form.html`, `/seller-orders.html`, `/seller-order.html`, `/admin-orders.html`, `/admin-order.html`, `/admin-users.html` and everything under `/static` are public files. The pages that need a login are only HTML shells; their data comes from API endpoints that need a token.

## Auth flow (M2)

- **Register** creates a `customer` or `seller` (never `admin`; the seed creates admins). Email is trimmed and lowercased, password is 8 to 72 characters (also max 72 bytes, and no NUL character), stored only as a bcrypt hash. Duplicate email: 409.
- **Login** looks up the lowercased email, checks the bcrypt password first, then `is_active`. Unknown email and wrong password give the same 401 `"Incorrect email or password"` (an unknown email still runs one `bcrypt.checkpw` against the module constant `DUMMY_PASSWORD_HASH`, same cost factor, so timing is the same; a password over 72 bytes or with a NUL character is also this 401). A correct password on a disabled account gives 403 `"Account is disabled"`.
- **Token:** PyJWT, HS256 (only HS256 is accepted when decoding, with `exp` and `sub` required), signed with `JWT_SECRET` (32 or more characters). Payload is only `sub` (user id as a string) and `exp` (`JWT_EXPIRE_MINUTES`, default 60). The role is NOT in the token.
- **Browser storage:** the token is in `localStorage` under the key `access_token`. `static/js/api.js` (`apiRequest(path, method, body)`) adds `Authorization: Bearer <token>`. On a 401 from any path except `/auth/login` it removes the token and throws; it goes to `/login.html?next=<encoded path and query of the current page>` only when the page's `<body>` has `data-requires-login="true"` (changed in M4, `next` added in M6).
- **Every request** to a protected endpoint goes through `get_current_user` (in `app/core/dependencies.py`): it reads the Bearer header (`HTTPBearer(auto_error=False)`), decodes the token, loads the user from the database and returns the user. The role and `is_active` always come from the database.
- **401** (`"Not authenticated"`, with `WWW-Authenticate: Bearer`): missing header, bad signature, expired token, no `sub`/`exp`, user not found, or user disabled.
- **403:** logged in, but the role is wrong. `require_customer`, `require_seller` and `require_admin` check that the role is exactly that role (an admin does NOT pass `require_customer` or `require_seller`).
- **404:** a resource that exists but belongs to someone else (for example another user's address) looks the same as one that does not exist.
- **409:** duplicate email.

## Pagination format (M2)

List endpoints take `page` (default 1, between 1 and 100,000) and `page_size` (default 20, between 1 and 100); values outside the range give 422. The response is:

```json
{"items": [...], "total": 42, "page": 1, "page_size": 20}
```

## Settings (M2)

| Variable | Default | Meaning |
|---|---|---|
| `JWT_SECRET` | none, **required**, at least 32 characters | Signing key. Generate with `openssl rand -hex 32`. The app and Alembic refuse to start (pydantic validation error) if it is missing or shorter (M10; before, only an empty value was refused) |
| `JWT_EXPIRE_MINUTES` | 60 | Token lifetime |

Stripe settings (read in `app/core/config.py`, used since M7): `STRIPE_SECRET_KEY` (must start with `sk_test_`; empty gives 503 "Payments are not configured" and any other prefix gives 503 "Only Stripe test keys are allowed", both before any database work), `STRIPE_WEBHOOK_SECRET` (used since M8; empty makes the webhook answer 503 "Webhooks are not configured"), `STRIPE_CURRENCY` (default `inr`), `FRONTEND_BASE_URL` (default `http://localhost:8000`, used for the Stripe success and cancel URLs).

The algorithm (HS256) is written inline where the token is created and decoded. The local `.env` has a generated dev secret; `.env.example` has the placeholder `REPLACE_ME` (too short on purpose, so a copied example cannot start) with a note.

## Key design decisions (M2)

- **Services raise `HTTPException` directly** (404, 409, 401, 403, 422). CLAUDE.md did not say how services report errors; this is the simplest option and avoids a separate exception layer.
- **No `core/security.py`:** bcrypt hashing/checking and JWT encode/decode are written inline in `auth_service.py` and `dependencies.py`.
- **`get_current_user` calls `user_repository.get_user_by_id`** directly (a dependency may use the repository). It shares the request's session with the service, so services can modify `current_user` and commit it.
- **Pydantic strips spaces** (`str_strip_whitespace`) on register, profile and address bodies; the service lowercases the email. Login takes `email` as a plain string, so a badly formatted email gives 401, not 422.
- **Passwords:** the 72-byte limit is checked in bytes in the service (a 72-character password with multi-byte characters is rejected with 422 on register, and with 401 on login), because bcrypt 5 raises an error above 72 bytes.
- **Addresses:** one shared `AddressRequest` for POST and PUT (PUT replaces all fields). A user may end up with no default address (deleting the default, or a PUT with `is_default: false` on it); the app never promotes another one. Nothing in the database enforces "one default per user"; the service does it.
- **Unknown JSON fields are ignored** (for example `role` in a PATCH body), so PATCH `/users/me` can only change `full_name`.
- **A missing or short `JWT_SECRET` stops the app at startup** (`Field(min_length=32)` in `config.py`; it was a check at the bottom of the file until M10), because a weak key would allow forged tokens.
- **`apiRequest`:** the method defaults to `GET` if omitted, and a `204` response returns `null`.
- `static/js/index.js` (temporary user bar) was added in M2 and deleted in M4 when the real navbar arrived.
- `static/js/.gitkeep` was deleted because the folder now has files.

## Catalog (M3)

**Category response** (create, update): `{id, name, slug, description}`. **List item** (`GET /categories`) adds `product_count`, the number of ACTIVE products (0 for empty categories). It is one grouped query with an outer join; the "is active" test is inside the join condition, so empty categories are not dropped.

**Product response** (list items, detail, create, update and `/seller/products` all use this shape):

```json
{"id": 1, "name": "...", "description": "...", "price": 49900, "stock": 5,
 "image_url": "https://... or /static/images/x.png or null", "is_active": true,
 "created_at": "2026-...Z", "category": {"id": 2, "name": "Books", "slug": "books"},
 "seller": {"id": 3, "full_name": "Meera Iyer"}}
```

The seller's email and every other private field are never returned. Lists are wrapped in the pagination format above. The schemas are in `app/schemas/product.py` and `app/schemas/category.py`.

**Rules**
- **Soft delete:** `DELETE /products/{id}` only sets `is_active = false`. The row stays, so old orders and carts that point to the product stay valid. `PATCH {"is_active": true}` brings it back. Inactive products are hidden from `GET /products` and `GET /products/{id}` (404) but still appear in `/seller/products`.
- **Other sellers' products return 404** (not 403) on PATCH and DELETE. A customer gets 403. A product that does not exist gets 404. Admins can change any product. `seller_id` is set from the logged-in seller on create and can never be changed.
- **Slug rule** (written inline in `category_service.py`, once in create and once in update): lowercase; spaces and underscores become hyphens; every character outside `a-z`, `0-9` and `-` is removed; repeated hyphens collapse into one; hyphens at the start and end are trimmed. "Home & Kitchen" becomes `home-kitchen`. An empty result (for example "!!!") gives 422. Updating a category regenerates the slug.
- **Duplicates:** the service inserts and catches `IntegrityError` (rollback, then 409), so the unique constraints on `name` and `slug` decide. Names that differ only in punctuation or case (for example "Books" and "books!") share a slug and give 409.
- **Money** is integer paise everywhere in the API. Nothing is converted.
- `image_url` must start with `http://`, `https://` or `/static/images/` (checked by a `Field(pattern=...)`) and is at most 500 characters. M10 limits: product `name` 1 to 200, `description` 1 to 5000, `price` 1 to 10,000,000 paise, `stock` 0 to 1,000,000, `category_id` 1 to 2,147,483,647; category `name` 1 to 100 and `description` up to 5000. `null` is allowed and PATCH with `image_url: null` removes the image.

## Frontend (M4)

### Frontend map

| URL | Query parameters | Files |
|---|---|---|
| `/` | none | `frontend/index.html`, `home.js` |
| `/products.html` | `q`, `category`, `min_price`, `max_price`, `in_stock`, `sort`, `page`. **Prices in the page URL are in RUPEES** (see "Search (M5)"). `page` defaults to 1; anything below 1 or not a number becomes 1 | `frontend/products.html`, `products.js` |
| `/product.html` | `id` (positive whole number; anything else shows "Product not found" without calling the API) | `frontend/product.html`, `product.js` |
| `/cart.html` | none. `<body data-requires-login="true">` | `frontend/cart.html`, `cart.js` |
| `/addresses.html` | `next` (optional, same safety rule as login; only used after a successful ADD). `<body data-requires-login="true">` | `frontend/addresses.html`, `addresses.js` |
| `/checkout.html` | none. Login required | `frontend/checkout.html`, `checkout.js` |
| `/order-success.html` | `order_id` (positive whole number, otherwise "Order not found" and no API call). Login required | `frontend/order-success.html`, `order-success.js` |
| `/order-cancelled.html` | `order_id` (optional, only used for a link). Login required | `frontend/order-cancelled.html`, `order-cancelled.js` |
| `/orders.html` | `page` (default 1). Login required | `frontend/orders.html`, `orders.js` |
| `/order.html` | `id` (positive whole number, otherwise "Order not found" and no API call). Login required | `frontend/order.html`, `order.js` |
| `/seller-products.html` | `page`. Login required, seller | `frontend/seller-products.html`, `seller-products.js` |
| `/seller-product-form.html` | `id` (optional: with it the form edits that product; anything but a positive whole number shows "Product not found" without calling the API). Login required, seller | `frontend/seller-product-form.html`, `seller-product-form.js` |
| `/seller-orders.html` | `page`. Login required, seller | `frontend/seller-orders.html`, `seller-orders.js` |
| `/seller-order.html` | `id` (same rule as `/order.html`). Login required, seller | `frontend/seller-order.html`, `seller-order.js` |
| `/admin-orders.html` | `status` (one of the five, otherwise ignored), `page`. Login required, admin | `frontend/admin-orders.html`, `admin-orders.js` |
| `/admin-order.html` | `id` (same rule). Login required, admin | `frontend/admin-order.html`, `admin-order.js` |
| `/admin-users.html` | `page`. Login required, admin | `frontend/admin-users.html`, `admin-users.js` |
| `/login.html` | `next` (optional, see "Cart (M6)") | `frontend/login.html`, `login.js` |
| `/register.html` | `next` (optional, same rule) | `frontend/register.html`, `register.js` |
| any unknown path | none | `frontend/404.html` (M10): the shared header and footer, "Page not found" and a link home; the `StaticFiles(html=True)` mount serves it with status 404 |

| Script (`static/js/`) | What it does |
|---|---|
| `api.js` | `apiRequest(path, method, body)`: fetch + JSON + token header. On a 401 it removes the token and throws; redirects to `/login.html?next=...` only if `<body data-requires-login="true">`. Errors carry the HTTP status in `error.status` |
| `layout.js` | Defines `SITE_NAME` (once, `"ShopEasy"`). Fills `#site-header` (navbar, with the search form added in M5) and `#site-footer`. Calls `GET /users/me` only when a token exists; any failure silently shows Login and Register. Logout removes the token and reloads. For a **customer** it also adds a "Cart" link with the badge `<span id="cart-count">` and fills it from `GET /cart/count` (M6), and (M7) "My Orders" and "Addresses" links. Sellers and admins get none of them. M9: a **seller** also gets "My Products" (`/seller-products.html`) and "Orders" (`/seller-orders.html`), an **admin** gets "Orders" (`/admin-orders.html`) and "Users" (`/admin-users.html`); nobody sees another role's links |
| `product-card.js` | `buildProductCard(product)`: returns the `<a>` card used by the home and listing pages (image with one-time placeholder fallback, name, price, "Out of stock" label) |
| `home.js` | Category cards (`GET /categories`) and the 8 newest products (`GET /products?page=1&page_size=8`) |
| `products.js` | Sidebar (category links, filter form), heading, total count, product grid (20 per page) and Previous/Next links. Converts rupees from the URL to paise for the API (M5) |
| `product.js` | Product detail (image, name, category link, seller, price, stock status, buy area, description). M6: calls `GET /users/me` once (if a token exists) and shows the buy area, see "Cart (M6)" |
| `cart.js` | M6: one function `loadCart()` fetches `GET /cart` and draws the whole cart page. Called on page load and after every change. M7: a "Proceed to checkout" link to `/checkout.html` in the summary box (plain text instead of a link when `has_problems`; an empty cart shows no summary at all) |
| `addresses.js` | M7: `loadAddressesPage()`: address cards with a "Default" label, one form for add and edit, delete (after `confirm()`), "Make default" (a full PUT with `is_default: true`). After a successful ADD it goes to `next` if `next` passes the login.js safety check (written inline) |
| `checkout.js` | M7: loads `GET /cart` and `GET /users/me/addresses`, shows a read-only summary and the address radio buttons (default preselected), and the "Place order and pay" button. An empty cart shows a message and no button; `has_problems` and "no address" disable the button. The redirect goes only to a URL that starts with `https://checkout.stripe.com/`. After an error the button comes back only for a 502 or a network failure |
| `order-success.js` | M7: checks `GET /orders/{id}` up to 15 times, 2 seconds apart, while the status is `pending_payment`. Says "Payment received. Thank you!" only when the API status is `paid` (or later `shipped`/`delivered`), "This order was cancelled." for `cancelled`, otherwise "We are still confirming your payment. Check My Orders in a moment." Arriving on the page never counts as proof of payment |
| `order-cancelled.js` | M7: the static message plus links (the order, My Orders, products) |
| `orders.js` | M7: My Orders, 10 per page, order cards with the first 3 items, Previous/Next links |
| `order.js` | M7: order detail (address, items table, total, payment status). Holds its own status label objects (one for the order, one for the payment). M9: the payment status is a badge (`Refunded` added); a "Cancel order" button for `pending_payment` and `paid` (`confirm()` first, different text for paid; calls `POST /orders/{id}/cancel`, reloads on success); for a cancelled order with payment `succeeded` it shows "Refund pending" and "Retry refund" (same endpoint). After a 502 it shows the API message and a "Reload" button (the order is cancelled, the page is stale) |
| `seller-products.js` | M9: table of `GET /seller/products` (20 per page): image with placeholder fallback, name, price, stock (orange at 5 or fewer), Active/Inactive, "Edit" link, "Deactivate" (`DELETE /products/{id}`) or "Activate" (`PATCH {"is_active": true}`). Reloads after success, shows the API message on error |
| `seller-product-form.js` | M9: one form for create (`POST /products`) and edit (`PATCH /products/{id}`, loaded from `GET /seller/products/{id}`). Price is typed in rupees and sent as `Math.round(Number(value) * 100)`; checks name, description, price above 0, whole-number stock, category before sending. In create mode it calls `GET /users/me` once, only to show "This page is for seller accounts." to other roles |
| `seller-orders.js`, `seller-order.js` | M9: one card per visible order (the seller's own lines, "Your items total", "Includes other sellers' products"); detail page with the shipping address, the seller's items, "Mark as shipped" / "Mark as delivered" only when `has_other_sellers` is false (otherwise the "only an admin" note) |
| `admin-orders.js`, `admin-order.js`, `admin-users.js` | M9: orders table with a GET status filter (pagination links keep it), order detail with customer email, address, all items, payment badge and the buttons "Mark as shipped", "Mark as delivered", "Cancel order" (`confirm()`), "Retry refund"; read-only users table |
| `login.js`, `register.js` | The two forms (from M2). M6: after success they go to the `next` page (rule below) instead of always `/` |

`static/css/style.css` is the one stylesheet (variables, base, layout, navbar and footer, buttons, forms, cards and grid, category links and pagination, products page sidebar, product detail, states, responsive; M9 added "Order actions and payment badges" and "Seller and admin dashboards"). Dashboard tables sit in `.table-wrapper` (scrolls inside its own box); on small screens `.dashboard-table` keeps a minimum width, so it scrolls in its box and the page never scrolls sideways. `static/images/placeholder.svg` is the fallback image.

### How to add a new page

1. Create `frontend/<name>.html` with `<!DOCTYPE html>`, `lang="en"`, charset and viewport meta tags, a meaningful `<title>`, `<link rel="icon" href="data:,">` (without it the browser asks for `/favicon.ico` and logs a 404 in the console) and the stylesheet link. Exactly one `<h1>`. No inline `<script>`, `<style>`, `style=""` or `on...=` attribute: the Content-Security-Policy blocks them.
2. Inside `<body>`: an empty `<header id="site-header"></header>`, a `<main class="container">` with the content, and an empty `<footer id="site-footer"></footer>`.
3. Scripts at the end of the body, in this order: `api.js`, `layout.js`, then the page script (add `product-card.js` before the page script if it shows product cards).
4. If the page needs a logged-in user (cart, checkout, orders), put `data-requires-login="true"` on `<body>`. Then a 401 sends the user to `/login.html`. Public pages must NOT set it, so a stale token never redirects them.
5. Script globals are shared between script tags, so page scripts put their code inside one function (for example `async function loadProductsPage()`) and call it once. Do not redeclare `SITE_NAME`, `apiRequest`, `buildProductCard` or `showLayout`.

### Frontend rules

- **Price display** (prices are paise, shown as rupees). Use this exact inline expression wherever a price is shown (`price` is the paise value, for example `product.price`):
  `"₹" + (price / 100).toLocaleString("en-IN", { minimumFractionDigits: price % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 })`
- **Never put API data into the page with `innerHTML` or template strings that become HTML.** Names, descriptions, category names and seller names come from sellers and admins. Build elements with `document.createElement`, set text with `textContent`, set attributes with `setAttribute` or properties, and use `encodeURIComponent` for text values in links. The description uses `textContent` in an element with `white-space: pre-line`.
- Every data area starts with "Loading..." and shows a message plus a "Try again" button (reloads the page) when a request fails. Empty lists show "No products found." with a link to all products.
- Stock status: 0 is red "Out of stock", 1 to 5 is orange "Only N left in stock", above 5 is green "In stock".
- (M10) Accessibility: every control has a `<label>` or `aria-label`; the areas that show "Loading...", an error or an empty state are `aria-live="polite"`; error paragraphs and the action and checkout messages have `role="alert"`. The `next` redirect check is the same condition in `login.js`, `register.js` and `addresses.js`. Form limits match the API limits (see the security model).

### Key design decisions (M4)

- `apiRequest` now puts the HTTP status on the error (`error.status`). The milestone did not ask for it; `product.js` needs it to tell a 404 ("Product not found") from other failures (which get an error message and "Try again").
- The product id must also be at most 2147483647 (the database integer limit). A larger number would make the API answer 500 (an existing backend quirk), so the page shows "Product not found" without calling the API.
- `page` is accepted only if it is a safe integer of at least 1, so a huge page number falls back to 1 instead of overflowing the database offset.
- A page number past the last page shows "No products found." and no pagination.
- Page titles do not contain the site name (it is defined only in `layout.js`). `product.js` sets the tab title to the product name.
- Page scripts wrap their code in one function each (classic scripts have no top-level `await`, and it keeps their variables out of the global scope). Error boxes and empty states are written out in each script, as the coding style asks, not shared.
- `login.html` and `register.html` now have the navbar and footer, with the form inside `<main class="container">`. `static/js/index.js` and the `.user-bar` style were removed.
- Tested by hand in headless Chrome (all pages, stale token, valid token, database stopped, 375px wide). The only automated frontend test checks that the files are served.

## Notes from M3 for the storefront (used in M4)

- Response shapes are described above (`app/schemas/product.py`, `app/schemas/category.py`). Both lists are public, so the storefront needs no token.
- **Prices are paise.** The frontend must divide by 100 to show rupees (for example `49900` is Rs 499.00).
- `GET /categories` returns `product_count` (active products only), ready for a home page category grid.
- `image_url` is either an `https://` URL, a `/static/images/...` path (served by the static mount), or `null`. Show a placeholder for `null`.
- `stock` can be 0: show "out of stock" and do not offer add-to-cart.
- `GET /products?category=<slug>` filters by category and gives 404 for an unknown slug.

## Search (M5)

### `GET /products` query parameters (all optional, all combinable)

| Parameter | Type | Limits | Default | Notes |
|---|---|---|---|---|
| `q` | string | trimmed; at most 100 characters (101 gives 422); empty or only spaces counts as no search | none | Full-text search on name and description (see below) |
| `category` | string | a category slug, up to 100 characters | none | Unknown slug: 404 |
| `min_price` | integer, paise | 0 to 1,000,000,000, inclusive (M10; was 2147483647) | none | Greater than `max_price`: 422 |
| `max_price` | integer, paise | 0 to 1,000,000,000, inclusive (M10) | none | |
| `in_stock` | boolean | `true` / `false` | `false` | `true` shows only products with `stock > 0` |
| `sort` | one of `relevance`, `newest`, `price_asc`, `price_desc`, `name_asc` | anything else gives 422 | `relevance` when `q` is present, otherwise `newest` | `relevance` without `q` gives 422 |
| `page` | integer | 1 to 100,000 (M10) | 1 | |
| `page_size` | integer | 1 to 100 | 20 | |

- Only active products are ever returned, with every combination. Every sort ends with `id DESC`, so pages are stable. The response shape is unchanged (`items`, `total`, `page`, `page_size`); `total` counts the products after all filters.
- Orders: `newest` = `created_at DESC`; `price_asc` / `price_desc` = `price`; `name_asc` = `name ASC`; `relevance` = `ts_rank(search_vector, query) DESC` (a name match has weight A, a description match weight B, so name matches rank higher).
- The price upper limit was the database integer limit (2147483647) until M10; it is now 1,000,000,000 paise (a product costs at most 10,000,000). Without any limit a huge value made Postgres fail with a 500.

### How the search works

- Postgres built-in full-text search only (no extension). `search_vector @@ websearch_to_tsquery('english', q)`.
- **Syntax** (websearch): several words must all match; `"quoted phrase"` needs the words next to each other in order; `a or b` matches either; a leading `-word` excludes it. Any other input (`'`, `&`, `:*`, `(`, `)`, `!`, SQL text) is just text and never causes a syntax error.
- **Whole words and stems** (the `english` configuration): "phones" finds "phone" and the other way round; "running" finds "run". Common words (stop words such as "the", "a", "of") are ignored, so a search made only of them returns 200 with an empty list.
- **Limitations:** no partial words ("pho" does not find "phone"), no typo tolerance, no "did you mean", no highlighting, no search inside `/seller/products`. Words are stemmed with the English rules only, so product names in other languages are matched as plain words.
- A NUL character (`%00`) in `q` is removed by the service, because Postgres text cannot hold it (it would be a 500).
- All rules (trim, min/max check, default sort) live in `product_service.list_public_products`. The repository `list_products` has no business rules: it builds one list of WHERE conditions and uses it for both the page query and the count query, and it returns `(products, total)`. `count_products` was removed. `/seller/products` calls the same function with `only_active=False`, a `seller_id`, no search and `sort="newest"`.

### URL of `products.html` (rupees in the page URL, paise in the API)

| URL parameter | Meaning |
|---|---|
| `q` | Search text (shown with `textContent` only) |
| `category` | Category slug |
| `min_price`, `max_price` | **In RUPEES.** The page converts with `Math.round(Number(value) * 100)` before calling the API, which takes **paise** |
| `in_stock` | `1` = in stock only |
| `sort` | `relevance` (only with `q`; without `q` it is treated as `newest`), `newest`, `price_asc`, `price_desc`, `name_asc` |
| `page` | 1 or more |

The sidebar form is a plain GET form to `/products.html` (hidden inputs keep `q` and `category`, and are disabled when empty). It does not send `page`, so applying filters returns to page 1. The sort dropdown submits the form on change. "Clear filters" keeps only `q` and `category`. Category links keep `q`, the price filters, `in_stock` and `sort`, and drop `page`. The navbar search form sends only `q`, so a new search drops the category and the filters. Bad price input (not a number, negative, too large, min above max) shows a message and does not call the API.

### Indexes on products

| Index | Definition | Why it exists |
|---|---|---|
| `products_pkey` | `btree (id)` | Primary key, detail page |
| `ix_products_category_id` | `btree (category_id)` | Category filter, the foreign key (M1) |
| `ix_products_price` | `btree (price)` | Price range filter and price sort (M1). Measured: the price-range query uses it (0.04 ms) |
| `ix_products_seller_id` | `btree (seller_id)` | `/seller/products`, the foreign key (M1) |
| `ix_products_search_vector` | `gin (search_vector)` | Full-text search (M5) |
| `ix_products_active_newest` | `btree (created_at DESC, id DESC) WHERE is_active IS TRUE` (partial) | Newest-first listing of active products: the home page, the default listing and the category listing (M5, measured below) |

The partial index condition is written `is_active IS TRUE` on purpose. SQLAlchemy's `Product.is_active.is_(True)` sends `is_active IS true`, and Postgres did **not** use an index declared with `WHERE is_active` for that query (measured: still a sequential scan). Keep the two spellings identical.

Migration `099593dc45a9` was checked by hand. `alembic upgrade head`, `downgrade -1`, `upgrade head` all work, and `alembic revision --autogenerate` found no drift (the empty revision was deleted).

### Search performance

All measurements: Postgres 16 in the `db` container, default settings, 120 seeded rows plus 50,000 temporary rows inside a transaction that is rolled back (the dev database has 120 products afterwards, checked with `select count(*) from products`). The SQL is exactly what SQLAlchemy sends (captured with a `before_cursor_execute` listener), with literal values. "Execution time" is from `EXPLAIN (ANALYZE, BUFFERS)`, second run (warm cache). Numbers are from one machine and vary a little between runs.

The template in the milestone gave every sample row the same `created_at` and the same category. That would make the newest-first and category queries meaningless, so the sample rows spread `created_at` (one per minute) and rotate through all categories. Everything else is as given.

**Setup block** (run inside `BEGIN; ... ROLLBACK;`, then `VACUUM ANALYZE products;`):

```sql
INSERT INTO products (seller_id, category_id, name, description, price, stock, is_active, created_at)
SELECT (SELECT id FROM users WHERE role = 'seller' ORDER BY id LIMIT 1),
       (SELECT array_agg(id ORDER BY id) FROM categories)[1 + g % (SELECT count(*) FROM categories)],
       'Sample product ' || g || ' ' || (ARRAY['laptop','phone','book','shirt','chair','bottle'])[1 + g % 6],
       'Description text for sample product number ' || g,
       100 + (g % 5000) * 100, 10, true,
       now() - g * interval '1 minute'
FROM generate_series(1, 50000) g;
ANALYZE products;
```

**Commands** (the files were kept outside the project; they contain the setup block above followed by the `EXPLAIN` statements below):

```bash
docker compose cp setup.sql db:/tmp/setup.sql
docker compose cp stage1.sql db:/tmp/stage1.sql      # BEGIN; \i /tmp/setup.sql; EXPLAIN ...; ROLLBACK; VACUUM ANALYZE products;
docker compose exec -T db psql -U postgres ecommerce -f /tmp/stage1.sql
docker compose exec -T db psql -U postgres ecommerce -c "select count(*) from products"   # must print 120
```

The search statements (the page query is the real one with its two `LEFT OUTER JOIN`s; shortened here to the part that matters):

```sql
-- Stage 1 (ILIKE), page query and count query
EXPLAIN (ANALYZE, BUFFERS) SELECT products.id, products.name FROM products
  LEFT OUTER JOIN categories AS categories_1 ON categories_1.id = products.category_id
  LEFT OUTER JOIN users AS users_1 ON users_1.id = products.seller_id
  WHERE products.is_active IS true
    AND (products.name ILIKE '%charger%' ESCAPE '\' OR products.description ILIKE '%charger%' ESCAPE '\')
  ORDER BY products.created_at DESC, products.id DESC LIMIT 20 OFFSET 0;
EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM products WHERE products.is_active IS true
  AND (products.name ILIKE '%charger%' ESCAPE '\' OR products.description ILIKE '%charger%' ESCAPE '\');

-- Stage 2 (full-text), page query (relevance) and count query
EXPLAIN (ANALYZE, BUFFERS) SELECT products.id, products.name FROM products
  LEFT OUTER JOIN categories AS categories_1 ON categories_1.id = products.category_id
  LEFT OUTER JOIN users AS users_1 ON users_1.id = products.seller_id
  WHERE products.is_active IS true
    AND (products.search_vector @@ websearch_to_tsquery('english'::regconfig, 'charger'))
  ORDER BY ts_rank(products.search_vector, websearch_to_tsquery('english'::regconfig, 'charger')) DESC, products.id DESC
  LIMIT 20 OFFSET 0;
EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM products WHERE products.is_active IS true
  AND (products.search_vector @@ websearch_to_tsquery('english'::regconfig, 'charger'));
```

The search word `charger` is rare (1 match in 50,120 rows), which is what a normal product search looks like. `laptop` (1 row in 6) is the common-word case.

**Before (stage 1, ILIKE `'%text%'`, no usable index) and after (stage 2, full-text, GIN index present):**

| Query (50,120 rows) | Plan | Execution time |
|---|---|---|
| Stage 1, `charger`, page query | Seq Scan + Sort | **74.3 ms** |
| Stage 1, `charger`, count query | Seq Scan | 72.4 ms |
| Stage 1, `laptop` (8,335 matches), page query | Seq Scan + top-N heapsort | 68.5 ms |
| Stage 2, `charger`, page query | **Seq Scan** + Sort (planner choice) | **11.4 ms** |
| Stage 2, `charger`, count query | Seq Scan (planner choice) | 11.4 ms |
| Stage 2, `laptop`, page query | Seq Scan + top-N heapsort | 14.4 ms |
| Stage 2, `charger`, count query with `SET LOCAL enable_seqscan = off` | **Bitmap Heap Scan + Bitmap Index Scan on `ix_products_search_vector`** | **2.6 ms** (the same query was 11.0 ms as a seq scan) |

**The expected bitmap index scan did not happen by itself on this data.** With the milestone's sample rows (a 13 MB table, about 40 characters of description per row) the planner estimates 251 matching rows for `charger` (the real number is 1), prices the GIN scan at about the same as a sequential scan (2374 against 2298) and picks the sequential scan. The full-text version is still about 6 times faster than ILIKE (11 ms against 74 ms) because it compares one stored `tsvector` per row instead of running two `ILIKE` patterns, and the index is 4 times faster again when it is used (2.6 ms). Realistic descriptions make the index matter more. A second run with 60 random words in every description (table 78 MB, GIN index 111 MB, otherwise the same):

| Query (60-word descriptions) | Plan | Execution time |
|---|---|---|
| ILIKE count, `charger` | Seq Scan | 236 ms |
| Full-text count, `charger`, planner's own choice | **Bitmap Heap Scan + Bitmap Index Scan on `ix_products_search_vector`** | **0.3 to 0.6 ms** |
| Full-text count, `charger`, with `SET LOCAL enable_bitmapscan = off` | Seq Scan | 22.7 ms |

So on rows with real-sized text the planner chooses the GIN index by itself, and it is about 400 to 800 times faster than the ILIKE version. The index costs disk space (111 MB for 78 MB of table in this test, a worst case with 60 distinct words per row) and slows inserts and updates a little.

**Other queries** (page queries with the two joins, 50,120 rows). Measured before adding any extra index:

| Query | Plan before | Time before | Plan after `ix_products_active_newest` | Time after |
|---|---|---|---|---|
| Default listing (newest, active only) | Seq Scan + top-N heapsort (reads all 50,118 rows) | 14.8 ms | Index Scan using `ix_products_active_newest` | 0.02 ms |
| Category filter, newest | Bitmap Index Scan on `ix_products_category_id` + top-N heapsort of 5,012 rows | 2.7 ms | Index Scan using `ix_products_active_newest` (stops after 20 matching rows) | 0.04 ms |
| Price range 1000 to 5000 rupees, `price_asc` | Index Scan using `ix_products_price` | 0.04 ms | unchanged | 0.03 ms |

**Decision on extra indexes:** one was added, `ix_products_active_newest` (partial, `(created_at DESC, id DESC) WHERE is_active IS TRUE`). Evidence: the default listing was a sequential scan plus a sort of every active row (14.8 ms and growing with the table), and the same index also fixed the category listing (2.7 ms to 0.04 ms). The `(category_id, price)` index was **not** added: the price query already uses `ix_products_price` at 0.04 ms, so there is no evidence for it. The existing `category_id`, `price` and `seller_id` indexes are unchanged.

**Known limit:** the total count (`SELECT count(*) ... WHERE is_active`) is still a sequential scan (about 9.7 ms for 50,000 rows, before and after the new index), because every row has to be counted. This is fine for this project's size. If it ever matters, the usual fixes are caching the total or an estimated count; neither is in scope.

## Cart (M6)

### `GET /cart` response

```json
{"items": [{"product_id": 7, "name": "...", "image_url": "... or null", "unit_price": 49900, "stock": 5,
            "is_active": true, "quantity": 2, "line_total": 99800, "available": true, "problem": null}],
 "item_count": 2, "subtotal": 99800, "has_problems": false}
```

- Money is integer paise. `unit_price` is always the **current** product price (the cart stores no price). `line_total = unit_price * quantity`. Lines are ordered by `cart_items.id` (when they were added).
- A line is **available** when the product is active and `stock >= quantity`. `problem` is `null` for available lines, otherwise `"No longer available"` (inactive), `"Out of stock"` (stock 0) or `"Only N left"` (stock above 0 but below the quantity), checked in that order.
- `item_count` is the total quantity of ALL lines (also lines with problems). `subtotal` adds only available lines. `has_problems` is true if any line is unavailable.
- No cart row yet: `{"items": [], "item_count": 0, "subtotal": 0, "has_problems": false}` and no row is created.
- **`GET /cart` and `GET /cart/count` never modify data.** A problem is only reported; lines are never removed or corrected automatically. The cart items and their products are loaded in one query (`joinedload(CartItem.product)`; checked: 1 query for 3 lines).
- `POST` and `PATCH` return `{"product_id", "quantity" (new quantity of that line), "item_count" (cart total)}`.

### Quantity limit

The most of one product in a cart is `min(stock, MAX_QUANTITY_PER_PRODUCT)`, where `MAX_QUANTITY_PER_PRODUCT = 10` (top of `cart_service.py`). Above it: 409 `"Maximum quantity for this product is N"`, or 409 `"Out of stock"` when the limit is 0. A refused request leaves the cart exactly as it was. The cart is **not** a stock reservation: stock is only reserved at checkout.

The request bodies check `quantity` 1 to 10 with a literal `10` in `schemas/cart.py` (a schema should not import from a service). Keep the two in sync. `product_id` (body and path) must be 1 to 2147483647 (the database integer limit; a bigger number would be a 500), otherwise 422.

### Atomic upserts (and why)

Two requests at the same moment (a double click, two tabs) must never create two carts, fail with a unique error, or lose a quantity. So there is no check-then-insert:

1. `INSERT INTO carts ... ON CONFLICT (user_id) DO NOTHING`, then `SELECT id` (`cart_repository.get_or_create_cart_id`).
2. `INSERT INTO cart_items ... ON CONFLICT ON CONSTRAINT uq_cart_items_cart_id_product_id DO UPDATE SET quantity = cart_items.quantity + excluded.quantity RETURNING quantity` (`cart_repository.upsert_cart_item`). The old quantity is never read first.

The service then compares the returned quantity with the limit; if it is too high it calls `db.rollback()` (this also removes a cart row that was created by the same request) and raises 409. PATCH checks the limit **before** changing anything. Both use the dialect `insert` from `sqlalchemy.dialects.postgresql`. The service owns the transaction; the repository never commits.

DELETE of a line or of the whole cart is one `DELETE ... WHERE cart_id IN (SELECT id FROM carts WHERE user_id = ...)`, so another user's cart can never be touched.

### The `next` redirect rule (login and register)

`api.js` sends a logged-out visitor on a `data-requires-login="true"` page to `/login.html?next=<encodeURIComponent(pathname + search)>`. The product page's "Log in to add to cart" link uses the same format. After a successful login or registration, `login.js` and `register.js` read `next` and use it **only if** it starts with `/`, does not start with `//`, contains no backslash and (added in M6) contains no control character. Otherwise they go to `/`. The check is written inline in each file. The control-character test closes a hole: `next=/%09/evil.com` decodes to `/<tab>/evil.com`, and browsers delete the tab, which leaves `//evil.com`. The register page has no link that carries `next` from the login page yet (not asked), so `next` only works there when it is typed into the URL.

### Badge rule

The element is `<span id="cart-count" class="cart-badge">` inside the Cart link, created by `layout.js` for **customers only** (hidden until known). `layout.js` fills it from `GET /cart/count` after `GET /users/me`; if that call fails there is no badge and no error. `cart.js` (from `item_count`) and `product.js` (from the POST answer) update it with `document.getElementById("cart-count")` and **only if the element exists** (the navbar fills in after an async call, so it may not exist yet). The badge text is the number and it is hidden when the number is 0.

### Product page buy area

Decided in this order: seller or admin gives "Use a customer account to buy products." (any stock); stock 0 shows nothing extra (the "Out of stock" status is enough, also when logged out); logged out shows "Log in to add to cart"; a customer gets a quantity dropdown (1 to `min(stock, 10)`) and "Add to Cart". The role comes from one `GET /users/me` call on the page; any failure counts as logged out. Messages: "Added to cart" with a "Go to cart" link, or the API's error text.

### Cart page

Each line: image (linked, one-time placeholder fallback), name (linked), unit price, quantity dropdown (1 to `min(stock, 10)`; if the quantity is above that, a disabled first option shows it and stays selected; no dropdown when the limit is 0), line total, Remove. Lines with a problem have a lighter background and the problem in red. Changing the dropdown calls PATCH, Remove calls DELETE, Clear cart calls `DELETE /cart` after `confirm()`; each then calls `loadCart()` again, **also after an error** (the error stays in the message area above the list and the list is refreshed, so a stale page fixes itself). The controls of the line are disabled while its request runs. The summary box has a "Proceed to checkout" link (M7). A seller or admin who opens `/cart.html` by hand sees "Could not load your cart: Customer access required" (their navbar has no Cart link).

## Checkout and orders (M7)

### The checkout flow (`app/services/checkout_service.py`, function `checkout`)

`POST /orders/checkout` takes only `{address_id}` (1 to 2147483647). Items, prices and amounts always come from the server. It is plain sequential code, steps a to n in order. `CHECKOUT_SESSION_MINUTES = 30` and `MAX_ORDER_TOTAL = 99_999_999` are the constants at the top of the file.

Before any database work: `STRIPE_SECRET_KEY` empty gives 503 "Payments are not configured"; a key that does not start with `sk_test_` gives 503 "Only Stripe test keys are allowed".

**Stage 1: one database transaction** (default READ COMMITTED, isolation level not changed)

| Step | What | Result if it fails |
|---|---|---|
| a | Load the address where `id = address_id AND user_id = me` | 404 "Address not found" |
| b | `SELECT ... FOR UPDATE` on the user's cart row (`cart_repository.lock_cart`) | no cart row: 400 "Your cart is empty" |
| c | Load the cart items | none: 400 "Your cart is empty" |
| d | Lock the product rows of those items with ONE query, `WHERE id IN (...) ORDER BY id FOR UPDATE` (`product_repository.lock_products`) | |
| e | Check every line against the locked rows: active, and stock at least the quantity. Collect ALL problems | 409 with one message such as `"Pen: out of stock; Book: only 3 left"` (`"<name>: no longer available"`, `"<name>: out of stock"`, `"<name>: only N left"`). Rollback, nothing changed |
| f | Line prices from the locked product rows, `total_amount = sum(unit_price * quantity)` | |
| f2 | (M10) If `total_amount` is above `MAX_ORDER_TOTAL` (99,999,999 paise, at the top of the file; Stripe accepts at most eight digits) | Rollback, nothing written, 409 "Order total is too large (maximum ₹9,99,999.99 per order). Remove some items and try again." |
| g | Create the order (`pending_payment`) with the shipping fields copied from the address | |
| h | Create the order items (snapshot of `product_name` and `unit_price`) | |
| i | `product.stock = product.stock - quantity` for each line (the CHECK `stock >= 0` is only a backstop) | |
| j | Create the payment: `amount = total_amount`, `currency = STRIPE_CURRENCY`, `status = pending` | |
| k | Delete the cart items (the cart row stays) | |
| l | **Commit.** No lock is held after this | |

**Stage 2: after the commit, no database lock held**

| Step | What |
|---|---|
| m | `stripe.checkout.Session.create(...)`, see "Stripe session settings" |
| n | A second small transaction saves `payments.stripe_checkout_session_id`. The payment intent id is NOT saved here (M8 does it). Returns 201 `{order_id, checkout_url (the session url), total_amount}` |

**Lock order and why.** Always the cart row first, then the product rows in ascending id order, in stage 1 and in the failure path. The cart lock makes a double click or two tabs of the same user safe: the second request waits, then finds an empty cart (400). Locking all products in ascending id order with one query means two checkouts with overlapping products can never wait for each other in a circle (no deadlock). Two buyers of the last item: the second one waits for the product lock, then re-reads the stock (0) and gets 409. `lock_products` uses `populate_existing`, because the cart items were loaded with their products before the lock (step c) and SQLAlchemy would otherwise keep those stale numbers instead of the freshly locked ones.

**Why the Stripe call is outside the transaction.** A database transaction must never stay open during a network call. Stripe can take seconds (or hang up to the 10 second timeout), and the open transaction would hold the cart and product locks that whole time, blocking every other buyer of those products.

**Failure path.** If the Stripe call raises `stripe.StripeError` (the base class of all Stripe errors in SDK 16.0.0), ONE cancellation transaction runs: lock the cart row, lock the product rows (same order), set the order to `cancelled`, set the payment to `failed`, add the quantities back to the stock, and put the order's items back into the cart (the same atomic upsert as the cart API, so a product the customer added again in the meantime gets the quantities added together; this can pass the usual limit of 10 in that rare case). The answer is 502 "Payment service is unavailable. Your cart has not been changed. Please try again." The Stripe error text is not sent to the client and nothing is logged.

### Stripe session settings

`mode="payment"`; one line item per order item (`price_data`: `currency` from settings, `unit_amount` = the snapshot `unit_price`, `product_data.name` = the snapshot name; `quantity`); `client_reference_id=str(order_id)`; `metadata={"order_id": str(order_id)}`; `customer_email` = the user's email; `success_url = FRONTEND_BASE_URL + "/order-success.html?order_id=<id>"`; `cancel_url = FRONTEND_BASE_URL + "/order-cancelled.html?order_id=<id>"`; `idempotency_key="order-<id>"`; `api_key=settings.STRIPE_SECRET_KEY` (passed on the call, no global key); `expires_at` = now + 30 minutes + 60 seconds (integer Unix timestamp, see decisions). The 10 second network timeout is set inline with `stripe.default_http_client = stripe.RequestsClient(timeout=10)`: in SDK 16.0.0 the timeout belongs to the HTTP client, not to the call. The SDK's default of 2 automatic retries on network errors stays on; it is safe because of the idempotency key.

### What is written at checkout

| Table | Fields |
|---|---|
| `orders` | `user_id`, `status = pending_payment`, `total_amount`, `shipping_full_name`, `shipping_phone`, `shipping_line1`, `shipping_line2`, `shipping_city`, `shipping_state`, `shipping_postal_code`, `shipping_country` (all copied from the address) |
| `order_items` | `order_id`, `product_id`, `product_name`, `unit_price` (the locked product's price at that moment), `quantity` |
| `payments` | `order_id`, `amount = total_amount`, `currency = settings.STRIPE_CURRENCY`, `status = pending`, `stripe_checkout_session_id` (set in step n), `stripe_payment_intent_id` stays NULL |
| `products` | `stock` reduced by the quantities |
| `cart_items` | all of the user's lines deleted |

On a Stripe failure: `orders.status = cancelled`, `payments.status = failed`, `stripe_checkout_session_id` stays NULL, stock restored, cart lines restored.

Stripe ids (`stripe_checkout_session_id`, `stripe_payment_intent_id`) are never returned by any endpoint.

### Known gaps

- Only card payments are supported (asynchronous payment methods are not handled).
- Only full refunds (no partial refunds), and no returns after delivery.
- The cart is empty after an abandoned payment (the customer has to add the items again; the order is still in My Orders). There is no "pay again" button.

The M9 notes that used to be here are done; see "Order lifecycle (M9)".

### Key design decisions (M7)

- **Decisions CLAUDE.md and the milestone did not cover:**
  - `expires_at` is now + 30 minutes + 60 seconds. Stripe requires at least 30 minutes between creating the session and its expiry, and the request needs a moment to arrive, so exactly 30 minutes could be refused. The tests accept 29 to 31 minutes. The cancelled page's "up to 30 minutes" is therefore a little conservative.
  - `address_id` and `order_id` have an upper limit of 2147483647 (422 above), like the other ids.
  - `page` of `GET /orders` has no upper limit (same as the other lists); a gigantic page number would be a 500.
  - The product lock query uses `populate_existing` (see above). The cart-lock query returns only the cart id.
  - The failure path locks the cart row first, because putting items back touches `cart_items`, whose foreign key needs a share lock on the cart row; taking the product locks first could deadlock with a second checkout of the same user.
  - The success page counts `shipped` and `delivered` as "payment received" too (they only come after `paid`), and shows "This order was cancelled." for `cancelled`.
  - The checkout button comes back after a 502 or a network failure only. After other errors it stays disabled (the page needs a reload or another page).
  - `api.js` already put the status on the error (M4), so it was not changed.
  - `STRIPE_SECRET_KEY` is read on every checkout call (not at import time), so the tests can change the setting.
  - The existing `client` fixture commits for real and truncates afterwards (it does not roll back); the new `tests/test_checkout.py` uses it like `test_cart.py` does. Only `committed_data` is new.
- **Tests:** Stripe is replaced with `unittest.mock.patch("stripe.checkout.Session.create")` and the key setting is set to `sk_test_dummy` with `monkeypatch`. The concurrency tests call `checkout_service.checkout` directly from threads (each with its own session), lined up with a `threading.Barrier(...)`, and fail if a thread is still alive after 15 seconds. They passed 20 runs in a row. As a check, they all fail when the two `FOR UPDATE` locks are removed.
- **Tested by hand** with headless Chrome (Playwright from a temporary virtual environment outside the project) and a real `sk_test_` key: a seeded customer adds two products, checks out, lands on the real Stripe page; cancelled page, orders list, detail, success page ending with "still confirming" after about 30 seconds; `<script>` and `<img onerror>` text in an address shows as plain text on the addresses, checkout and order pages (no dialog); cart problem state (inactive product) disables the checkout; no-address state with `?next=` returns to the checkout after adding; simulated 502, 409 and a non-Stripe `checkout_url`; 375px and 360px wide pages without horizontal scroll; seller sees no Cart, My Orders or Addresses links. The dev database was restored to the seeded state afterwards.

## Webhooks (M8)

### The endpoint

`POST /webhooks/stripe` (`app/routers/webhooks.py`, prefix `/webhooks`). Public: no login, no `Depends(require_*)`. Its security is the Stripe signature, checked on the **exact raw bytes** of the body with `STRIPE_WEBHOOK_SECRET` (`stripe.Webhook.construct_event`, default tolerance of 5 minutes). There is no Pydantic body model and `request.json()` is never used, because parsing and re-serializing would change the bytes. It is the **only `async def` endpoint** in the project: reading the raw body needs `await request.body()`. The blocking service call runs through `run_in_threadpool`, so database and Stripe calls do not block the event loop. The router returns whatever the service returns: `{"received": true}`.

The service is one function, `webhook_service.handle_stripe_event(db, payload, signature_header)`: plain sequential code with steps a to i. It takes the session from `get_db` like every other service (the milestone listed only `payload` and `signature_header`; the session is needed so the tests' database override works, and so the concurrency tests can pass their own session).

### Events

| Event | What happens |
|---|---|
| `checkout.session.completed`, `payment_status = "paid"`, order `pending_payment` | Order `paid`, payment `succeeded`, `stripe_payment_intent_id` saved. Commit, 200 |
| same, order already `paid` (duplicate) / `shipped` / `delivered` | Nothing changes, 200 |
| same, order `cancelled` (late payment) | Payment already `refunded`: 200, no Stripe call. Otherwise the order stays cancelled, the payment intent is saved and committed, then a refund is created and the payment becomes `refunded` (see below). 200, or 500 if the refund call fails |
| `checkout.session.completed`, `payment_status` not `"paid"` | Nothing changes, 200 |
| `checkout.session.completed`, `amount_total` or `currency` (lowercased) different from the payment's | Error is logged, nothing changes, 200 (a bug to investigate, not something Stripe should retry) |
| `checkout.session.expired`, order `pending_payment` | Order `cancelled`, payment `failed`, stock of every order item given back. One transaction. 200 |
| same, any other order status | Nothing changes, 200 |
| Any other event type (for example `payment_intent.created`) | Logged and ignored, 200 |

Out of scope and not handled: `checkout.session.async_payment_succeeded` / `async_payment_failed`, `payment_intent.payment_failed` (Stripe's page lets the customer retry inside the same session), a table of processed event ids, emails, any retry queue of our own.

### Response codes and why

| Code | When | Why |
|---|---|---|
| 200 `{"received": true}` | handled, or ignored, or not our problem to retry: unknown session, unknown order, no usable order id in the metadata, an order with a different session, a duplicate, an amount mismatch | Stripe retries every non-2xx response for days. Retrying these would never help |
| 400 "Invalid webhook request" | missing `Stripe-Signature`, wrong signature, tampered body, timestamp older than 5 minutes, a body that is not valid JSON (even with a valid signature) | A forged or broken request. Nothing is read from the body, nothing changes. The message is generic on purpose |
| 503 "Webhooks are not configured" | `STRIPE_WEBHOOK_SECRET` is empty | Nothing can be verified, so nothing is processed. Checked before anything else |
| 500 | a database error or any unexpected exception (the transaction is rolled back), or the late-payment refund failed | Something we should retry: Stripe sends the event again |

The SDK raises `stripe.SignatureVerificationError` (class `stripe._error.SignatureVerificationError` in 16.0.0) for a missing header, a bad header, a wrong signature and an old timestamp, and `ValueError` (`JSONDecodeError`, `UnicodeDecodeError`) for a body that is not JSON. Both give 400. The SDK checks only that a timestamp is too OLD (not too new).

### Idempotency, and why the check is inside the order row lock

Stripe delivers the same event more than once (and retries non-2xx answers), and two deliveries can arrive at the same moment. Checking the status first and updating later would let both deliveries see `pending_payment` and both act (for example giving stock back twice). So the service locks the order row with `SELECT ... FOR UPDATE` (`order_repository.lock_order`, with `populate_existing`) and reads the status **inside the lock**: the second delivery waits at the lock, then reads the status the first one left behind and changes nothing. Only an order that is still `pending_payment` is changed. The two-thread tests (`tests/test_webhooks_concurrency.py`) fail when the lock is removed.

Lock order: this endpoint locks the order row, then updates products in ascending product id order (one atomic `UPDATE products SET stock = stock + n` each, `product_repository.increase_stock`). Checkout locks the cart row, then products in ascending id order, and never locks an order, so the two can never deadlock.

### How the payment is found

1. By `stripe_checkout_session_id` = the session id in the event.
2. Fallback: `metadata.order_id` (it must be 1 to 9 ASCII digits, checked inline with `isdigit()` and `len()` (M10; before: up to 10 digits and at most 2147483647), so `abc`, `1.5`, `-1`, ` 1`, empty and huge numbers like `99999999999999999999` give a logged 200 and change nothing). The fallback matters because checkout stage 2 (M7) can fail **after** the Stripe session exists, which leaves the payment without a session id.
3. Found by order id and the payment already has a **different** session id: logged, 200, nothing changes. Found by order id and the session id is empty: the event's session id is saved on the payment (together with the change the event causes).
4. No payment found: warning, 200.

### The late-payment refund

If `checkout.session.completed` (paid, amounts match) arrives for an order that is already `cancelled` (for example the Stripe call in checkout timed out, the order was cancelled by the failure path, or the customer cancelled and still paid before the session was expired), the order is NOT reactivated and the stock stays as it is (it was already given back). If the payment is already `refunded` the answer is 200 and Stripe is not called. Otherwise the service saves the payment intent id and commits, then calls `stripe.Refund.create(payment_intent=..., idempotency_key="late-payment-refund-<order id>")`, outside any transaction. On success a small transaction sets the payment to `refunded` and saves `stripe_refund_id` (M9; before M9 the payment stayed `failed` and every delivery called the refund again). If Stripe answers `charge_already_refunded` (for example the customer's own cancel already refunded it) that counts as success too, with no refund id (a small M9 addition, so such a retry cannot loop forever). If the refund call raises any other `stripe.StripeError` the answer is 500, so Stripe delivers the event again; the retry reaches the same code and the idempotency key makes that safe.

### Logging

One line per event with only the event id, the event type, the order id and the outcome, through `logging.getLogger(__name__)`. The request body, the signature header and the secrets are never logged (a test checks this with `caplog`). `main.py` calls `logging.basicConfig(level=logging.INFO)`, otherwise Python hides INFO lines. `alembic/env.py` now calls `fileConfig(..., disable_existing_loggers=False)`: the test setup runs Alembic inside the pytest process, and the default `True` silently disabled all existing loggers (including the webhook logger).

### Local webhook setup

1. On the host, run: `stripe listen --events checkout.session.completed,checkout.session.expired --forward-to localhost:8000/webhooks/stripe`
2. Copy the `whsec_...` secret it prints into `STRIPE_WEBHOOK_SECRET` in `.env`.
3. Recreate the app container so it reads the new value: `docker compose up -d --force-recreate app`
4. Pay with the test card `4242 4242 4242 4242` (any future expiry, any CVC). The declined card `4000 0000 0000 0002` shows an error on Stripe's page and lets the customer retry; the order stays `pending_payment`.
5. To test expiry, run `stripe checkout sessions expire <session id>` (the session id is in the `payments` table: `docker compose exec db psql -U postgres ecommerce -c "select order_id, stripe_checkout_session_id, status from payments"`).
6. To test duplicates, run `stripe events resend <event id>`.

Without the Stripe CLI the endpoint can still be checked with a wrong signature: `curl -i -X POST localhost:8000/webhooks/stripe -H "Stripe-Signature: t=1,v1=bad" -d '{}'` gives 400 (or 503 while the secret is empty).

### Key design decisions (M8)

- **Decisions CLAUDE.md and the milestone did not cover:**
  - `handle_stripe_event` takes the `db` session as its first argument (see above).
  - Failures are reported by raising `HTTPException` (400, 503, 500), like the other services.
  - The event is converted with `event.to_dict()` and read with plain `.get()` calls. In SDK 16.0.0 a `StripeObject` is not a dict and has no `.get`.
  - A session id that is missing or not a string is ignored (200). Without this check, a lookup with `None` would turn into `IS NULL` and could match a payment that has no session id yet.
  - A late payment without a payment intent id cannot be refunded: logged as an error, 200.
  - The fallback session id and every other change are only saved by the commit of the branch that acts. Branches that change nothing call `db.rollback()` (this also releases the order lock early).
  - The refund call passes `api_key=settings.STRIPE_SECRET_KEY` (no global key), like the checkout call.
  - The success page polling window was not changed (see the M8 summary).
- **Tests:** `stripe.Refund.create` is patched in an autouse fixture, so the real Stripe API can never be reached. Orders are made through the real checkout API with `stripe.checkout.Session.create` patched. The concurrency tests post from two threads through the `client` (lined up by a `threading.Barrier`, fail if a thread is still alive after 15 seconds) and count the "order paid" / "stock restored" log lines to prove the order was changed exactly once. They passed 20 runs in a row together with `tests/test_checkout_concurrency.py`, and the expired test fails when `FOR UPDATE` is removed from `lock_order`.
- **Not tested here:** the real flow with the Stripe CLI (`stripe listen`, a real payment, `stripe events resend`) needs the CLI and a webhook secret; see "Local webhook setup".

## Order lifecycle (M9)

### Allowed order changes (everything else is 409)

| From | To | Who | Side effects |
|---|---|---|---|
| `pending_payment` | `paid` | Stripe webhook only (M8) | none |
| `paid` | `shipped` | seller (only when every item in the order is theirs) or admin | none |
| `shipped` | `delivered` | seller (same rule) or admin | none |
| `pending_payment` | `cancelled` | the customer who owns the order, or an admin | stock restored, payment `failed`, Stripe session expired |
| `paid` | `cancelled` | the customer who owns the order, or an admin | stock restored, full Stripe refund |

`shipped` and `delivered` orders can never be cancelled (no returns). Sellers cannot cancel; customers cannot change a status. Every code path that changes an order locks the order row first (`order_repository.lock_order`, `SELECT ... FOR UPDATE`) and reads the status again inside the lock.

### Payment status `refunded`, and `stripe_refund_id`

`payments.status` now also allows `refunded`; `payments.stripe_refund_id` holds the Stripe refund id (NULL when Stripe said the charge was already refunded). A paid-then-cancelled order is `cancelled` with payment `succeeded` from the moment of the cancel until the refund is really done; then the payment becomes `refunded`. `order_repository.mark_payment_refunded` is one atomic `UPDATE ... WHERE id = ? AND status <> 'refunded'`, so a second call can never erase the refund id.

### The cancel flow (`order_lifecycle_service.cancel_order`)

`POST /orders/{order_id}/cancel`. The role check (customer or admin, otherwise 403) is inline in the service. `REFUND_KEY_PREFIX = "cancel-refund-"` is the constant at the top of the file.

**Stage 1, one transaction:** lock the order (a customer only finds their own: `lock_order(db, order_id, user_id)`, so someone else's order is never even locked; not found is 404), read the status in the lock, load the payment and the items. Then by status:
- `shipped` / `delivered`: 409 "A shipped order can no longer be cancelled."
- `cancelled`: if the payment is not `succeeded` (failed or refunded), 200 and nothing changes (a double click is harmless). If it is `succeeded` a refund is still owed: the **retry refund** path. It checks the Stripe key rule (503) and that a payment intent exists, then jumps to stage 2 step g.
- `pending_payment`: order `cancelled`, payment `failed`, stock restored, `updated_at` set, commit.
- `paid`: BEFORE changing anything the Stripe key rule (empty key or a key that does not start with `sk_test_`: 503, nothing changed) and the payment intent check (none: logged, 409 "This order has no payment to refund. Please contact support.") run. Then the order becomes `cancelled`, the stock is restored, commit. The payment stays `succeeded`.

Stock is restored with one atomic `UPDATE products SET stock = stock + n` per product (`product_repository.increase_stock`), in ascending product id order, like the M8 webhook.

**Stage 2, after the commit, no transaction open:**
- f. A cancelled `pending_payment` order with a Stripe session id: `stripe.checkout.Session.expire(session id)` (10 second timeout, `api_key=settings.STRIPE_SECRET_KEY`). A `stripe.StripeError` is only logged as a warning (only the error class name; Stripe error text can contain part of a key). It is safe because a customer who still pays is refunded by the M8 late-payment refund (the safety net). No session id, or a key that is not a test key: no call.
- g. If a refund is owed: `stripe.Refund.create(payment_intent=..., idempotency_key="cancel-refund-<order id>")` (10 second timeout). Success: a small transaction sets the payment to `refunded` and saves `stripe_refund_id`. `charge_already_refunded` (`error.code`): counts as success, `refunded`, no refund id. Any other `stripe.StripeError`: logged (class and code, never the text or a key), then **502** "Your order has been cancelled, but the refund could not be completed yet. Open the order and press Retry refund." The cancellation stays committed.
- h. 200 `{order_id, status, payment_status}` with the final statuses.

**Why the commit comes before the Stripe call.** A database transaction must never stay open during a network call (it would hold the order and product locks for up to the timeout). The database is the source of truth: if Stripe fails after the commit, the order is correctly cancelled and the stock is back, and the only thing missing is the money, which the "retry refund" path (the same endpoint, pressed again by the customer or an admin) can finish safely because the idempotency key is the same. The other order (Stripe first, then commit) could refund money for an order that is still paid in our tables.

### Status changes (`order_lifecycle_service.update_order_status`)

One function shared by `PATCH /seller/orders/{id}/status` and `PATCH /admin/orders/{id}/status` (the router passes the logged-in user; the seller router uses `require_seller`, the admin router `require_admin`). The body is `{"status": "shipped" | "delivered"}` (a `Literal`: `paid`, `cancelled`, `pending_payment` and `banana` are 422). Steps: lock the order and read the status in the lock; load the seller of every line and the payment; for a seller (a) not visible gives 404 "Order not found", (b) lines of other sellers give 403 "This order includes products from other sellers. Only an admin can update its status."; an order already in the requested status gives 200 and changes nothing; only `paid` to `shipped` and `shipped` to `delivered` are allowed, everything else is 409 "Cannot change an order from <current> to <requested>."; then save and commit.

### Seller visibility and mixed orders

A seller sees an order only if (a) its payment status is `succeeded` or `refunded` (so abandoned and unpaid checkouts never appear) and (b) at least one line is theirs (an `EXISTS` condition on `order_items` joined to `products.seller_id`). Everything else is 404. A seller sees only their own lines (never the other sellers' lines) and never the customer's email, but they do see the shipping address. A cancelled order whose payment is `refunded` is still visible (cancelled, payment `failed` is not). One order can hold products of several sellers but has one status, so a seller can change the status only when every line is theirs: `has_other_sellers` is true when the order has more lines than the seller has; then only an admin can change the status. The lists load lines and products with `selectinload(Order.items).joinedload(OrderItem.product)` (3 queries per page, no query per order). Neither seller nor admin responses contain Stripe ids or password hashes; seller responses never contain the customer email.

### Lock order (why there is no deadlock)

An order row is locked BEFORE its products are changed, and products are changed in ascending product id order. Checkout locks the cart row and then the product rows, and creates the order only after the products are locked, so no checkout transaction ever waits for an order lock while holding product locks; the webhook and the cancel/status paths lock the order row first and then touch products (atomic increments, ascending id). A product edit (`PATCH` / `DELETE /products/{id}`, M9) locks only one product row. So no cycle can form: orders (lowest id first inside one order) -> products (ascending id), and checkout never goes from products to orders while another transaction goes the other way.

### Product edits are locked too

`product_service.update_product` and `deactivate_product` now call `product_repository.lock_products(db, [product_id])` (the existing `SELECT ... FOR UPDATE` query) first, so a seller's stock edit cannot interleave with a checkout reserving the same stock. Role (403) is checked before the lock; early exits call `db.rollback()` to release it. `GET /seller/products/{id}` (new) does not lock.

### Where 403, 404, 409, 502 and 503 come from

- **403:** wrong role (`require_*` or the inline checks); a seller changing the status of a mixed order.
- **404:** ownership and visibility failures: someone else's order (`/orders/{id}`, cancel), an order a seller may not see, someone else's product, a missing resource.
- **409:** invalid status change, cancelling a shipped or delivered order, a paid order without a payment intent.
- **502:** the refund call failed after the cancellation was committed (cancel, retry refund); the checkout Stripe call failed (M7, cart restored).
- **503:** Stripe not configured or not a test key: checkout (before any database work), refund paths of cancel (nothing changed), webhook secret empty, `/health` database down.

### Key design decisions (M9)

- **Decisions CLAUDE.md and the milestone did not cover:**
  - "shipped to paid" cannot be asked for: the request body only accepts `shipped` and `delivered`, so `paid` is a 422, not a 409. The test checks the 422 and that the order is unchanged.
  - `lock_order` got an optional `user_id` (a customer's cancel only locks their own order).
  - `mark_payment_refunded` is an atomic UPDATE (see above); the late-payment webhook uses it too.
  - The webhook treats `charge_already_refunded` as success (the milestone only asked for it in the cancel path), so the duplicate/late combination cannot make Stripe retry forever.
  - A pending cancel only calls `Session.expire` with an `sk_test_` key (the same test-key rule as everywhere, so a live key can never be used).
  - The retry-refund path also checks for a payment intent (409 if missing), like the paid path.
  - Admin `item_count` is the total quantity (same meaning as in `GET /orders`). The admin detail also repeats `item_count`, `customer_email` and `shipping_full_name` from the list item.
  - The seller product form (create mode) calls `GET /users/me` once, only so a non-seller sees "This page is for seller accounts."; the form's price and stock also have the database integer limit as an upper bound (otherwise a huge number would be a 500).
  - The retry-refund and cancel buttons use the same endpoint; on the admin page a 502 just shows the message (the button comes back, so pressing it again is the retry).
  - A concurrent cancel of a `pending_payment` order while checkout stage 2 is still creating the Stripe session: the payment has no session id yet, so nothing is expired; the session that checkout creates a moment later stays open until it expires by itself, and if it is paid anyway the M8 late-payment refund returns the money.
- **Tests:** `tests/test_order_cancel.py` (21), `tests/test_order_status.py` (33), `tests/test_order_lifecycle_concurrency.py` (3: cancel against ship, two cancels, cancel of a pending order against the `completed` webhook; they passed 20 runs in a row; with `FOR UPDATE` removed from `lock_order`, 2 of the 3 failed in every one of 6 runs), plus two changed and one new M8 webhook test. `Session.expire` and `Refund.create` are patched in autouse fixtures.
- **Tested by hand** (headless Chrome driven with Playwright from a temporary virtual environment outside the project): every new page as seller, admin and customer (the "for ... accounts" messages for the wrong role), mixed and single-seller orders, Mark as shipped and delivered as seller and as admin, customer cancel of an unpaid order (`confirm()` text, order cancelled, payment Failed), customer cancel of a paid order with a fake payment intent (Stripe refused: the 502 message, "Reload", then "Refund pending" with "Retry refund"), `<script>` text in a product name and an address shown as plain text, the product form (all validation messages, a rejected image URL, create, edit, deactivate and activate, the product leaving and returning to the storefront search), 375px wide pages without sideways scrolling. **Full run with a real `sk_test_` key and `stripe listen` (Stripe CLI 1.53.1, run from a temporary folder, key passed through `STRIPE_API_KEY`), card 4242 on the hosted Stripe page, driven with Playwright:** a mixed order (one product of each seller) became Paid through the real webhook; seller1 saw only their own line, `has_other_sellers` true, no "Mark as shipped" and no customer email; the admin shipped and delivered it and the customer's My Orders followed; a single-seller order was shipped and delivered by its seller and a cancel by the customer was refused (409, no button); a paid order cancelled by the customer ended `cancelled` / `refunded` with the refund id saved, the stock back, and the charge shown as refunded in Stripe (`refunded: true`, full amount); an unpaid order cancelled by the customer had its stock back and the Checkout Session `expired` in Stripe (the `checkout.session.expired` event then arrived and changed nothing); `stripe events resend` of a `completed` event changed nothing. The dev database was restored to its seeded state afterwards.

**Dev gotcha found during the run:** checkout uses `order-<id>` as the Stripe idempotency key, and Stripe remembers a key for 24 hours. After resetting or restoring the dev database the order id counter starts again, and a new order can reuse a key with different parameters: Stripe answers 400 (idempotency error), checkout returns 502 and the order is cancelled (the failure path worked as designed). Fix for dev: `SELECT setval('orders_id_seq', 6000)` (the dev counter was set to 6000 after the run). Not a problem on a database that is never reset.

### Notes for M10 (done)

The M9 hand-off notes for M10 (the table of endpoints with their rules, the things to check, the indexes the seller queries rely on, and the README requirements) have all been dealt with: the endpoint rules are in "Security model (M10)", the indexes were measured in "Performance review (M10)" (the guess that `order_items.order_id` and the order sort had no index was right, and both were fixed), and the README is `README.md`.

## Security model (M10)

### Access rule of every endpoint (the inventory)

This is the same list as `ENDPOINTS` in `tests/test_endpoint_security.py`, which fails when an endpoint is added without a decision (and when this list has an entry that no longer exists). The access words are: `public`, `signature` (the Stripe webhook), `any_user`, `customer`, `seller`, `admin`, `customer_or_admin`, `seller_or_admin`. 38 endpoints.

| Method and path | Access | Ownership / visibility |
|---|---|---|
| GET `/health` | public | none |
| POST `/auth/register` | public | none (role `customer` or `seller` only) |
| POST `/auth/login` | public | none |
| GET `/users/me` | any_user | own user |
| PATCH `/users/me` | any_user | own user (name only) |
| GET `/users/me/addresses` | any_user | own addresses |
| POST `/users/me/addresses` | any_user | own addresses |
| PUT `/users/me/addresses/{address_id}` | any_user | own address, otherwise 404 |
| DELETE `/users/me/addresses/{address_id}` | any_user | own address, otherwise 404 |
| GET `/admin/users` | admin | all users |
| GET `/admin/orders` | admin | all orders |
| GET `/admin/orders/{order_id}` | admin | any order |
| PATCH `/admin/orders/{order_id}/status` | admin | any order |
| GET `/categories` | public | none |
| POST `/categories` | admin | none |
| PUT `/categories/{category_id}` | admin | none |
| DELETE `/categories/{category_id}` | admin | none |
| GET `/products` | public | active products only |
| GET `/products/{product_id}` | public | active products only (inactive: 404) |
| POST `/products` | seller | `seller_id` is the caller |
| PATCH `/products/{product_id}` | seller_or_admin | a seller only their own (404 otherwise), admin any |
| DELETE `/products/{product_id}` | seller_or_admin | same as PATCH |
| GET `/seller/products` | seller | own products |
| GET `/seller/products/{product_id}` | seller | own product, otherwise 404 |
| GET `/seller/orders` | seller | paid orders (payment `succeeded` or `refunded`) with at least one of the seller's products, own lines only |
| GET `/seller/orders/{order_id}` | seller | same visibility, otherwise 404 |
| PATCH `/seller/orders/{order_id}/status` | seller | same visibility (404), every line must be theirs (403) |
| GET `/cart` | customer | own cart |
| DELETE `/cart` | customer | own cart |
| GET `/cart/count` | customer | own cart |
| POST `/cart/items` | customer | own cart |
| PATCH `/cart/items/{product_id}` | customer | own cart |
| DELETE `/cart/items/{product_id}` | customer | own cart |
| POST `/orders/checkout` | customer | own cart and own address (404) |
| GET `/orders` | customer | own orders |
| GET `/orders/{order_id}` | customer | own order, otherwise 404 |
| POST `/orders/{order_id}/cancel` | customer_or_admin | a customer only their own order (404), admin any |
| POST `/webhooks/stripe` | signature | the Stripe signature, checked on the raw bytes |

Not listed (not API endpoints): `/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`, `/static/...` and the HTML pages.

The tests behind this: `test_endpoint_security.py` (inventory equals the real routes; no token and a garbage token give 401 on every protected endpoint; each role gets 403 where it is not allowed and anything but 401 and 403 where it is; a deactivated user's valid token gives 401 everywhere; wrong secret, `alg: none`, missing `exp`, expired, non-numeric `sub`, missing `sub` and a different algorithm all give the same 401), `test_idor.py` (one customer or seller against another's data: 404 and nothing changed), `test_no_leaks.py` (raw text of every GET response).

### Status codes and when each is used

| Code | Used for |
|---|---|
| 400 | A bad Stripe webhook (missing or wrong signature, old timestamp, body that is not JSON); an empty cart at checkout; a category id that does not exist when making a product |
| 401 | No token, a bad, expired or forged token, a user that no longer exists or is disabled: always `{"detail": "Not authenticated"}` with `WWW-Authenticate: Bearer`. Also a wrong email or password at login (`"Incorrect email or password"`, identical for unknown email and wrong password) |
| 403 | Logged in but the wrong role; a seller changing the status of an order that has other sellers' products; a disabled account that gave the right password at login |
| 404 | The resource does not exist **or is not yours / not visible to you** (other people's addresses, orders, products, cart lines; orders a seller may not see; inactive products); unknown category slug; unknown HTML page (the friendly `404.html`) |
| 409 | Conflicts and refused changes: duplicate email or category, a stock or cart limit, an invalid order status change, cancelling a shipped order, an order total above 99,999,999 paise, a paid order without a payment intent to refund |
| 413 | A request whose `Content-Length` is above 1,000,000 bytes (the body is not read) |
| 422 | Bad input: failed validation (type, length, number range), a NUL character or a number the database refuses (the `DataError` handler: `{"detail": "Invalid input"}`), password rules, a name without letters or digits |
| 500 | Only for unexpected errors: `{"detail": "Internal server error"}`. The one deliberate exception is the Stripe webhook, which answers 500 `"Refund failed, please retry"` or a retryable failure so that Stripe delivers the event again |
| 502 | A Stripe call failed: the Checkout Session at checkout (cart restored), or the refund after a cancel (the order stays cancelled, "Retry refund") |
| 503 | Not configured: no or non-test `STRIPE_SECRET_KEY` (checkout and refunds), empty `STRIPE_WEBHOOK_SECRET` (webhook), or `/health` when the database cannot be reached |

### Headers, CSP and the middleware

`app/main.py` has one HTTP middleware, `protect_every_request`, written as plain steps: (1) a `Content-Length` above `MAX_BODY_BYTES` (1,000,000) gives 413 without reading the body (a chunked upload without `Content-Length` is not covered); (2) call the app; (3) add `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` and `Permissions-Policy: camera=(), microphone=(), geolocation=()` to every response; (4) add the Content-Security-Policy to every response except paths starting with `/docs` or `/redoc` and `/openapi.json`.

```
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: data:; connect-src 'self';
form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'
```

- **Why `/docs` is excluded:** Swagger UI loads its scripts and styles from a CDN and runs an inline script, so the policy would break the page. The other four headers still apply there. (Checked in headless Chrome: `/docs` renders all 38 operations.)
- **Why `img-src` allows `https:`:** a seller may use any `https://` image URL for a product (and the seed uses picsum.photos). Images cannot run script, so this is the one wide setting.
- **No inline script or style anywhere:** the pages use `<script src>` and one stylesheet only, with no `on...=` attributes and no `style=` attributes (checked by search; the JS never touches `.style`). `data-requires-login` is a data attribute, not script.
- **No HSTS** on purpose (it belongs behind HTTPS at deploy time).
- **The 500 handler adds the same headers itself:** Starlette's `ServerErrorMiddleware` (which calls the `Exception` handler) wraps the user middleware, so a 500 response would not get them otherwise. The headers live in two constants (`SECURITY_HEADERS`, `CONTENT_SECURITY_POLICY`) used by both.
- **No CORS middleware.** The frontend is served by this app (same origin). Nothing in the code base mentions CORS, and tests check that a request with an `Origin` header and an `OPTIONS` preflight never get `Access-Control-Allow-Origin`.

### Exception handlers

- `Exception`: `logger.exception(...)` (traceback in the log only), response `500 {"detail": "Internal server error"}`. Tests use `TestClient(app, raise_server_exceptions=False)` and check that no SQL, path, `Traceback` or exception text reaches the client.
- `sqlalchemy.exc.DataError`: a value the database refused because of user input. An experiment with the installed versions (SQLAlchemy 2.1.4, psycopg 3.3.6) showed that **both** a NUL character in text (`psycopg.DataError`) and an out-of-range integer (`psycopg.errors.NumericValueOutOfRange`, a subclass of `DataError`) arrive as `sqlalchemy.exc.DataError`. The handler logs only the error class and answers `422 {"detail": "Invalid input"}`. It is a safety net: the schemas and path parameters have bounds, so normal bad input is stopped earlier with a precise 422.
- `get_db` closes the session in a `finally`, so a failed request never leaks a connection or leaves a transaction open (a test checks that the pool has no checked-out connection after a `DataError`).
- Every other error keeps FastAPI's normal `{"detail": ...}` shape.

### Input bounds

Every string has a `max_length` that fits its column and a sensible minimum, and every integer has `ge` and `le` that fit its column (int4 maximum 2,147,483,647). The M3 product schema and the M5 price filters were tightened to these caps.

| Input | Limit |
|---|---|
| Names (user full name, address full name, product name) | 1 to 200 |
| Category name | 1 to 100 (also needs a letter or digit) |
| Descriptions (product 1 to 5000, category up to 5000) | 5000 |
| Address lines, `line1` and `line2` | up to 200 |
| City, state, country | 1 to 100 |
| Phone | 1 to 20 |
| Postal code | 1 to 12 |
| Email | up to 255 (and a valid address) |
| Register password | 8 to 72 characters (and at most 72 bytes, no NUL character) |
| Login email / password | up to 255 / up to 128 (a password over 72 bytes, or with a NUL, is a 401) |
| Image URL | `http://`, `https://` or `/static/images/`, up to 500 |
| Search `q` / `category` slug | up to 100 / up to 100 |
| Product `price` | 1 to 10,000,000 paise (₹1,00,000) |
| Product `stock` | 0 to 1,000,000 |
| `min_price`, `max_price` filters | 0 to 1,000,000,000 paise |
| `page` | 1 to 100,000 |
| `page_size` | 1 to 100 |
| Cart `quantity` | 1 to 10 |
| Every id in a path or body (`product_id`, `order_id`, `address_id`, `category_id`) | 1 to 2,147,483,647 |
| Order total | at most 99,999,999 paise (`MAX_ORDER_TOTAL` in `checkout_service.py`) |
| Request body | at most 1,000,000 bytes (by `Content-Length`) |
| Webhook `metadata.order_id` | 1 to 9 ASCII digits, otherwise acknowledged with 200 and ignored |

Pydantic's normal conversion still accepts a numeric string such as `"5"` for an integer field (strict mode would change the behaviour of every endpoint). A string that is not a number, a list, an object or `null` gives 422.

**Money columns.** `products.price`, `order_items.unit_price`, `orders.total_amount` and `payments.amount` are all `INTEGER` (int4, up to 2,147,483,647). Largest values the app can write: a price is at most 10,000,000, a line is at most 10 units (cart limit), and the order total is refused above 99,999,999 **before anything is written** (the total is added up in Python, which has no overflow). `payments.amount` copies `total_amount`. So no allowed combination can reach the int4 limit, with a margin of more than 20 times. **No migration was needed.** (Before M10 a seller could set a price of 2,147,483,647 and a customer could buy several, which Python summed without trouble but Postgres would have refused with a 500. The new caps close that.)

### Timing protection and token handling

- **Login timing.** When the email does not exist, login still runs one `bcrypt.checkpw` against `DUMMY_PASSWORD_HASH`, a module constant made once with `bcrypt.gensalt()` (the same cost factor, 12 rounds, as real passwords). A test counts `bcrypt.checkpw` calls for a wrong password and for an unknown email and expects one each. The messages are identical.
- **Tokens.** `jwt.decode(..., algorithms=["HS256"], options={"require": ["sub", "exp"]})`; the user is loaded from the database on every request, so `role` and `is_active` never come from the token. Every failure is the same 401.
- **Passwords with a NUL character.** bcrypt silently stops reading a password at a NUL, so a password such as `Pass\0word` would have been stored as `Pass`. Register now refuses it (422) and login gives 401. Found by the NUL test of this milestone.
- **JWT secret.** `JWT_SECRET: str = Field(min_length=32)` with no default. The app, Alembic and the tests fail at startup with a pydantic validation error when it is missing or short (`.env.example` holds the placeholder `REPLACE_ME`, which is too short on purpose).

### Logging

`main.py` calls `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")` once. Searched the whole code base: log lines carry only ids, event types, outcomes, error class names and Stripe error codes. No password, token, authorization header, Stripe key, webhook secret, signature, request body or email is logged, and there is no `print` left (the seed script now reports through `logging`). The engine is created with `hide_parameters=True`, so a failed statement's values (a password hash, an email) never appear in SQLAlchemy's error text. A test (`test_webhooks.py::test_nothing_sensitive_is_logged`) still checks the webhook logs.

### Accepted gaps (not built on purpose)

- **No login rate limiting.** The next step would be a Postgres-based throttle or a reverse proxy.
- **No token revocation and no refresh tokens.** A token lives for `JWT_EXPIRE_MINUTES`. (A disabled user is refused at once, because the user is loaded on every request.)
- **Registration reveals whether an email exists** (409).
- **The token lives in `localStorage`.** A cross-site scripting bug could read it. The mitigations are the CSP, `textContent`-only rendering and the short expiry. httpOnly cookies would need CSRF protection and are out of scope. CSRF does not apply to the API, because it uses a bearer header and not cookies.
- **No HSTS / HTTPS** (deployment).
- **Chunked uploads** without `Content-Length` are not limited by the 413 check.
- **`img-src https:`** lets a page show an image from any https host (a seller's choice of image URL).
- **`statement_timeout` also covers waiting for a row lock.** A request that waits more than 15 seconds for a lock fails with a generic 500. Locks are held for milliseconds, and the concurrency tests pass under the timeout.

## Performance review (M10)

Measured on Postgres 16 in the `db` container (default settings), with a temporary dataset inside a transaction that is rolled back, so nothing remains in the dev database (after the run: `VACUUM (FULL, ANALYZE)`, and the counts were products 120, users 5, orders 0, order_items 0, payments 0, carts 0, cart_items 0, addresses 2, categories 10, the same as before; the id sequences were set back to their old values, because Postgres does not roll them back).

**Dataset** (`setup.sql`, plain SQL, kept outside the project): 200 customers, 50,000 products (alternating between the two seeded sellers, rotating through the categories, as in M5), 20,000 orders spread over the 200 customers (100 each, oldest first, one new minute per order) with the five statuses in turn (4,000 each), one payment per order (`succeeded` for paid, shipped and delivered; `pending` for pending_payment; `refunded` or `failed` for cancelled) and 3 order items per order (60,000, products from all over the table). Then `ANALYZE` of the five tables. The ids of the sample rows are looked up with `\gset` in the script.

**Commands**

```bash
docker compose cp setup.sql db:/tmp/perf/setup.sql
docker compose cp measure.sql db:/tmp/perf/measure.sql        # BEGIN; \i setup.sql; \gset variables; EXPLAIN (ANALYZE, BUFFERS) ... twice; ROLLBACK;
docker compose exec -T db psql -U postgres ecommerce -f /tmp/perf/measure.sql
docker compose exec -T db psql -U postgres ecommerce -c "VACUUM (FULL, ANALYZE)"
docker compose exec -T db psql -U postgres ecommerce -c "select count(*) from products"   # must print 120
```

**The SQL is the real SQL.** A throwaway script (outside the project) ran the real repository functions on the same data inside a rolled back transaction and captured every statement they send (a `before_cursor_execute` listener; `selectinload` sends its own `... WHERE order_id IN (...)` query). The statements were copied into `measure.sql`, with the ids replaced by psql variables. Each statement ran twice; the table reports the second (warm) run. Index experiments (variants with different index sets, each created inside the rolled back transaction) were run first, to decide which indexes earn their place.

**Results.** "Before" is the schema as of M9, "after" is with migration `e918e5dbff2d`.

| Query (real SQL from the repository) | Plan before | Time before | Plan after | Time after |
|---|---|---|---|---|
| Customer order list, page (one user, newest first, limit 10) | Bitmap scan on `ix_orders_user_id` + sort of that user's 100 orders | 0.20 ms | Index scan on `ix_orders_user_id_created_at_id`, no sort | **0.035 ms** |
| Customer order list, items of the page | **Seq Scan** on `order_items` (60,000 rows) | 5.25 ms | Bitmap scan on `ix_order_items_order_id` | **0.075 ms** |
| Customer order list, count | Bitmap scan on the user index | 0.20 ms | Bitmap scan on the new user index | 0.20 ms (unchanged) |
| Order detail: the order / the items / the payment | pkey / **Seq Scan** / unique index | 0.016 / 4.14 / 0.019 ms | pkey / index scan on `ix_order_items_order_id` / unique index | 0.016 / **0.013** / 0.014 ms |
| Seller order list, page (limit 10) | Parallel hash joins that read **all** of orders, payments, order_items and products (the half of the products that belong to the seller), then a sort | 40.8 ms | Walks `ix_orders_created_at_id` newest first and checks each order through `payments_order_id_key`, `ix_order_items_order_id` and `products_pkey`; stops after 10 matches | **0.256 ms** |
| Seller order list, items and products of the page | Seq Scan on `order_items` + pkey lookups | 5.99 ms | Bitmap scan on `ix_order_items_order_id` + pkey lookups | **0.103 ms** |
| Seller order list, count | The same full parallel hash joins (every matching order must be counted) | 37.4 ms | Same full scan | 32.8 ms (still a full scan) |
| Admin order list, no filter, page (limit 20) | Seq Scan on all 20,000 orders + hash join + sort | 13.6 ms | Walks `ix_orders_created_at_id`, nested loop to `users_pkey` | **0.068 ms** |
| Admin order list, no filter, items of the page | Seq Scan on `order_items` | 5.54 ms | Bitmap scan on `ix_order_items_order_id` | **0.050 ms** |
| Admin order list, no filter, count | Seq Scan on `orders` | 3.93 ms | Seq Scan on `orders` | 2.90 ms (unchanged) |
| Admin order list, `status = 'paid'`, page | Bitmap scan on `ix_orders_status`, hash join, sort of 4,000 rows | 4.69 ms | Walks `ix_orders_created_at_id` and filters the status (1 in 5), nested loop to users | **0.101 ms** |
| Admin order list, `status = 'paid'`, items of the page | Seq Scan on `order_items` | 5.31 ms | Bitmap scan on `ix_order_items_order_id` | **0.052 ms** |
| Admin order list, `status = 'paid'`, count | Bitmap scan on `ix_orders_status` | 2.56 ms | Seq Scan on `orders` (the planner's choice) | 2.50 ms (unchanged) |
| Cart read (5 lines) | pkey lookups for the products | 0.042 ms | same | 0.044 ms |
| Stock lock, 3 products (`FOR UPDATE`) | `products_pkey` | 0.033 ms | same | 0.035 ms |
| Stock restore (one `UPDATE products SET stock = stock + 1`) | `products_pkey` (2 foreign key triggers 0.05 ms) | 0.106 ms | same | 0.105 ms |
| Order lock (`FOR UPDATE`) | `orders_pkey` | 0.020 ms | same | 0.018 ms |

**Decisions**

- Added (one migration, `e918e5dbff2d`, with a working downgrade; checked: `upgrade`, `downgrade -1`, `upgrade`, and `alembic check` reports no drift):
  - `ix_order_items_order_id` on `order_items (order_id)`. Foreign keys do not get an index in Postgres. It fixed five sequential scans of 4 to 6 ms (they grow with the table), including the order detail page.
  - `ix_orders_created_at_id` on `orders (created_at DESC, id DESC)`. The seller and admin lists went from a full scan and a sort (40.8 ms and 13.6 ms) to reading the first rows of the index (0.26 ms and 0.07 ms).
  - `ix_orders_user_id_created_at_id` on `orders (user_id, created_at DESC, id DESC)`, which **replaces** `ix_orders_user_id` (dropped in the same migration; a leading `user_id` makes the old index redundant). It was added because the measurement showed a side effect of the previous index: with only the two indexes above, the planner started to walk the global `created_at` index for a customer's list and filter by user, which made that list slower (0.20 ms to 1.0 ms). With the composite index the customer list takes 0.035 ms and the plan no longer depends on guesses. A customer with one old order took 0.025 ms either way.
- Considered and **not** added, because the measurement showed no gain:
  - `order_items (product_id)`: no plan changed with it (the seller queries still take the same plan; the seller count stayed at 37 to 40 ms with and without it). Nothing deletes a product (soft delete), so the foreign key check never needs it.
  - `addresses (user_id)` and `cart_items (product_id)`: the tables are tiny per user and no query is slow. They are the first candidates when the tables grow large. `cart_items (cart_id)` is already the left part of the unique constraint `uq_cart_items_cart_id_product_id`.
  - `ix_orders_status` stays (the paid-orders count can use it); it is not used by the page queries any more.
- **Still a full scan, on purpose:** `count(*)` queries (the seller count at about 33 ms for 20,000 orders is the slowest). A count has to visit every matching row, so an index cannot help. If it ever matters, the usual fixes are a cached or estimated total, or "next page" paging without a total; neither is in scope.
- Already fast, left alone: the cart read, the stock lock and restore, the order lock and the order detail row.

**Every index in the database, and why it exists**

| Table | Index | Why |
|---|---|---|
| users | `users_pkey` (id) | primary key, `get_current_user` on every request |
| users | `users_email_key` (email, unique) | login and duplicate-email check |
| addresses | `addresses_pkey` | primary key |
| categories | `categories_pkey`, `categories_name_key`, `categories_slug_key` | primary key, unique name and slug (the slug lookup of `?category=`) |
| products | `products_pkey` | primary key, detail page, locks, order lines |
| products | `ix_products_category_id` | category filter, foreign key |
| products | `ix_products_price` | price range filter and price sort |
| products | `ix_products_seller_id` | `/seller/products`, the seller checks of the order queries, foreign key |
| products | `ix_products_search_vector` (GIN) | full-text search |
| products | `ix_products_active_newest` (partial) | newest-first listing of active products |
| carts | `carts_pkey`, `carts_user_id_key` (unique) | one cart per user, lookup by user |
| cart_items | `cart_items_pkey`, `uq_cart_items_cart_id_product_id` | primary key; one line per product per cart, and lookup by cart |
| orders | `orders_pkey` | primary key, order detail, `FOR UPDATE` lock |
| orders | `ix_orders_user_id_created_at_id` | the customer's own order list (and the foreign key to users) |
| orders | `ix_orders_created_at_id` | seller and admin order lists, newest first |
| orders | `ix_orders_status` | status filter and count of the admin list |
| order_items | `order_items_pkey` | primary key |
| order_items | `ix_order_items_order_id` | loading the lines of an order, the seller EXISTS check, the foreign key |
| payments | `payments_pkey` | primary key |
| payments | `payments_order_id_key` (unique) | one payment per order, joins from orders |
| payments | `payments_stripe_checkout_session_id_key` (unique) | the webhook finds the payment by session id |

## Hardening and audit decisions (M10)

**Fixed**
- App-wide: size limit, security headers and CSP, 500 and `DataError` handlers (an unexpected error is a plain JSON 500; bad values that reach the database are 422), required `JWT_SECRET` of 32 or more characters, a 15 second `statement_timeout` (constant `STATEMENT_TIMEOUT_MS` in `db.py`; the tests' engine uses the same value; `pool_pre_ping` was already on), `hide_parameters=True`, one logging format, no `print`.
- Auth: dummy-hash login check, NUL in passwords, an upper limit on login email and password length.
- Input bounds on every schema, path and query (see the table above); product price and stock caps; `min_price`/`max_price` cap 1,000,000,000; `page` cap 100,000; `category` slug length. The frontend forms got the same limits (`maxlength`, the price and stock checks in the seller product form, the price filter on the products page).
- Checkout total cap (`MAX_ORDER_TOTAL`, step f2, 409, nothing written). Webhook `metadata.order_id` is now 1 to 9 digits (before: up to 10 digits and at most 2,147,483,647).
- Indexes (see the performance review).
- Frontend audit (searched every HTML and JS file): no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`, `setAttribute("on...")` or `setAttribute("style")`; no inline event attributes, inline scripts or styles, `style=""` attributes or `javascript:` URLs; no `target="_blank"` anywhere; no `http://` URL except the XML namespace inside `placeholder.svg`; no `console.*`, `alert`, `debugger` or TODO. Fixed: the `next` redirect check is now the same condition in `login.js`, `register.js` and `addresses.js`; error and status areas are live regions (`role="alert"` on error paragraphs and `aria-live="polite"` on the areas that show loading, empty and error states); a `data:` favicon link on every page (the browser's automatic `/favicon.ico` request was a console error); new `frontend/404.html`. The checkout redirect still accepts only `https://checkout.stripe.com/`.
- Accessibility pass (by reading, no tooling): every form control has a `<label>` or `aria-label` (checkbox and radio inputs sit inside their label), every image has `alt`, every page has `<title>`, `lang="en"` and exactly one `<h1>` (on the product, order and seller/admin order pages the JS creates it), buttons are `<button>` elements.
- Code audit: no helper functions and no same-layer calls in `routers`, `services` or `repositories` (checked with a throwaway `ast` script: the only module-level functions outside the layers are the `get_db` dependency, the four `core/dependencies.py` dependencies, `health` and the three functions of `main.py` that this milestone allows). One violation found and fixed: `order_service.py` used `sorted(..., key=lambda ...)` four times; the order lines now come back sorted from `Order.items = relationship(order_by="OrderItem.id")`. Removed: unused imports (`text`, `joinedload`, an unused `Address` import in a test), the two stale `.gitkeep` files, and the `print` calls in `seed.py`. The JS files each hold one page function (plus `apiRequest`, `buildProductCard`, `showLayout` and `loadCart`); the event callbacks are the browser's own way of working. No unused CSS class is left (the `badge-*` classes are built from the status in the JS).
- `pip-audit` (run once, not added to `requirements.txt`): see below.
- Docker: non-root user (uid 1000), `.dockerignore`, a healthcheck on the app, Postgres port closed.

**Left as it is, and why**
- `GET /products?q=%00` answers **200 with an empty list**, not a 4xx: the behaviour rule of this milestone says a search with bad characters is "a normal empty result", and the M5 rule already stripped NUL characters. It is never a 500.
- Numeric strings (`"5"`) are accepted for integer fields (Pydantic's normal conversion).
- `models/order.py` and `models/cart.py` use `Mapped["Product"]` as a string annotation without importing `Product` (pyflakes reports "undefined name"). SQLAlchemy resolves the name from its registry at runtime, it works, and adding `TYPE_CHECKING` imports would be extra code for no gain.
- `app/models/__init__.py` imports every model without using it on purpose (Alembic and `Base.metadata` need them registered).
- The count queries (full scans), the missing `addresses (user_id)`, `cart_items (product_id)` and `order_items (product_id)` indexes: see the performance review.
- No rate limiting, token revocation, refresh tokens or httpOnly cookies (out of scope, see the accepted gaps).
- The `pip` that ships in the `python:3.12-slim` image (25.0.1) has known issues; see the pip-audit result.
- CLAUDE.md rules were not changed. Its facts were brought up to date: the project folder is called `ecom/` (the file said `ecommerce/`), the router list (it said `auth, products, categories, cart, orders, webhooks, admin`; the real ones add `users` and `seller_orders`), the extra files (`seed.py`, `README.md`, `.dockerignore`, `alembic.ini`, `pytest.ini`, `404.html`), the settings list (`TEST_DATABASE_URL`, `JWT_EXPIRE_MINUTES`, the 32 character rule), the order total cap and the real expiry (30 minutes plus one) in the checkout rules, and the `--events` flag of `stripe listen`. The order statuses, payment statuses (with `refunded`), the endpoints and the seller rule already matched.
- Compared the endpoint table with the live `/openapi.json` (38 operations): method and path sets are identical, and the access column matches the inventory above.

**Stability**
- The full suite was run three times in a row and the three concurrency files (`test_checkout_concurrency.py`, `test_webhooks_concurrency.py`, `test_order_lifecycle_concurrency.py`) twenty times in a row; see "Test results" below.

### Test results (M10)

- **299 tests pass** (213 before M10; 86 new: `test_endpoint_security.py` 36, `test_hardening.py` 20, `test_coverage_gaps.py` 14, `test_idor.py` 8, `test_no_leaks.py` 3, `test_query_counts.py` 3, `test_full_flow.py` 1, `test_frontend_files.py` +1).
- **Stability.** The full suite ran three times in a row: 299 passed each time (about 57 seconds each). The three concurrency files (`test_checkout_concurrency.py`, `test_webhooks_concurrency.py`, `test_order_lifecycle_concurrency.py`, 8 tests) ran 20 times in a row: 8 passed every time. Nothing failed, so nothing needed fixing in this step. (During the work itself the new tests failed a few times because of mistakes in the tests, for example a route added after the `/` mount answering 404, a URL longer than httpx allows, and the NUL password case that exposed the real bcrypt problem described above; all were fixed before the runs.)
- **Statement counts** (`test_query_counts.py`): `GET /products`, `/cart`, `/orders`, `/seller/orders` and `/admin/orders` send the same number of SQL statements for 2 rows and for 12 rows. No endpoint needed a fix (they already used `joinedload` and `selectinload`).
- **Coverage** (`pytest --cov=app --cov-report=term-missing`, 299 passed). Per layer, statements covered:

  | Layer | Statements | Covered |
  |---|---|---|
  | services | 730 | **99.6%** (the 3 missed lines are in `webhook_service.py`: a payment whose order row disappeared between two queries, which the foreign key makes impossible) |
  | routers | 189 | 100% |
  | repositories | 214 | 100% |
  | schemas | 238 | 100% |
  | models | 129 | 100% |
  | core (`config.py`, `dependencies.py`) | 46 | 100% |
  | `main.py` and `db.py` | 68 | 100% |
  | `seed.py` (a script that runs when imported; used by hand in the README steps and the fresh-clone check) | 45 | 0% |
  | **Total** | 1,659 | 97% (99.8% without `seed.py`) |

  Before the new tests of this milestone were added, the first run of the coverage report showed 96%, with services at 91 to 100% per file; the 14 tests in `test_coverage_gaps.py` cover the error and permission branches that were missing (registration race, passwords over 72 bytes, sold-out cart changes, empty category slug, category delete race, retry refund without a payment intent, cancel without a test key, the inline role check of the status service, a webhook without a session id, a late payment without a payment intent, `get_db` closing the session, `/health` with the database down).
- **Fresh clone check (the README, step by step).** After `docker compose down -v` for this project, the repository was cloned into a temporary folder (the local repository, with this milestone's uncommitted files copied over it, since a clone of the committed state would not contain them), and the README was followed: `cp .env.example .env`, `openssl rand -hex 32` into `JWT_SECRET`, the Stripe test key, `docker compose up --build`, `alembic upgrade head` (all four migrations ran), `python -m app.seed` ("Seeded 5 users, 10 categories and 120 products"), the site and `/health` answered, `stripe listen --events ... --forward-to ...` printed the signing secret, which was copied into `.env` before `docker compose up -d --force-recreate app`, then a customer paid with 4242 on the real Stripe page and the success page said "Payment received". Then, in the same copy: `docker compose exec app pytest` (299 passed), the coverage command (97%), the 20-run concurrency loop of the README (20 of 20 passed), `docker compose exec --user "$(id -u):$(id -g)" app alembic current`, `docker compose exec db psql ... -c "select 1"`, `stripe events resend <event id>` (pending_webhooks 2) and the "run without reload" command (`/health` answered 200, no reload line in its log). The full browser flow of the previous bullet was run against this copy as well. The copy was stopped with `docker compose down -v` afterwards, and the real project was started again, migrated and seeded (the dev database is in its seeded state; `orders_id_seq` was set to 7100 because Stripe remembers the idempotency keys `order-<id>` of earlier test payments). **Steps that needed a change:** (1) the README's first checkout failed with "Payment service is unavailable" because the fresh database numbered the first order 1 and this Stripe account had already used the key `order-1`; the failure path worked as designed (order cancelled, stock and cart restored), and the README now has a troubleshooting item with the `setval` command; (2) the README said to pass the key to `stripe listen` with `--api-key`, but what was actually run is the `STRIPE_API_KEY` environment variable (or `stripe login`), so the README now says that; (3) the no-reload command needs a few seconds for the database, now noted. The clone used the local repository, not the GitHub URL written in the README, which could not show this milestone's files before they are pushed.
- **Checked by hand** (headless Chrome driven with Playwright from a temporary virtual environment outside the project; Stripe CLI 1.53.1 downloaded from the official GitHub release into a temporary folder, SHA-256 checked against the published checksum file): one full run with a real `sk_test_` key and `stripe listen`: browse, category, search, register, logout and login, add to cart, add an address, cart, checkout, the real Stripe page paid with 4242 (a webhook through `stripe listen` made the success page say "Payment received"), My Orders, order detail, cancel of the paid order (status Refunded), seller dashboard (products, product form, orders, order detail), admin dashboard (orders, order detail, users) and the 404 page: **no CSP violation and no console error** on any of our pages. The only two console lines were the browser's automatic `/favicon.ico` request (fixed with the `data:` icon link) and the deliberate 404 for the unknown page. With the product image hosts blocked, every product card showed `placeholder.svg`. `/docs` rendered all 38 operations. The curl checks: `curl -I /` shows the four headers and the CSP; `GET /products/99999999999` gives 422; `GET /products?q=%00` gives 200 with an empty list; `POST /auth/register` with `\u0000` in the name gives 422; `POST /cart/items` with `product_id` 99999999999 gives 422; none gives a 500.

### pip-audit result

`python -m pip_audit -r requirements.txt --no-deps` (installed in the container with `pip install --user`, never added to `requirements.txt`): **No known vulnerabilities found** in the pinned packages. `python -m pip_audit` on the whole container environment (every transitive package) found issues only in `pip` itself (25.0.1 in the `python:3.12-slim` base image, fixed in 26.x). `pip` is only the installer used when the image is built; it is not in `requirements.txt` and is not used by the running app. It was **not** upgraded (a minor version jump of the base image's tooling, not a safe patch-level change). Run it again at deploy time.

## Docker (M10)

- `Dockerfile`: `python:3.12-slim`, `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`, a user `appuser` with uid 1000, the code copied with `--chown`, `USER appuser`. The live-reload bind mount (`.:/app`) works because uid 1000 is also the usual first user on a Linux host (it was checked: files written by the container into the project folder belong to the host user, and uvicorn `--reload` still restarts on edits). With a different host user id the container can still read and reload; to create files from inside it, run `docker compose exec --user "$(id -u):$(id -g)" app ...`.
- `.dockerignore`: `.env`, `.git`, caches, `.coverage` and virtualenvs.
- `docker-compose.yml`: the app has a healthcheck (`python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"`, every 10 seconds; `docker compose ps` shows `healthy`). The `db` service has **no `ports:`** entry, so Postgres is closed to the outside (use `docker compose exec db psql ...`).
- The dev compose file keeps `--reload`. To run without it: `docker compose run --rm --service-ports app uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `pytest-cov==7.1.0` was added to `requirements.txt` (the only new package).

## Future work

- **Reviews and ratings** (deferred on purpose; CLAUDE.md says not to create tables, endpoints or UI yet). A sketch of what it needs:
  - Tables: `reviews` (`id`, `product_id` FK, `user_id` FK, `rating` with `CHECK (rating BETWEEN 1 AND 5)`, `title`, `body`, `created_at`, `updated_at`, `UNIQUE (product_id, user_id)` so one review per buyer per product), indexed on `(product_id, created_at DESC)`.
  - Endpoints: `POST /products/{id}/reviews` (customer only; the service checks that the buyer **received** the product, with an `EXISTS` over their `delivered` orders and `order_items`, otherwise 403), `PUT` and `DELETE` of one's own review (404 for someone else's), `GET /products/{id}/reviews` (public, paginated), and an admin delete for moderation. Every new endpoint goes into the inventory test.
  - Average rating: keep `rating_count` and `rating_sum` on `products`, changed in the same transaction as the review (with the product row locked, like stock edits), so lists never need an aggregate query or a query per product; `average = rating_sum / rating_count` is computed in the service. A `sort=rating` option for `GET /products` would use an index on the stored average.
  - UI: stars on the product card and the product page, a review list, a review form shown only to eligible buyers, all text through `textContent` (reviews are user content, the CSP and the no-`innerHTML` rule stay), accessible star input (radio buttons with labels).
- Login rate limiting (a Postgres-based throttle or a reverse proxy), token revocation and refresh tokens
- Email notifications (order confirmation, shipment)
- Returns and partial refunds
- Per-item fulfilment (one status per order today, so a mixed order needs an admin)
- Other payment methods (asynchronous methods need the `async_payment_*` events)
- A very small order total can be rejected by Stripe (minimum charge); the order is then cancelled and the cart restored
- Deployment: HTTPS and the HSTS header, a production server setup, secrets management, backups, monitoring

## Key design decisions (M6)

- **Decisions CLAUDE.md and the milestone did not cover:**
  - `product_id` has an upper limit of 2147483647 in the body and in the paths (422 above), like the price limits in M5.
  - The `next` check also rejects control characters (see above).
  - On PATCH, if the product is inactive the "no longer available" 409 comes before the limit check. If the limit is 0 the limit message is "Out of stock".
  - The 404 for a line that is not in the cart says `"Product is not in your cart"`.
  - `quantity` in the PATCH/POST body is validated by Pydantic (422); the max in the service is the only place that knows the stock-based limit.
  - One shared `.button-secondary` style (Remove, Clear cart) and one `.quantity-select` style (product page and cart page).
  - "Subtotal (1 item)" uses the singular for one item.
- Tests: `tests/test_cart.py` has its own small fixtures (`shop`: seller, category, a logged-in customer and a `product()` maker; `change_product`; `table_snapshot`). Each test builds its own data; nothing uses the seed.
- Tested by hand in headless Chrome (driven over the DevTools protocol): logged-out product page and `/cart.html` redirect, garbage token on a public page (still loads, token removed), login with `next`, five open-redirect attempts (all go to `/`), add from the product page, the stock-1 product (dropdown offers only 1, second add shows the 409 message), badge updates, quantity change, problems ("Only 3 left" with a disabled option, "No longer available"), remove, clear, seller/admin views, stock-0 product, 360px wide (no horizontal scroll). The only console errors are the browser's own logs of expected 401/403/409 responses. The dev database was restored afterwards.

## Key design decisions (M5)

- **Decisions CLAUDE.md did not cover:**
  - `list_products` now returns `(products, total)` and `count_products` was deleted, so the WHERE conditions are built once (the milestone asked for one shared list). The seller list uses the same function.
  - The service rejects `min_price > max_price` and `sort=relevance` without `q` with 422 and a plain-text `detail`.
  - `min_price` / `max_price` have an upper limit of 2147483647 (the database integer), otherwise a huge value caused a 500.
  - A NUL character in `q` is stripped in the service (it would be a 500 otherwise).
  - `in_stock` is `bool`, default `false`; `false` means "no stock filter".
  - The extra partial index `ix_products_active_newest` was added with measured evidence (see "Search performance"). The declared condition is `is_active IS TRUE` so Postgres matches it to SQLAlchemy's SQL.
  - `deferred=True` on `search_vector`; it is only used inside WHERE and ORDER BY, never loaded or returned.
  - The tests' `create_product` fixture got an optional `description` argument.
  - `sort` in the page URL is carried into links only when the URL already had one, so default URLs stay short. The sort dropdown always sends it.
- Stage 1 (ILIKE) was built and measured first, then fully deleted. No ILIKE code remains.
- Frontend: tested by hand in headless Chrome (search, filters, sort, category with search kept, Next/Previous, empty state, price error, `<script>alert(1)</script>` in `q` shown as text, 420px wide).

## Key design decisions (M3)

- **`PATCH` body:** the optional fields use `Field(default=None)` with a non-null type, so a field that is left out is simply not used, while an explicit `null` gives 422 (only `image_url` accepts `null`). The service reads `request.model_dump(exclude_unset=True)`.
- **One product list query:** `product_repository.list_products` and `count_products` take `only_active`, `category_id` and `seller_id`, so the public list and `/seller/products` share them. The service passes `None` for the filters it does not use.
- **`/seller/products`** is declared first in `routers/products.py` (router without a prefix). It is a different path from `/products/{product_id}`, so they can never clash.
- **Role check for PATCH/DELETE** is in the service (`get_current_user`, then 403 unless seller or admin, then the 404 ownership check), as asked. POST and `/seller/products` use `require_seller`, so an admin gets 403 there.
- **Product responses after a write:** `create_product` reads the product again with `joinedload` so the category and seller are in the response; `update_product` assigns `product.category` when the category changes (the session does not expire objects on commit).
- **Categories:** create and update responses have no `product_count` (only the list does). Deleting also catches `IntegrityError` (rollback, then 409) in case a product was added at the same moment.
- **Eager loading:** `Product.category` and `Product.seller` are loaded with `joinedload` in the repository queries, so lists do not run one query per product.
- **Slug limits:** only ASCII letters and digits are kept, so a name made only of other scripts (for example Hindi) gives 422.

## Patterns and test tips (handoff notes from M2, still valid)

- **Seller endpoints must allow a seller or an admin.** `require_seller` accepts only sellers, so do NOT use it for product management. Use `get_current_user` and check `role in ("seller", "admin")` inline in the service (raise 403 otherwise).
- **Ownership:** a seller may only change their own products (`product.seller_id == current_user.id`); an admin may change any. When a seller touches someone else's product, return 404 (not 403), like addresses.
- Public catalog endpoints (list and read products, categories) need no token. Hide inactive products from the public lists.
- Paginated lists must use the format `{"items", "total", "page", "page_size"}` with `page >= 1` and `1 <= page_size <= 100` (default 20), as in `/admin/users`. See `user_service.list_users` and `user_repository.list_users` / `count_users` for the pattern.
- Same file pattern as M2: router (HTTP only) → service (transaction, rules, `HTTPException`) → repository (queries, no commit). Use `from app.repositories import xxx_repository` and call `xxx_repository.function(db, ...)`.
- Tests: use the `client`, `create_user` and `auth_headers` fixtures. Insert categories/products in each test (the test database is empty).
- After changing `requirements.txt`, rebuild with `docker compose up -d --build`. Creating files inside the container with Alembic makes them root-owned; use `docker compose exec --user "$(id -u):$(id -g)" app alembic revision ...`.
