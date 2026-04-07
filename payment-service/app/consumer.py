import asyncio
import random
from datetime import datetime, timezone

import httpx
from faststream.rabbit import RabbitMessage
from sqlalchemy import update

from app.broker import broker, PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE
from app.database import AsyncSessionLocal
from app.models import Payment, PaymentStatus

MAX_RETRIES = 3


async def _emulate_gateway(payment_id: str, amount: float, currency: str) -> bool:
    """2-5s delay, 90% success rate."""
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return random.random() < 0.9


async def _send_webhook(url: str, payment_id: str, status: str):
    """POST webhook with 3 attempts and exponential backoff."""
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
            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s


@broker.subscriber(PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE, retry=False)
async def handle_payment(msg: dict, raw_message: RabbitMessage):
    """
    Single consumer. Retries up to MAX_RETRIES times with exponential backoff.
    On final failure, nacks without requeue — RabbitMQ routes to DLQ via x-dead-letter-exchange.
    """
    payment_id = msg["payment_id"]
    amount = msg["amount"]
    currency = msg["currency"]
    webhook_url = msg.get("webhook_url")

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            success = await _emulate_gateway(payment_id, amount, currency)
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

        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s

    # All retries exhausted — send to DLQ
    await raw_message.nack(requeue=False)
