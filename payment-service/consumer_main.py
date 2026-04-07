"""Entrypoint for the standalone consumer service."""
import asyncio
from app.broker import broker
import app.consumer  # register subscriber


async def main():
    async with broker:
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
