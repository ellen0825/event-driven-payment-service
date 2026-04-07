"""Emulated external payment gateway."""
import random
import asyncio


async def process_payment(payment_id: str, amount: float, currency: str) -> dict:
    """Simulate gateway latency and random success/failure."""
    await asyncio.sleep(random.uniform(0.5, 2.0))
    success = random.random() > 0.2  # 80% success rate
    return {
        "success": success,
        "gateway_ref": f"GW-{payment_id[:8].upper()}" if success else None,
        "error": None if success else "Gateway declined the transaction",
    }
