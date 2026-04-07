import asyncio
import random
from datetime import datetime, timezone

import httpx
from faststream.rabbit import RabbitMessage
from sqlalchemy import update, select

from app.broker import broker, PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE
from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Payment, PaymentStatus


async def _emulate_gateway(payment_id: str, amount: float, currency: str) -> bool:
    """Emulate external gateway: 2-5s delay, 90% success."""
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return random.random() < 0.9


async def _send_webhook(url: str, payment_id: str, status: str, retries: int = 3):
    payload = {"payment_id": payment_id, "status": status}
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code < 500:
                    return
        except Exception:
            pass
        await asyncio.sleep(2 ** attempt)


@broker.subscriber(PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE, retry=2)
async def handle_payment(msg: dict, raw_message: RabbitMessage):
    payment_id = msg["payment_id"]
    amount = msg["amount"]
    currency = msg["currency"]
    webhook_url = msg.get("webhook_url")

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
