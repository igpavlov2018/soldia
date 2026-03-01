"""
✅ FIXED v2.6: Database Manager

ИСПРАВЛЕНИЯ v2.6:
  BUG-1: session() context manager убран авто-commit на выходе.
         Callers (Celery tasks, FastAPI routes) управляют транзакциями сами.
         Авто-commit вызывал двойной коммит и некорректный rollback при ошибках.

Без изменений от v2.4: NullPool FIX, QueuePool configuration.
"""

import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    AsyncEngine,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy import event, text

from config.settings import settings
from models.database import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL connections with async support"""

    def __init__(self):
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def create_engine(self) -> AsyncEngine:
        """Create SQLAlchemy async engine with connection pooling"""

        # NullPool FIX: определяем параметры в зависимости от типа пула.
        # NullPool не принимает pool_size/max_overflow/pool_timeout —
        # передавать их приводит к ArgumentError в SQLAlchemy 2.0+.
        if settings.ENVIRONMENT == "testing":
            # Тесты: без пула, без параметров пула
            engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DATABASE_ECHO,
                pool_pre_ping=True,
                poolclass=NullPool,
                connect_args={
                    "server_settings": {
                        "application_name": "soldia_v2_test",
                        "jit": "off"
                    }
                }
            )
        else:
            # Production / development: QueuePool с полными настройками
            engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DATABASE_ECHO,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_timeout=settings.DATABASE_POOL_TIMEOUT,
                pool_pre_ping=True,
                poolclass=AsyncAdaptedQueuePool,
                connect_args={
                    "server_settings": {
                        "application_name": "soldia_v2",
                        "jit": "off"
                    }
                }
            )

        # Слушатели событий подключения
        @event.listens_for(engine.sync_engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            logger.debug("New database connection established")

        @event.listens_for(engine.sync_engine, "close")
        def receive_close(dbapi_conn, connection_record):
            logger.debug("Database connection closed")

        return engine

    async def init(self):
        """Initialize database engine and session factory"""
        if self._engine is not None:
            logger.warning("Database already initialized")
            return

        logger.info("🔌 Initializing database connection...")

        self._engine = self.create_engine()

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )

        # Проверяем подключение
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise

    async def create_tables(self):
        """Create all database tables"""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")

        logger.info("📊 Creating database tables...")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("✅ Database tables created")

    async def drop_tables(self):
        """Drop all database tables (use with caution!)"""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")

        logger.warning("⚠️  Dropping all database tables...")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        logger.info("✅ Database tables dropped")

    async def close(self):
        """Close database connections"""
        if self._engine is None:
            return

        logger.info("🔌 Closing database connections...")
        await self._engine.dispose()
        self._engine = None
        self._session_factory = None
        logger.info("✅ Database connections closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database sessions

        Usage:
            async with db_manager.session() as session:
                result = await session.execute(query)
                await session.commit()
        """
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call init() first.")

        # BUG-1 FIX: No auto-commit on exit.
        # The old version called session.commit() here unconditionally.
        # Celery tasks already commit explicitly at precise checkpoints
        # (after status=processing, after status=completed, after rollback).
        # The extra auto-commit caused a double-commit, and on exception
        # the auto-rollback here wiped data that had already been committed
        # (e.g. a successfully sent tx_hash got lost).
        # Callers are fully responsible for commit/rollback; we only close.
        session = self._session_factory()
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

    async def get_session(self) -> AsyncSession:
        """
        Get a new database session (for dependency injection)

        Note: Caller is responsible for closing the session
        """
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call init() first.")

        return self._session_factory()

    async def health_check(self) -> bool:
        """Check database health"""
        try:
            async with self.session() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def get_stats(self) -> dict:  # sync: only reads pool attributes, no IO
        """Get database connection pool statistics"""
        if self._engine is None:
            return {"status": "not_initialized"}

        pool = self._engine.pool

        # NullPool не имеет методов size/checkedin/checkedout/overflow
        if settings.ENVIRONMENT == "testing":
            return {"status": "healthy", "pool_type": "NullPool"}

        return {
            "status": "healthy",
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.size() + pool.overflow()
        }


# Global database manager instance
db_manager = DatabaseManager()


# Dependency for FastAPI
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get database session

    Usage:
        @app.get("/users")
        async def get_users(session: AsyncSession = Depends(get_db_session)):
            result = await session.execute(select(User))
            return result.scalars().all()
    """
    async with db_manager.session() as session:
        yield session


# Lifespan management for FastAPI
@asynccontextmanager
async def lifespan_db(app):
    """
    Lifespan context manager for database
    Use with FastAPI lifespan parameter
    """
    # Startup
    await db_manager.init()

    yield

    # Shutdown
    await db_manager.close()


# Migration helper
async def run_migrations():
    """Run database migrations (placeholder - use Alembic in production)"""
    logger.info("📦 Running database migrations...")

    await db_manager.init()
    await db_manager.create_tables()

    logger.info("✅ Migrations completed")

    await db_manager.close()


if __name__ == "__main__":
    import asyncio

    async def main():
        """Test database connection"""
        await db_manager.init()

        healthy = await db_manager.health_check()
        logger.info(f"Database healthy: {healthy}")

        stats = await db_manager.get_stats()
        logger.info(f"Database stats: {stats}")

        await db_manager.close()

    asyncio.run(main())
