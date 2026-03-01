"""
✅ FIXED v2.9: Celery Worker Configuration

ИСПРАВЛЕНИЯ v2.9 (WARN-2/3):
  Проблема: Celery tasks создавали asyncio.new_event_loop() на каждый вызов задачи
  и закрывали его в finally. SQLAlchemy asyncpg QueuePool хранит соединения
  привязанными к event loop. После _loop.close() соединения в пуле становились
  невалидными → при следующем вызове задачи возникал RuntimeError: Event loop is closed.

  Решение: worker_process_init создаёт ОДИН persistent event loop на весь
  процесс Celery worker и устанавливает его через asyncio.set_event_loop().
  Все задачи в этом процессе используют один и тот же loop через
  asyncio.get_event_loop().run_until_complete(). Пул соединений asyncpg
  живёт на протяжении всего времени жизни процесса без пересоздания.

  db_manager.init() вызывается один раз в worker_process_init.
  Задачи используют asyncio.get_event_loop() (не new_event_loop()).

  Также: SolanaClient(RPC connection) сбрасывается при форке — каждый
  воркер создаёт собственное HTTP-соединение.

СОХРАНЕНО от v2.8:
  BUG-CELERY-INIT FIX: db_manager.init() через worker_process_init
  OBS-7 FIX: Redis singleton сброс после fork
"""

import asyncio
import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_process_shutdown
from config.settings import settings

logger = logging.getLogger(__name__)

# Create Celery instance
celery = Celery(
    'soldia',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['tasks.deposits', 'tasks.withdrawals', 'tasks.split_retry']
)

# Celery configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Periodic tasks
celery.conf.beat_schedule = {
    'check-pending-deposits': {
        'task': 'tasks.deposits.check_pending_deposits',
        'schedule': 60.0,  # Every 60 seconds
    },
    'process-pending-withdrawals': {
        'task': 'tasks.withdrawals.process_pending_withdrawals',
        'schedule': 300.0,  # Every 5 minutes
    },
    'retry-failed-splits': {
        'task': 'tasks.split_retry.retry_failed_splits',
        'schedule': 1800.0,  # Every 30 minutes
    },
    # NOTE: reset_daily_limits / reset_monthly_limits removed in v2.2
    #       (no daily/monthly limits in this business model).
}


@worker_process_init.connect
def init_worker_db(**kwargs):
    """
    BUG-CELERY-INIT FIX: Initialize db_manager once per Celery worker process.

    WARN-2/3 FIX (v2.9): Create ONE persistent event loop for the entire worker
    process and register it via asyncio.set_event_loop().

    Previous approach created asyncio.new_event_loop() inside each Celery task
    and closed it in finally. Problem: SQLAlchemy asyncpg QueuePool stores
    connections bound to a specific event loop. Closing the loop invalidates
    all pooled connections → next task call raises RuntimeError: Event loop is closed.

    Fix: Create ONE loop here, set it as the thread's event loop, initialize
    db_manager on it. All tasks call asyncio.get_event_loop().run_until_complete()
    which reuses this same loop. The asyncpg connection pool lives for the entire
    worker process lifetime without being invalidated.

    OBS-7 FIX: Reset Redis and Solana client singletons inherited from parent
    process after fork. In Celery prefork mode, child processes inherit open
    file descriptors from the parent. Multiple asyncio event loops sharing a
    single socket causes data corruption and hangs.

    Called automatically by Celery once per process before accepting tasks.
    """
    # OBS-7 FIX: Reset singletons inherited from parent process after fork
    import security.web3_auth as _w3a
    _w3a._redis_client = None
    _w3a._instance = None

    # WARN-2/3 FIX: Also reset SolanaClient — it holds an HTTP session bound
    # to the parent's event loop. Each worker process needs its own connection.
    try:
        from blockchain.solana_client import solana_client as _sc
        _sc.client = None  # Force reconnect in the new event loop
    except Exception:
        pass

    # WARN-2/3 FIX: Create ONE persistent event loop for this worker process.
    # Tasks will reuse it via asyncio.get_event_loop() — NOT new_event_loop().
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    from database.manager import db_manager

    try:
        _loop.run_until_complete(db_manager.init())
        logger.info("✅ Celery worker: db_manager initialized on persistent event loop")
    except Exception as exc:
        logger.error(f"❌ Celery worker: db_manager init failed: {exc}")
        raise  # Worker must not start without a database connection


@worker_process_shutdown.connect
def shutdown_worker_db(**kwargs):
    """
    Clean shutdown: close db_manager and event loop when worker process exits.
    Prevents ResourceWarning about unclosed connections.
    """
    _loop = asyncio.get_event_loop()
    if _loop and not _loop.is_closed():
        try:
            from database.manager import db_manager
            _loop.run_until_complete(db_manager.close())
            logger.info("✅ Celery worker: db_manager closed on shutdown")
        except Exception as exc:
            logger.warning(f"Worker shutdown cleanup error (non-fatal): {exc}")
        finally:
            _loop.close()


if __name__ == '__main__':
    celery.start()
