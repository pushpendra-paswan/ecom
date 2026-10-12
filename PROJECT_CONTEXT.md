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
- Not installed yet (later milestones): bcrypt, JWT library, `stripe`

Pinned versions are in `requirements.txt`.

## Folder structure

```
ecom/                      # project root (CLAUDE.md calls it ecommerce/)
├── app/
│   ├── main.py            # FastAPI app, /health, static and frontend mounts
│   ├── db.py              # engine, SessionLocal, Base, get_db
│   ├── models/            # (only __init__.py for now)
│   ├── schemas/           # (only __init__.py for now)
│   ├── routers/           # (only __init__.py for now)
│   ├── services/          # (only __init__.py for now)
│   ├── repositories/      # (only __init__.py for now)
│   └── core/
│       └── config.py      # Settings class (reads env variables)
├── alembic/               # env.py, script.py.mako, versions/ (no migrations yet)
├── alembic.ini
├── static/                # css/style.css, js/, images/
├── frontend/              # index.html (placeholder)
├── tests/                 # conftest.py, test_health.py
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

Tests use `TEST_DATABASE_URL` (database `ecommerce_test`). `tests/conftest.py` creates that database if missing and overrides `get_db` so the app talks to it. It refuses to run if the test and dev database names are the same.

## Completed milestones

- **M0: Project setup.** Docker Compose (app + Postgres 16 with healthcheck and named volume), FastAPI skeleton with `/health`, static and frontend mounts, Alembic configured (no migrations), pytest against a separate test database.

## Pending milestones

M1 Database schema, models and seed data · M2 Authentication and roles · M3 Catalog API · M4 Storefront frontend · M5 Search, filter, sort, pagination · M6 Cart · M7 Checkout and orders · M8 Stripe webhooks · M9 Order lifecycle and seller/admin dashboard · M10 Hardening and finish

## Database schema

None yet. The schema starts in M1 (`users`, `addresses`, `categories`, `products`, `carts`, `cart_items`, `orders`, `order_items`, `payments`, as listed in CLAUDE.md).

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

## Notes for the next milestone (M1)

- Add models under `app/models/` and import every model module in `alembic/env.py` (where marked) so `Base.metadata` sees the tables. Then run `docker compose exec app alembic revision --autogenerate -m "..."` and `alembic upgrade head`.
- Files created inside the container by `alembic revision` will be owned by root. Run it with `docker compose exec --user "$(id -u):$(id -g)" app ...` or fix ownership afterwards.
- `tests/conftest.py` only creates the empty test database. Once models exist, the `test_engine` fixture must create the tables (for example run `alembic upgrade head` against the test database, or `Base.metadata.create_all`) and keep tests isolated (clean tables between tests).
- Seed data needs a script or command; there is no seed mechanism yet.
- Add `bcrypt` (M2), the JWT library (M2) and `stripe` (M7) to `requirements.txt` in their own milestones.
