"""One-shot script to backfill all historical data from install date to today.

Usage:
    docker compose exec api python scripts/backfill.py

The implementation lives in helio.ingestion.backfill so the API can run the same
code as a background task; `python -m helio.ingestion.backfill` is equivalent.
"""

import asyncio

from helio.ingestion.backfill import backfill

if __name__ == "__main__":
    asyncio.run(backfill())
