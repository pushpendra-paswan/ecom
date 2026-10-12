# CLAUDE.md

## Project

An Amazon-style e-commerce web application, built for learning. Customers browse, search, add to cart, pay with Stripe and track orders. Sellers and admins manage products, inventory and orders. The goal is to understand the full web development flow, from the browser to the database, including transactions, authorization, payment webhooks and order lifecycles.

It is a **well-built monolith**. Payments use **Stripe in test mode only**. Shipping is mocked.

## Tech stack

- **Backend:** Python, FastAPI, Pydantic
- **ORM and migrations:** SQLAlchemy 2.x (synchronous), Alembic
- **Database:** PostgreSQL
- **Auth:** JWT access token, bcrypt for password hashing
- **Payments:** Stripe (`stripe` Python SDK), hosted Stripe Checkout page, webhooks. Test mode only.
- **Frontend:** plain HTML, CSS and JavaScript (`fetch` API)
- **Testing:** pytest and httpx, run against a real Postgres test database (not SQLite)
- **Dev environment:** Docker Compose (app and Postgres). The Stripe CLI runs on the host to forward webhooks.

## Out of scope: do NOT add these

- React, Vue, TypeScript, Tailwind, or any frontend framework or build tool
- Redis or any caching layer (the cart lives in Postgres)
- Celery, background jobs or task queues (the Stripe webhook is a normal request handler, not a background job)
- Object storage such as S3 (product images are a URL or a path under `static/images/`)
- Microservices, WebSockets, Elasticsearch
- Any ML, recommendation, semantic search or chatbot features
- **Reviews and ratings.** Deferred to a later version. Do not create tables, endpoints or UI for them yet.
- Live Stripe keys or real money. Test keys only.
- Stripe.js or card inputs on our own pages. Card details must never touch our server.
- Real shipping and real emails

If something outside this list seems necessary, ask first.

## Coding style

This is the most important section. Keep the code simple and easy to read, in a beginner-friendly, procedural style.

- Write plain, sequential code that reads top to bottom, one step after another.
- Put a short comment above each step explaining what it does.
- **No unnecessary helper functions.** Do not extract a function just to reuse two lines or to make the code look tidy.
- **No helper calling another helper.** Inside a layer, functions must not call other functions of the same layer. Each function does its whole job inline.
- The only allowed calls between functions are the straight layer calls: router → service → repository.
- **No unnecessary splitting of code across files.** Do not create a new file without a clear reason. One file per route group, one per service and one per repository is enough.
- No clever abstractions, base classes, generic utilities, decorators or metaprogramming unless the framework requires them.
- Use clear, full variable names. Avoid abbreviations.
- Prefer a little repetition over a premature abstraction.
- Beyond the layer functions, the only extra functions allowed are FastAPI dependencies such as `get_db` and `get_current_user`.

## Architecture

Three layers, each with one job:

- **Routers:** HTTP only. Parse the request, call a service, return the response.
- **Services:** business logic. A service owns the database transaction (it opens it, commits or rolls back) and decides what happens. Stripe calls live here too.
- **Repositories:** database queries only (SQLAlchemy). Take the session from the service. Contain no business rules and never commit.

Do not put business logic in routers or repositories.

## Project structure

```
ecom/                    # the project folder (called ecommerce/ in the first draft of this file)
├── app/
│   ├── main.py          # app, security headers, error handlers, /health, static and page mounts
│   ├── db.py
│   ├── seed.py          # demo data: python -m app.seed
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic request/response schemas
│   ├── routers/         # auth, users, admin, categories, products, cart, orders, seller_orders, webhooks
│   ├── services/        # business logic, transactions, Stripe calls
│   ├── repositories/    # database queries
│   └── core/            # config, dependencies (the bcrypt and JWT code is inline in auth_service.py and dependencies.py)
├── alembic/             # env.py and versions/
├── static/              # css, js, images
├── frontend/            # HTML pages (including 404.html)
├── tests/
├── alembic.ini
├── pytest.ini
├── Dockerfile
├── .dockerignore
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
├── CLAUDE.md
└── PROJECT_CONTEXT.md
```

## Configuration

All settings come from environment variables, read in one config file in `core/`:
`DATABASE_URL`, `TEST_DATABASE_URL`, `JWT_SECRET` (required, at least 32 characters), `JWT_EXPIRE_MINUTES`, `STRIPE_SECRET_KEY` (`sk_test_...`), `STRIPE_WEBHOOK_SECRET`, `STRIPE_CURRENCY`, `FRONTEND_BASE_URL`.

Never commit secrets. Keep `.env` in `.gitignore` and maintain `.env.example`.

## Database rules

- Tables: `users`, `addresses`, `categories`, `products`, `carts`, `cart_items`, `orders`, `order_items`, `payments`
- Store money as integers in the smallest currency unit (paise or cents), never floats. This matches what Stripe expects.
- `order_items` stores a **price snapshot**, so later price changes never rewrite order history.
- `payments` stores: `order_id`, `stripe_checkout_session_id` (unique), `stripe_payment_intent_id`, `stripe_refund_id`, `amount`, `currency` and `status` (`pending`, `succeeded`, `failed`, `refunded`).
- Let the database enforce correctness: foreign keys, unique constraints (one cart per user), `CHECK (stock >= 0)`.
- Every schema change goes through an Alembic migration. Never edit the schema by hand.
- Add indexes for category, price and the search column.

## Auth and roles

- Roles: `customer`, `seller`, `admin`.
- Check roles with FastAPI dependencies (`require_customer`, `require_seller`, `require_admin`).
- **Every endpoint must check ownership**, so a user can never read or change another user's cart, orders or addresses. A seller can only edit their own products. Admins can edit everything.
- Never return password hashes. Never log tokens or Stripe secrets.

## Checkout and payment rules (the core of the project)

Stripe confirms payment asynchronously, and a database transaction must never stay open during a network call to Stripe. So checkout has two stages.

**Stage 1: place the order (`POST /orders/checkout`)**

In one database transaction:

1. Lock the product rows with `SELECT ... FOR UPDATE`
2. Verify stock for every cart item
3. Create the order with status `pending_payment`, plus order items with price snapshots (the order total may not be above 99,999,999 paise, Stripe's limit: otherwise roll back and answer 409)
4. Decrement stock (this reserves it for the buyer)
5. Create a `payments` row with status `pending`
6. Clear the cart

Then, after the commit:

7. Create a Stripe Checkout Session. The line items and amounts come from the order in our database, never from the client. Set an expiry of 30 minutes (the code adds one minute, because Stripe wants at least 30 minutes) and use the order id as the idempotency key (`order-<id>`).
8. Save the session id on the `payments` row and return the Stripe session URL.

If creating the Stripe session fails, cancel the order and restore stock in one transaction.

**Stage 2: Stripe webhook (`POST /webhooks/stripe`)**

- Verify the Stripe signature with `STRIPE_WEBHOOK_SECRET`. Reject the request if it is invalid.
- `checkout.session.completed`: the order goes `pending_payment → paid` and the payment becomes `succeeded`.
- `checkout.session.expired`: the order goes to `cancelled`, stock is restored and the payment becomes `failed`. Do this in one transaction.
- Webhooks must be **idempotent**. Stripe retries events, so only act if the order is still `pending_payment`.
- Return 200 quickly.
- Only the webhook marks an order as paid. The success redirect page never does.

Two buyers must never be able to buy the last item.

## Order lifecycle

`pending_payment → paid → shipped → delivered`, plus `cancelled`. Reject invalid transitions.

- A `pending_payment` order can be cancelled, which restores stock.
- A `paid` order can be cancelled before it ships. This restores stock and creates a Stripe refund.
- All cancellations run inside a transaction.
- Sellers can move an order to shipped or delivered only when every item in it is theirs; otherwise only an admin can.

## Frontend conventions

- Plain HTML, CSS and JavaScript only. No frameworks, no bundlers, no npm.
- One shared `api.js` handles `fetch`, attaches the JWT from `localStorage` and handles 401s.
- One CSS file shared by all pages. Use plain JS functions to build product cards and lists.
- Always show loading and error states.
- Checkout: the checkout page calls `/orders/checkout` and redirects the browser to the returned Stripe URL. A success page then polls the order until the webhook marks it `paid`. A cancelled page explains the order was not paid.

## API conventions

- REST, JSON, and plural nouns for resources (`/products`, `/orders`).
- Consistent error responses with proper status codes (400, 401, 403, 404, 409).
- Paginate list endpoints with `page` and `page_size`.

## Testing

- Use pytest with httpx against a separate Postgres test database.
- Never call the real Stripe API in tests. Patch the Stripe calls, and test the webhook by sending events signed with a test secret.
- Cover auth and permissions, the cart rules, checkout and the webhook.
- Required checkout tests: two concurrent buyers for the last item (exactly one must succeed), a failed Stripe session that restores stock, an expired session that cancels the order and restores stock, and a webhook delivered twice that changes the order only once.
- Keep tests plain and readable. Do not over-test trivial code.

## Local Stripe setup

1. Use a Stripe account in test mode and put the test secret key in `.env`.
2. Run `stripe listen --forward-to localhost:8000/webhooks/stripe` on the host (the README adds `--events checkout.session.completed,checkout.session.expired`, the only two events the app handles).
3. Copy the `whsec_...` signing secret it prints into `STRIPE_WEBHOOK_SECRET`.
4. Pay with the test card `4242 4242 4242 4242`, any future expiry date and any CVC.

## Milestones

| # | Milestone |
|---|---|
| M0 | Project setup (Docker Compose, FastAPI, Alembic, pytest, static files) |
| M1 | Database schema, models and seed data |
| M2 | Authentication and roles (plus login and register pages) |
| M3 | Catalog API (categories and products) |
| M4 | Storefront frontend (home, category and product pages) |
| M5 | Search, filter, sort and pagination |
| M6 | Cart |
| M7 | Checkout and orders (stock reservation, Stripe Checkout Session, order history) |
| M8 | Stripe webhooks (payment confirmation, expiry handling, idempotency) |
| M9 | Order lifecycle and seller/admin dashboard (including refunds on cancel) |
| M10 | Hardening and finish (security pass, test gaps, indexes, README) |

## Workflow

- Work on **one milestone at a time**. Do not start the next one until asked.
- Read `CLAUDE.md` and `PROJECT_CONTEXT.md` first, then **start writing code straight away**. Do not stop to ask for approval of a plan.
- If a decision is not covered here, pick the simplest option that fits the coding style and record it in `PROJECT_CONTEXT.md`. Only stop to ask when something would break the scope list above or cannot be undone.
- Stay inside the milestone's scope. Do not add features that were not asked for.
- **After every milestone, update `PROJECT_CONTEXT.md`** with: the architecture and stack, completed and pending milestones, the database schema as it now stands, key design decisions, and anything the next milestone needs to know.
- When finished, give a short summary of what was built, how to run it and how to verify it.
