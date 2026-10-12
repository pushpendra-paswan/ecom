from fastapi import APIRouter, Depends, Header, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import webhook_service

# Public: no login. The Stripe signature is the security.
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# This is the only "async def" endpoint in the project. Reading the raw request body needs "await".
# The signature is checked against those exact bytes, so there is no Pydantic body model.
@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()

    # The service uses the database and Stripe (blocking calls), so it runs in a worker thread
    # and does not block the event loop
    return await run_in_threadpool(webhook_service.handle_stripe_event, db, payload, stripe_signature)
