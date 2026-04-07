import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import engine, Base
from app.routers.payments import router as payments_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(10):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except Exception:
            if attempt == 9:
                raise
            await asyncio.sleep(2)
    yield


app = FastAPI(title="Payment Processing Service", lifespan=lifespan)
app.include_router(payments_router)
