from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Payment
from app.schemas import PaymentCreate, PaymentResponse
from app.worker import process_payment_task

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentResponse)
async def create_payment(
    body: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    # Return existing payment if idempotency key already used
    result = await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
    existing = result.scalar_one_or_none()
    if existing:
        return PaymentResponse(payment_id=existing.id, status=existing.status, created_at=existing.created_at)

    payment = Payment(
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        metadata_=body.metadata or {},
        idempotency_key=idempotency_key,
        webhook_url=body.webhook_url,
    )

    db.add(payment)
    try:
        await db.commit()
        await db.refresh(payment)
    except IntegrityError:
        await db.rollback()
        # Race condition: another request with same key committed first
        result = await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        existing = result.scalar_one()
        return PaymentResponse(payment_id=existing.id, status=existing.status, created_at=existing.created_at)

    # Enqueue async processing
    process_payment_task.delay(
        payment.id,
        float(payment.amount),
        payment.currency.value,
        payment.webhook_url,
    )

    return PaymentResponse(payment_id=payment.id, status=payment.status, created_at=payment.created_at)
