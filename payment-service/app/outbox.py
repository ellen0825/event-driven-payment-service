"""Outbox relay: polls unpublished events and publishes them to RabbitMQ."""
import asyncio
from sqlalchemy import select, update

from app.broker import broker, PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE
from app.database import AsyncSessionLocal
from app.models import OutboxEvent


async def run_outbox_relay():
    while True:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.published == False)
                    .limit(50)
                    .with_for_update(skip_locked=True)
                )
                events = result.scalars().all()

                for event in events:
                    await broker.publish(
                        event.payload,
                        queue=PAYMENTS_NEW_QUEUE,
                        exchange=PAYMENTS_EXCHANGE,
                    )
                    await session.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id == event.id)
                        .values(published=True)
                    )

                await session.commit()
        except Exception:
            pass

        await asyncio.sleep(1)
