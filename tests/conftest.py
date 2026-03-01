"""
Pytest configuration and fixtures

WHY NO SQLITE:
  ORM models use PostgreSQL-specific constructs:
    - postgresql_using="brin" indexes
    - PostgreSQL-dialect CheckConstraints
  These cause Base.metadata.create_all() to fail on SQLite.

For unit tests: use AsyncMock (no DB required).
For integration tests: use a real PostgreSQL instance.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db():
    """
    Mock AsyncSession for unit tests.

    Uses AsyncMock — avoids any DB dependency in unit tests.
    For integration tests that need real data, use a PostgreSQL test database
    (e.g. via docker-compose -f docker-compose.test.yml).
    """
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.refresh = AsyncMock()
    yield session


@pytest.fixture
async def client():
    """HTTP client for API testing"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
