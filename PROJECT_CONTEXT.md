# PROJECT_CONTEXT.md

## Project summary

An Amazon-style e-commerce web app, built for learning the full web flow from browser to database. Customers browse, search, add to cart, pay with Stripe (test mode only) and track orders. Sellers and admins manage products, inventory and orders. It is a well-built monolith; shipping is mocked. See `CLAUDE.md` for all rules (coding style, architecture, checkout and webhook rules, scope list).

## Tech stack

- Backend: Python 3.12, FastAPI, Pydantic, pydantic-settings
- ORM and migrations: SQLAlchemy 2.1 (synchronous), Alembic
- Database: PostgreSQL 16 (driver: psycopg 3)
- Frontend: plain HTML, CSS, JavaScript (served by FastAPI)
- Testing: pytest and httpx (via FastAPI `TestClient`) against a real Postgres test database
- Dev environment: Docker Compose (`app` and `db`)
- Password hashing: `bcrypt` (used directly; installed in M1 for the seed script)
- Not installed yet (later milestones): JWT library, `stripe`

Pinned versions are in `requirements.txt`.

## Folder structure

```
ecom/                      # project root (CLAUDE.md calls it ecommerce/)
├── app/
│   ├── main.py            # FastAPI app, /health, static and frontend mounts
│   ├── db.py              # engine, SessionLocal, Base, get_db
│   ├── seed.py            # demo data: python -m app.seed
│   ├── models/            # user.py, catalog.py, cart.py, order.py (__init__ imports all)
│   ├── schemas/           # (only __init__.py for now)
│   ├── routers/           # (only __init__.py for now)
│   ├── services/          # (only __init__.py for now)
│   ├── repositories/      # (only __init__.py for now)
│   └── core/
│       └── config.py      # Settings class (reads env variables)
├── alembic/               # env.py, script.py.mako, versions/ (one migration: initial schema)
├── alembic.ini
├── static/                # css/style.css, js/, images/
├── frontend/              # index.html (placeholder)
├── tests/                 # conftest.py, test_health.py, test_schema.py
├── docker-compose.yml
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── .env.example / .env    # .env is git-ignored
├── CLAUDE.md
└── PROJECT_CONTEXT.md
```

## How to run

```bash
docker compose up --build
```

- App: http://localhost:8000/ (placeholder page)
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- CSS: http://localhost:8000/static/css/style.css
- Alembic: `docker compose exec app alembic current`

`.env` is a copy of `.env.example`. Postgres is not published on the host; use `docker compose exec db psql -U postgres ecommerce`.

## How to test

```bash
docker compose exec app pytest
```

Tests use `TEST_DATABASE_URL` (database `ecommerce_test`). `tests/conftest.py` creates that database if missing, then runs `alembic downgrade base` and `alembic upgrade head` on it once per test session (so the migration itself is tested). It refuses to run if the test and dev database names are the same.

Two fixtures:
- `db_session`: a session inside an outer transaction that is rolled back after every test (savepoint mode, so a failed statement inside `pytest.raises(IntegrityError)` does not break the test). Use this for model and repository/service tests.
- `client`: a `TestClient` whose `get_db` is overridden to use the test database. It commits for real, so data written through the client is NOT rolled back (M2 must clean up, e.g. truncate tables after each test).

## Completed milestones

- **M0: Project setup.** Docker Compose (app + Postgres 16 with healthcheck and named volume), FastAPI skeleton with `/health`, static and frontend mounts, Alembic configured (no migrations), pytest against a separate test database.
- **M1: Database schema, models and seed data.** All 9 tables as SQLAlchemy 2.x models, one Alembic migration (`6fc51572ed70`), seed script, schema tests. No endpoints.

## Pending milestones

M2 Authentication and roles · M3 Catalog API · M4 Storefront frontend · M5 Search, filter, sort, pagination · M6 Cart · M7 Checkout and orders · M8 Stripe webhooks · M9 Order lifecycle and seller/admin dashboard · M10 Hardening and finish

## Database schema

Created by the single migration `alembic/versions/6fc51572ed70_create_initial_schema.py`. All tables have `id integer` primary key (auto-increment). Money columns are integers in paise. `timestamptz` columns default to `now()` on the server. `updated_at` is also refreshed by SQLAlchemy on ORM updates (`onupdate=func.now()`).

**users**: `email` varchar(255) unique not null; `password_hash` not null; `full_name` not null; `role` varchar(20) default `customer`, CHECK in (`customer`, `seller`, `admin`); `is_active` bool default true; `created_at`.

**addresses**: `user_id` FK users **ON DELETE CASCADE**; `full_name`, `phone`, `line1`, `line2` (nullable), `city`, `state`, `postal_code`, `country` (default `India`); `is_default` bool default false; `created_at`.

**categories**: `name` unique; `slug` unique; `description` (nullable); `created_at`. Flat list, no parent.

**products**: `seller_id` FK users (no action); `category_id` FK categories (no action); `name`; `description`; `price` CHECK `> 0`; `stock` CHECK `>= 0`; `image_url` (nullable); `is_active` default true; `created_at`; `updated_at`. Indexes: `ix_products_category_id`, `ix_products_price`, `ix_products_seller_id`. (No search index yet, that is M5.)

**carts**: `user_id` FK users **ON DELETE CASCADE**, UNIQUE (one cart per user); `created_at`.

**cart_items**: `cart_id` FK carts **ON DELETE CASCADE**; `product_id` FK products (no action); `quantity` CHECK `> 0`; UNIQUE (`cart_id`, `product_id`).

**orders**: `user_id` FK users **ON DELETE RESTRICT**; `status` varchar(20) default `pending_payment`, CHECK in (`pending_payment`, `paid`, `shipped`, `delivered`, `cancelled`); `total_amount` CHECK `>= 0`; shipping address copy: `shipping_full_name`, `shipping_phone`, `shipping_line1`, `shipping_line2` (nullable), `shipping_city`, `shipping_state`, `shipping_postal_code`, `shipping_country` (no FK to addresses); `created_at`; `updated_at`. Indexes: `ix_orders_user_id`, `ix_orders_status`.

**order_items**: `order_id` FK orders **ON DELETE CASCADE**; `product_id` FK products **ON DELETE RESTRICT**; `product_name` (snapshot); `unit_price` (snapshot) CHECK `> 0`; `quantity` CHECK `> 0`.

**payments**: `order_id` FK orders (no action), UNIQUE (one payment per order); `stripe_checkout_session_id` varchar(255) nullable, UNIQUE; `stripe_payment_intent_id` nullable; `amount` CHECK `>= 0`; `currency` default `inr`; `status` default `pending`, CHECK in (`pending`, `succeeded`, `failed`); `created_at`; `updated_at`.

Constraints are named explicitly (`ck_<table>_<rule>`, `uq_cart_items_cart_id_product_id`); unique and FK constraints use Postgres default names.

ORM relationships (only these four): `Product.category`, `Cart.items`, `Order.items`, `Order.payment`. Everything else is queried by id in repositories.

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

## Notes for the next milestone (M2)

- Add the JWT library (e.g. PyJWT) to `requirements.txt`; `bcrypt` is already installed. Set `JWT_SECRET` in `.env` (it defaults to empty).
- Seed users already have bcrypt hashes made with `bcrypt.hashpw(password.encode(), bcrypt.gensalt())` (decoded to str), so login should check with `bcrypt.checkpw(password.encode(), password_hash.encode())`.
- `User.is_active` exists: login should reject inactive users.
- Registration should only create `customer` users; sellers and admins come from the seed (or an admin later). The DB already rejects duplicate emails (`IntegrityError`; turn it into a 409).
- Models have no `back_populates` and no relationship to `User`; query by `user_id` in repositories.
- API tests that go through the `client` fixture commit for real into `ecommerce_test` and the schema is only rebuilt at the start of the next test session. Clean up between tests (for example truncate the tables in a fixture) or make `client` use a rolled back `db_session`.
- Creating files inside the container with Alembic makes them root-owned; use `docker compose exec --user "$(id -u):$(id -g)" app alembic revision ...`.
- After changing `requirements.txt`, rebuild with `docker compose up -d --build` (the project folder is mounted, but installed packages live in the image).
