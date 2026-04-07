import asyncio
from datetime import datetime, timezone

import httpx
from celery import Celery
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Payment, PaymentStatus
from app.services.gateway import process_payment

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)

# Sync engine for Celery tasks
sync_engine = create_engine(settings.sync_database_url)
SyncSession = sessionmaker(bind=sync_engine)


@celery_app.task(bind=True, max_retries=3)
def process_payment_task(self, payment_id: str, amount: float, currency: str, webhook_url: str | None):
    try:
        result = asyncio.run(process_payment(payment_id, amount, currency))
        new_status = PaymentStatus.succeeded if result["success"] else PaymentStatus.failed

        with SyncSession() as session:
            session.execute(
                update(Payment)
                .where(Payment.id == payment_id)
                .values(status=new_status, processed_at=datetime.now(timezone.utc))
            )
            session.commit()

        if webhook_url:
            _send_webhook(webhook_url, payment_id, new_status)

    except Exception as exc:
        raise self.retry(exc=exc, countdown=2**self.request.retries)


def _send_webhook(url: str, payment_id: str, status: PaymentStatus):
    payload = {"payment_id": payment_id, "status": status.value}
    try:
        with httpx.Client(timeout=10) as client:
            client.post(url, json=payload)
    except Exception:
        pass  # webhook delivery is best-effort
