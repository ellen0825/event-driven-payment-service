import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.broker import broker
from app.outbox import run_outbox_relay
from app.routers.payments import router as payments_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.start()
    outbox_task = asyncio.create_task(run_outbox_relay())

    yield

    outbox_task.cancel()
    await broker.close()


app = FastAPI(title="Payment Processing Service", lifespan=lifespan)
app.include_router(payments_router)
