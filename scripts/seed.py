import asyncio

from dotenv import load_dotenv

from app.utilities.database import (
    get_answer_index,
    get_document_index,
    get_tracking_index,
)

load_dotenv()


async def seed():
    """Async seed function using the index from db.py."""
    async with get_document_index() as index:
        # Currently a no-op other than creating the index
        await index.create(overwrite=True, drop=False)

    async with get_answer_index() as index:
        # Currently a no-op other than creating the index
        await index.create(overwrite=True, drop=False)

    async with get_tracking_index() as index:
        # Currently a no-op other than creating the index
        await index.create(overwrite=True, drop=False)


if __name__ == "__main__":
    asyncio.run(seed())
