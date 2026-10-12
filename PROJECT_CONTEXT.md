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
- Password hashing: `bcrypt` (used directly, no wrapper)
- Tokens: `PyJWT` (HS256). Email validation: `email-validator` (used by Pydantic `EmailStr`)
- Not installed yet (later milestones): `stripe`

Pinned versions are in `requirements.txt`.

## Folder structure

```
ecom/                      # project root (CLAUDE.md calls it ecommerce/)
├── app/
│   ├── main.py            # FastAPI app, /health, static and frontend mounts
│   ├── db.py              # engine, SessionLocal, Base, get_db
│   ├── seed.py            # demo data: python -m app.seed
│   ├── models/            # user.py, catalog.py, cart.py, order.py (__init__ imports all)
│   ├── schemas/           # user.py, address.py, category.py, product.py
│   ├── routers/           # auth.py, users.py, admin.py, categories.py, products.py
│   ├── services/          # auth_service.py, user_service.py, address_service.py, category_service.py, product_service.py
│   ├── repositories/      # user_repository.py, address_repository.py, category_repository.py, product_repository.py
│   └── core/
│       ├── config.py      # Settings class (reads env variables)
│       └── dependencies.py  # get_current_user, require_customer, require_seller, require_admin
├── alembic/               # env.py, script.py.mako, versions/ (one migration: initial schema)
├── alembic.ini
├── static/                # css/style.css, js/ (see the frontend map), images/ (placeholder.svg)
├── frontend/              # index.html, products.html, product.html, login.html, register.html
├── tests/                 # conftest.py, test_health.py, test_schema.py, test_auth.py, test_users.py, test_roles.py, test_categories.py, test_products_public.py, test_products_write.py, test_frontend_files.py
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

- App: http://localhost:8000/ (storefront home page)
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
- `client`: a `TestClient` whose `get_db` is overridden to use the test database. It commits for real, so after every test it runs `TRUNCATE users, categories RESTART IDENTITY CASCADE` (this empties every table). The test database is never seeded.

Helper fixtures in `conftest.py` (M2, M3):
- `create_user(email, role="customer", is_active=True, password="Password@123")`: inserts a user directly into the test database (fast bcrypt rounds) and returns the user id.
- `auth_headers(email, password="Password@123")`: logs in through `/auth/login` and returns `{"Authorization": "Bearer ..."}`.
- `create_category(name, slug=None)` (M3): inserts a category directly and returns its id. The slug defaults to the lowercased name with spaces turned into hyphens.
- `create_product(seller_id, category_id, name=..., price=10000, stock=10, is_active=True, created_at=None)` (M3): inserts a product directly and returns its id. Pass `created_at` to control the order in tests.

## Completed milestones

- **M0: Project setup.** Docker Compose (app + Postgres 16 with healthcheck and named volume), FastAPI skeleton with `/health`, static and frontend mounts, Alembic configured (no migrations), pytest against a separate test database.
- **M1: Database schema, models and seed data.** All 9 tables as SQLAlchemy 2.x models, one Alembic migration (`6fc51572ed70`), seed script, schema tests. No endpoints.
- **M2: Authentication, roles and user accounts.** Register, login (JWT), profile, addresses, admin user list, role dependencies, login/register pages, shared `api.js`, 32 tests passing. No schema change (no new migration).
- **M3: Catalog API.** Public category and product reads, admin category management, seller/admin product management with soft delete, `/seller/products`. No schema change (no new migration). 56 tests passing.
- **M4: Storefront frontend.** Shared navbar and footer (`layout.js`), home page, product listing page, product detail page, one product card function, one stylesheet, placeholder image. Read-only: no search, no cart. No backend or schema change. 57 tests passing (one new test that checks the frontend files are served).

## Pending milestones

M5 Search, filter, sort, pagination · M6 Cart · M7 Checkout and orders · M8 Stripe webhooks · M9 Order lifecycle and seller/admin dashboard · M10 Hardening and finish

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

ORM relationships (only these five): `Product.category`, `Product.seller` (added in M3, no schema change), `Cart.items`, `Order.items`, `Order.payment`. Everything else is queried by id in repositories.

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

## API endpoints (as of M3)

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
| GET `/products` | public | Paginated, active products only, newest first. Query: `page`, `page_size`, `category` (slug) |
| GET `/products/{product_id}` | public | Missing or inactive: 404 |
| POST `/products` | seller only | Returns 201. Admin and customer get 403. Unknown `category_id`: 400 |
| PATCH `/products/{product_id}` | seller (own products) or admin (any) | Partial update. Customer: 403. Other seller's product or missing: 404 |
| DELETE `/products/{product_id}` | seller (own products) or admin (any) | Soft delete, returns 204 (also when already inactive). Same rules as PATCH |
| GET `/seller/products` | seller only | Paginated, the caller's own products, active or not, newest first |

The pages `/`, `/products.html`, `/product.html`, `/login.html` and `/register.html` and everything under `/static` are public files.

## Auth flow (M2)

- **Register** creates a `customer` or `seller` (never `admin`; the seed creates admins). Email is trimmed and lowercased, password is 8 to 72 characters (also max 72 bytes), stored only as a bcrypt hash. Duplicate email: 409.
- **Login** looks up the lowercased email, checks the bcrypt password first, then `is_active`. Unknown email and wrong password give the same 401 `"Incorrect email or password"` (an unknown email still runs one bcrypt hash so timing is similar). A correct password on a disabled account gives 403 `"Account is disabled"`.
- **Token:** PyJWT, HS256, signed with `JWT_SECRET`. Payload is only `sub` (user id as a string) and `exp` (`JWT_EXPIRE_MINUTES`, default 60). The role is NOT in the token.
- **Browser storage:** the token is in `localStorage` under the key `access_token`. `static/js/api.js` (`apiRequest(path, method, body)`) adds `Authorization: Bearer <token>`. On a 401 from any path except `/auth/login` it removes the token and throws; it goes to `/login.html` only when the page's `<body>` has `data-requires-login="true"` (changed in M4).
- **Every request** to a protected endpoint goes through `get_current_user` (in `app/core/dependencies.py`): it reads the Bearer header (`HTTPBearer(auto_error=False)`), decodes the token, loads the user from the database and returns the user. The role and `is_active` always come from the database.
- **401** (`"Not authenticated"`, with `WWW-Authenticate: Bearer`): missing header, bad signature, expired token, no `sub`/`exp`, user not found, or user disabled.
- **403:** logged in, but the role is wrong. `require_customer`, `require_seller` and `require_admin` check that the role is exactly that role (an admin does NOT pass `require_customer` or `require_seller`).
- **404:** a resource that exists but belongs to someone else (for example another user's address) looks the same as one that does not exist.
- **409:** duplicate email.

## Pagination format (M2)

List endpoints take `page` (default 1, minimum 1) and `page_size` (default 20, between 1 and 100); values outside the range give 422. The response is:

```json
{"items": [...], "total": 42, "page": 1, "page_size": 20}
```

## Settings (M2)

| Variable | Default | Meaning |
|---|---|---|
| `JWT_SECRET` | none, **required** | Signing key. Generate with `openssl rand -hex 32`. The app refuses to start if it is empty |
| `JWT_EXPIRE_MINUTES` | 60 | Token lifetime |

The algorithm (HS256) is written inline where the token is created and decoded. The local `.env` has a generated dev secret; `.env.example` has it empty with a note.

## Key design decisions (M2)

- **Services raise `HTTPException` directly** (404, 409, 401, 403, 422). CLAUDE.md did not say how services report errors; this is the simplest option and avoids a separate exception layer.
- **No `core/security.py`:** bcrypt hashing/checking and JWT encode/decode are written inline in `auth_service.py` and `dependencies.py`.
- **`get_current_user` calls `user_repository.get_user_by_id`** directly (a dependency may use the repository). It shares the request's session with the service, so services can modify `current_user` and commit it.
- **Pydantic strips spaces** (`str_strip_whitespace`) on register, profile and address bodies; the service lowercases the email. Login takes `email` as a plain string, so a badly formatted email gives 401, not 422.
- **Passwords:** the 72-byte limit is checked in bytes in the service (a 72-character password with multi-byte characters is rejected with 422 on register, and with 401 on login), because bcrypt 5 raises an error above 72 bytes.
- **Addresses:** one shared `AddressRequest` for POST and PUT (PUT replaces all fields). A user may end up with no default address (deleting the default, or a PUT with `is_default: false` on it); the app never promotes another one. Nothing in the database enforces "one default per user"; the service does it.
- **Unknown JSON fields are ignored** (for example `role` in a PATCH body), so PATCH `/users/me` can only change `full_name`.
- **An empty `JWT_SECRET` stops the app at startup** (a check at the bottom of `config.py`), because an empty key would allow forged tokens.
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
- `image_url` must start with `http://`, `https://` or `/static/images/` (checked by a `Field(pattern=...)`) and is at most 500 characters. `null` is allowed and PATCH with `image_url: null` removes the image.

## Frontend (M4)

### Frontend map

| URL | Query parameters | Files |
|---|---|---|
| `/` | none | `frontend/index.html`, `home.js` |
| `/products.html` | `category` (a category slug), `page` (default 1; anything below 1 or not a number becomes 1) | `frontend/products.html`, `products.js` |
| `/product.html` | `id` (positive whole number; anything else shows "Product not found" without calling the API) | `frontend/product.html`, `product.js` |
| `/login.html` | none | `frontend/login.html`, `login.js` |
| `/register.html` | none | `frontend/register.html`, `register.js` |

| Script (`static/js/`) | What it does |
|---|---|
| `api.js` | `apiRequest(path, method, body)`: fetch + JSON + token header. On a 401 it removes the token and throws; redirects to `/login.html` only if `<body data-requires-login="true">`. Errors carry the HTTP status in `error.status` |
| `layout.js` | Defines `SITE_NAME` (once, `"ShopEasy"`). Fills `#site-header` (navbar) and `#site-footer`. Calls `GET /users/me` only when a token exists; any failure silently shows Login and Register. Logout removes the token and reloads |
| `product-card.js` | `buildProductCard(product)`: returns the `<a>` card used by the home and listing pages (image with one-time placeholder fallback, name, price, "Out of stock" label) |
| `home.js` | Category cards (`GET /categories`) and the 8 newest products (`GET /products?page=1&page_size=8`) |
| `products.js` | Category link row, heading, total count, product grid (20 per page) and Previous/Next links |
| `product.js` | Product detail (image, name, category link, seller, price, stock status, description) |
| `login.js`, `register.js` | The two forms (from M2) |

`static/css/style.css` is the one stylesheet (variables, base, layout, navbar and footer, buttons, forms, cards and grid, category links and pagination, product detail, states, responsive). `static/images/placeholder.svg` is the fallback image.

### How to add a new page

1. Create `frontend/<name>.html` with `<!DOCTYPE html>`, `lang="en"`, charset and viewport meta tags, a meaningful `<title>` and the stylesheet link.
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

## Notes for M5 (search, filter, sort)

- **Frontend:** `products.html` and `products.js` are where search, filters and sorting go (read the new query parameters next to `category` and `page`, and keep them in the Previous/Next links). The navbar search box is added in `layout.js`. The category links row already exists in `products.js`.
- `GET /products` already has: `page`, `page_size`, `category` (slug). Sorting is fixed to newest first (`created_at DESC, id DESC`).
- Still missing: text search (and the search index), `min_price` / `max_price`, and sort options. Add them to the same endpoint, `product_service.list_public_products`, and the matching `product_repository.list_products` / `count_products` (both take the same filters, so keep them in step).
- `/seller/products` uses the same repository functions (with `only_active=False` and `seller_id`), so new filters added there are optional for it.

## Notes for M6 (cart)

- **Frontend:** the cart link and the cart count badge go in `layout.js` (inside the navbar). The Add to Cart control goes in `product.html` and `product.js` (hide or disable it when `stock` is 0). The cart pages (and checkout and orders later) must set `data-requires-login="true"` on `<body>`.
- A cart can contain products that are deactivated later (soft delete keeps the row). The cart must handle inactive products: show them as unavailable and refuse them at checkout. `product_repository.get_product_by_id` returns inactive products too; check `is_active` yourself. Adding a product to the cart should reject missing and inactive products.

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
