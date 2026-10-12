from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import admin, auth, cart, categories, orders, products, users

app = FastAPI(title="Ecommerce")

# Register the API routers (before the static mounts below)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)


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
