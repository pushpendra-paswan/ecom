import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import admin, auth, cart, categories, orders, products, seller_orders, users, webhooks

# One log format and level for the whole app. Show INFO lines (the webhook logs one line per event)
# next to the uvicorn logs. Nothing in the code base logs passwords, tokens, keys or request bodies.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# A request body bigger than this is refused (Stripe webhook payloads are far smaller)
MAX_BODY_BYTES = 1_000_000

# Sent with every response. There is no Strict-Transport-Security (HSTS) header on purpose:
# it belongs behind HTTPS at deploy time.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

# Sent with every response except the API docs. Product images may come from any https URL,
# which is why img-src allows https:
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: data:; "
    "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
)

# There is no CORS middleware on purpose: the frontend is served by this same app (same origin),
# so no other website can call the API from a browser.
app = FastAPI(title="Ecommerce")


# FastAPI needs a function here. It is plain sequential code, one step after another.
@app.middleware("http")
async def protect_every_request(request: Request, call_next):
    # Refuse a body that announces itself as too big, without reading it.
    # (A chunked upload without a Content-Length header is not covered by this check.)
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        response = JSONResponse(status_code=413, content={"detail": "Request body too large"})
    else:
        # Let the app handle the request
        response = await call_next(request)

    # Add the security headers to every response
    for header_name, header_value in SECURITY_HEADERS.items():
        response.headers[header_name] = header_value

    # Add the Content-Security-Policy to every response except the docs
    # (Swagger UI loads its scripts from a CDN, so the policy would break it)
    is_docs_path = (
        request.url.path.startswith("/docs")
        or request.url.path.startswith("/redoc")
        or request.url.path == "/openapi.json"
    )
    if not is_docs_path:
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY

    return response


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception):
    # The details (with the traceback) go to the log only, never to the client
    logger.exception("Unexpected error on %s %s", request.method, request.url.path)

    # This response is built outside the middleware above, so it gets the headers here
    headers = dict(SECURITY_HEADERS)
    headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return JSONResponse(status_code=500, content={"detail": "Internal server error"}, headers=headers)


@app.exception_handler(DataError)
async def handle_database_data_error(request: Request, error: DataError):
    # The database refused a value that came from the user (a number out of range, a NUL character).
    # That is bad input, not a server bug. Only the error class is logged, never the values.
    logger.warning("Invalid input on %s %s (%s)", request.method, request.url.path, type(error.orig).__name__)
    return JSONResponse(status_code=422, content={"detail": "Invalid input"})


# Register the API routers (before the static mounts below)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(seller_orders.router)
app.include_router(webhooks.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    # Run a simple query to check that the database is reachable
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database is unreachable")

    # Everything works
    return {"status": "ok"}


# Serve css, js and images at /static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the HTML pages at / (this mount must stay last so API routes win)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
