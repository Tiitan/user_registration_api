"""Transactional database cursor context manager."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncmy
from asyncmy.cursors import DictCursor


@asynccontextmanager
async def transactional_cursor(db_pool: asyncmy.Pool) -> AsyncIterator[DictCursor]:
    """Yield a dictionary cursor wrapped in a database transaction."""
    async with db_pool.acquire() as connection:
        await connection.begin()
        try:
            async with connection.cursor(DictCursor) as cursor:
                yield cursor
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
