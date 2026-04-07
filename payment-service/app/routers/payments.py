from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import verify_api_key
from app.database import get_db
from app.models import Payment, OutboxEvent
from app.schemas import PaymentCreate, PaymentResponse, PaymentDetail

router = APIRouter(prefix="/api/v1/payments", tags=["payments"], dependencies=[Depends(verify_api_key)])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentResponse)
async def create_payment(
    body: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
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

    # Write outbox event atomically with payment
    outbox = OutboxEvent(
        payment_id=payment.id,
        event_type="payment.created",
        payload={
            "payment_id": payment.id,
            "amount": float(body.amount),
            "currency": body.currency.value,
            "webhook_url": body.webhook_url,
        },
    )
    db.add(outbox)

    try:
        await db.commit()
        await db.refresh(payment)
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        existing = result.scalar_one()
        return PaymentResponse(payment_id=existing.id, status=existing.status, created_at=existing.created_at)

    return PaymentResponse(payment_id=payment.id, status=payment.status, created_at=payment.created_at)


@router.get("/{payment_id}", response_model=PaymentDetail)
async def get_payment(payment_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    return PaymentDetail(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.metadata_,
        status=payment.status,
        idempotency_key=payment.idempotency_key,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )
