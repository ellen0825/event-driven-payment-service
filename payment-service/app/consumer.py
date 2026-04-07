import asyncio
import random
from datetime import datetime, timezone

import httpx
from faststream.rabbit import RabbitMessage
from sqlalchemy import update

from app.broker import broker, PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE, PAYMENTS_DLQ, DLX_EXCHANGE
from app.database import AsyncSessionLocal
from app.models import Payment, PaymentStatus

MAX_RETRIES = 3


async def _emulate_gateway() -> bool:
    """Simulate external gateway: 2-5s latency, 90% success rate."""
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return random.random() < 0.9


async def _send_webhook(url: str, payment_id: str, status: str) -> None:
    """POST webhook with up to 3 attempts and exponential backoff (1s, 2s, 4s)."""
    payload = {"payment_id": payment_id, "status": status}
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code < 500:
                    return
        except Exception:
            pass
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(2 ** attempt)


# Declare DLQ so RabbitMQ creates it on startup
@broker.subscriber(PAYMENTS_DLQ, DLX_EXCHANGE)
async def handle_dead_letter(msg: dict) -> None:
    """Receives messages that exhausted all retries. Logged for observability."""
    payment_id = msg.get("payment_id", "unknown")
    print(f"[DLQ] Payment {payment_id} permanently failed after {MAX_RETRIES} attempts")


@broker.subscriber(PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE, retry=False)
async def handle_payment(msg: dict, raw_message: RabbitMessage) -> None:
    """
    Single consumer handling the full payment lifecycle:
    - Emulates gateway processing (2-5s, 90% success)
    - Updates payment status in DB
    - Sends webhook notification with retries
    - On unrecoverable error: nack → RabbitMQ routes to DLQ
    """
    payment_id = msg["payment_id"]
    amount = msg["amount"]
    currency = msg["currency"]
    webhook_url = msg.get("webhook_url")

    for attempt in range(MAX_RETRIES):
        try:
            success = await _emulate_gateway()
            new_status = PaymentStatus.succeeded if success else PaymentStatus.failed

            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Payment)
                    .where(Payment.id == payment_id)
                    .values(status=new_status, processed_at=datetime.now(timezone.utc))
                )
                await session.commit()

            if webhook_url:
                await _send_webhook(webhook_url, payment_id, new_status.value)

            await raw_message.ack()
            return

        except Exception:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)  # 1s → 2s → 4s

    # All retries exhausted — nack without requeue, RabbitMQ sends to DLQ
    await raw_message.nack(requeue=False)
