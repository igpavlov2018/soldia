"""
✅ FIXED v2.8: Withdrawal Processing Tasks

ИСПРАВЛЕНИЯ v2.8:
  БАГ-B: Withdrawal в статусе "processing" не подбирался ни одной задачей.
         Если воркер падал после commit("processing") но до commit("completed"),
         запись навсегда застревала в "processing". user.total_withdrawn был
         увеличен, но USDC не отправлен. Пользователь терял возможность
         вывода без ручного вмешательства в БД.
         Исправление: добавлен отдельный timeout для "processing" записей
         (PROCESSING_TIMEOUT_MINUTES = 15). Обрабатывается до stale_pending
         секции. Логика возврата средств идентична stale_pending.

  КОС-1: Заголовок обновлён с v2.6 на v2.8.

ИСПРАВЛЕНИЯ v2.6 (сохранены):
  N1: stale_withdrawals SELECT добавлен SKIP LOCKED.
  N2: send_withdrawal различает "not found" и "locked by another worker".
  BUG-2 / OBS-8: все pending SELECT используют SKIP LOCKED.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from tasks.worker import celery
from database.manager import db_manager
from models.database import Withdrawal, User
from sqlalchemy import select, update
from config.settings import constants

logger = logging.getLogger(__name__)

# Таймаут для зависших pending-выводов (в минутах)
PENDING_TIMEOUT_MINUTES = 30

# БАГ-B FIX: Таймаут для зависших processing-выводов (в минутах).
# "processing" означает что воркер взял задачу и сделал commit.
# Если воркер упал до завершения — запись застрянет в "processing".
# 15 минут достаточно для любой blockchain операции; если дольше — воркер мёртв.
PROCESSING_TIMEOUT_MINUTES = 15


@celery.task(name='tasks.withdrawals.process_pending_withdrawals')
def process_pending_withdrawals():
    """
    Периодическая задача обработки pending выводов.
    Отправляет USDC с hot wallet и обновляет статус.

    BUG-2 / N1 FIX: оба SELECT (stale + pending) используют SKIP LOCKED —
    исключает двойную обработку при параллельных воркерах.
    """
    import asyncio
    from blockchain.solana_client import solana_client

    async def _process():
        logger.info("💰 Processing pending withdrawals...")

        async with db_manager.session() as session:
            now = datetime.now(timezone.utc)
            timeout_threshold = now - timedelta(minutes=PENDING_TIMEOUT_MINUTES)
            processing_threshold = now - timedelta(minutes=PROCESSING_TIMEOUT_MINUTES)

            # БАГ-B FIX: сначала откатываем зависшие "processing" записи.
            # Воркер мог упасть после commit("processing") но до commit("completed").
            # Такая запись никогда не подбирается: pending-фильтр её не видит,
            # send_withdrawal явно пропускает (status != PENDING).
            # Решение: timeout для "processing" аналогичен timeout для "pending".
            result = await session.execute(
                select(Withdrawal).where(
                    Withdrawal.status == "processing",
                    Withdrawal.updated_at < processing_threshold
                ).with_for_update(skip_locked=True)
            )
            stuck_processing = result.scalars().all()

            for wd in stuck_processing:
                logger.warning(
                    f"⏰ Withdrawal {wd.id} stuck in 'processing' for "
                    f">{PROCESSING_TIMEOUT_MINUTES}m — marking failed and releasing funds"
                )
                from sqlalchemy import func as sqlfunc
                completed_count_result = await session.execute(
                    select(sqlfunc.count(Withdrawal.id)).where(
                        Withdrawal.user_id == wd.user_id,
                        Withdrawal.status == constants.STATUS_COMPLETED,
                    )
                )
                completed_count = completed_count_result.scalar() or 0
                # LOW-1 FIX: commit after each entry so the next iteration sees
                # the correct completed_count and last_withdrawal_at state.
                is_first_withdrawal = completed_count == 0

                await session.execute(
                    update(User)
                    .where(User.id == wd.user_id)
                    .values(
                        total_withdrawn=User.total_withdrawn - wd.amount,
                        last_withdrawal_at=None if is_first_withdrawal else User.last_withdrawal_at,
                    )
                )
                wd.status = constants.STATUS_FAILED
                wd.error_message = (
                    f"Worker crashed during processing — timed out after "
                    f"{PROCESSING_TIMEOUT_MINUTES} minutes"
                )
                # LOW-1 FIX: commit per entry, not once for the whole batch.
                # If two stuck withdrawals belong to the same user, reading
                # completed_count before any commit would report the wrong
                # is_first_withdrawal for the second one.
                await session.commit()
                logger.info(f"Released funds for stuck-processing withdrawal {wd.id}")

            if stuck_processing:
                logger.info(
                    f"Released funds for {len(stuck_processing)} stuck-processing withdrawals"
                )

            # PENDING TTL FIX: сначала переводим зависшие записи в failed.
            # N1 FIX: SKIP LOCKED — без него два воркера оба выбирают одни stale
            # rows и оба возвращают средства → двойной возврат total_withdrawn.
            result = await session.execute(
                select(Withdrawal).where(
                    Withdrawal.status == constants.STATUS_PENDING,
                    Withdrawal.created_at < timeout_threshold
                ).with_for_update(skip_locked=True)
            )
            stale_withdrawals = result.scalars().all()

            for wd in stale_withdrawals:
                logger.warning(
                    f"⏰ Withdrawal {wd.id} stuck in pending for >{PENDING_TIMEOUT_MINUTES}m — "
                    f"marking failed and releasing funds"
                )
                # M1 FIX: only reset last_withdrawal_at on first withdrawal attempt.
                from sqlalchemy import func as sqlfunc
                completed_count_result = await session.execute(
                    select(sqlfunc.count(Withdrawal.id)).where(
                        Withdrawal.user_id == wd.user_id,
                        Withdrawal.status == constants.STATUS_COMPLETED,
                    )
                )
                completed_count = completed_count_result.scalar() or 0
                is_first_withdrawal = completed_count == 0

                await session.execute(
                    update(User)
                    .where(User.id == wd.user_id)
                    .values(
                        total_withdrawn=User.total_withdrawn - wd.amount,
                        last_withdrawal_at=None if is_first_withdrawal else User.last_withdrawal_at,
                    )
                )
                wd.status = constants.STATUS_FAILED
                wd.error_message = f"Timed out after {PENDING_TIMEOUT_MINUTES} minutes in pending state"

            if stale_withdrawals:
                await session.commit()
                logger.info(f"Released funds for {len(stale_withdrawals)} stale withdrawals")

            # BUG-2 FIX: SKIP LOCKED — prevents two workers from sending USDC twice.
            result = await session.execute(
                select(Withdrawal).where(
                    Withdrawal.status == constants.STATUS_PENDING
                ).with_for_update(skip_locked=True).limit(10)
            )

            pending = result.scalars().all()

            if not pending:
                logger.info("No pending withdrawals")
                return 0

            # MEDIUM-1 FIX + BUG-FIX: Extract IDs INSIDE the async with block,
            # before the session closes. After session.close() SQLAlchemy expires
            # all ORM objects — accessing wd.id outside the block would raise
            # DetachedInstanceError / MissingGreenlet in asyncio.
            pending_ids = [wd.id for wd in pending]

        # Each withdrawal is processed in its own isolated session (MEDIUM-1 FIX).
        # Previously all 10 withdrawals shared one session — an exception + rollback
        # would expire all other ORM objects in that session (same BUG-A pattern
        # fixed in deposits in v2.8).
        logger.info(f"Found {len(pending_ids)} pending withdrawals")
        processed = 0

        for wd_id in pending_ids:
            try:
                ok = await _process_one_withdrawal(wd_id, solana_client)
                if ok:
                    processed += 1
            except Exception as e:
                logger.error(f"Error processing withdrawal id={wd_id}: {e}", exc_info=True)

        logger.info(f"Processed {processed}/{len(pending_ids)} withdrawals successfully")
        return processed

    async def _process_one_withdrawal(wd_id: int, solana_client) -> bool:
        """Process a single withdrawal in an isolated session."""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Withdrawal).where(
                    Withdrawal.id == wd_id,
                    Withdrawal.status == constants.STATUS_PENDING
                ).with_for_update(skip_locked=True)
            )
            withdrawal = result.scalar_one_or_none()

            if not withdrawal:
                return False  # Already taken by another worker or processed

            # Cache values before any commits to guard against ORM expiry
            wd_id_val = withdrawal.id
            wd_user_id = withdrawal.user_id
            wd_amount = withdrawal.amount
            wd_wallet = withdrawal.wallet_address

            logger.info(
                f"Processing withdrawal ID: {wd_id_val}, "
                f"Amount: {wd_amount} USDC, To: {wd_wallet}"
            )

            withdrawal.status = "processing"
            await session.commit()

            try:
                tx_signature = await solana_client.send_usdc(
                    to_wallet=wd_wallet,
                    amount=wd_amount,
                )

                if tx_signature:
                    withdrawal.status = constants.STATUS_COMPLETED
                    withdrawal.tx_hash = tx_signature
                    withdrawal.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.info(f"✅ Withdrawal {wd_id_val} completed: {tx_signature}")
                    return True
                else:
                    raise Exception("No signature returned from blockchain")

            except Exception as e:
                logger.error(f"❌ Error processing withdrawal {wd_id_val}: {e}")

                # CRITICAL FIX: if the exception came from session.commit() for
                # STATUS_COMPLETED, PostgreSQL puts the transaction in ABORTED state.
                # Any execute() without a prior rollback() will fail with
                # "current transaction is aborted, commands ignored".
                # rollback() here clears the aborted state so we can run the
                # fund-release UPDATE safely.
                await session.rollback()

                from sqlalchemy import func as sqlfunc
                _completed = await session.execute(
                    select(sqlfunc.count(Withdrawal.id)).where(
                        Withdrawal.user_id == wd_user_id,
                        Withdrawal.status == constants.STATUS_COMPLETED,
                    )
                )
                _is_first = (_completed.scalar() or 0) == 0

                await session.execute(
                    update(User)
                    .where(User.id == wd_user_id)
                    .values(
                        total_withdrawn=User.total_withdrawn - wd_amount,
                        last_withdrawal_at=None if _is_first else User.last_withdrawal_at,
                    )
                )

                withdrawal.status = constants.STATUS_FAILED
                withdrawal.error_message = str(e)
                await session.commit()
                logger.warning(f"Funds released for failed withdrawal {wd_id_val}")
                return False

    # WARN-2/3 FIX: Use the persistent event loop set by worker_process_init.
    # Do NOT create a new_event_loop() here — it would invalidate the asyncpg
    # connection pool (connections are bound to the loop from init_worker_db).
    try:
        _loop = asyncio.get_event_loop()
        try:
            return _loop.run_until_complete(_process())
        finally:
            pass  # WARN-2/3: Do NOT close the persistent loop
    except Exception as e:
        logger.error(f"Error in process_pending_withdrawals: {e}", exc_info=True)
        return 0


@celery.task(name='tasks.withdrawals.send_withdrawal')
def send_withdrawal(withdrawal_id: int):
    """
    Отправка USDC для конкретного вывода.

    N2 FIX: SELECT FOR UPDATE SKIP LOCKED корректно различает
    «запись не существует» и «запись заблокирована другим воркером».
    Предыдущая версия возвращала «not found» в обоих случаях.
    """
    import asyncio
    from blockchain.solana_client import solana_client

    async def _send():
        logger.info(f"💸 Sending withdrawal {withdrawal_id}")

        async with db_manager.session() as session:
            # N2 FIX: Two-step approach to distinguish "not found" from "locked".
            # Step 1: check existence WITHOUT lock.
            exists_result = await session.execute(
                select(Withdrawal.id).where(Withdrawal.id == withdrawal_id)
            )
            if not exists_result.scalar_one_or_none():
                logger.error(f"Withdrawal {withdrawal_id} not found in database")
                return {"success": False, "error": "Withdrawal not found"}

            # Step 2: try to acquire lock with SKIP LOCKED.
            # OBS-8 FIX: prevents race with process_pending_withdrawals.
            result = await session.execute(
                select(Withdrawal).where(
                    Withdrawal.id == withdrawal_id
                ).with_for_update(skip_locked=True)
            )
            withdrawal = result.scalar_one_or_none()

            if not withdrawal:
                # Record exists (checked above) but is locked → already being processed.
                logger.warning(
                    f"Withdrawal {withdrawal_id} is locked by another worker — skipping"
                )
                return {"success": False, "error": "Already being processed by another worker"}

            if withdrawal.status != constants.STATUS_PENDING:
                logger.warning(
                    f"Withdrawal {withdrawal_id} already processed (status: {withdrawal.status})"
                )
                return {"success": False, "error": f"Withdrawal already {withdrawal.status}"}

            # Cache primitive values NOW — before any commit() or rollback().
            # rollback() expires all ORM-mapped attributes on every object in the
            # session. Reading withdrawal.user_id or withdrawal.amount after
            # rollback() would trigger a lazy-load which raises MissingGreenlet
            # in an async context (no sync IO allowed).
            wd_user_id   = withdrawal.user_id
            wd_amount    = withdrawal.amount
            wd_wallet    = withdrawal.wallet_address

            withdrawal.status = "processing"
            await session.commit()

            try:
                logger.info(f"Sending {wd_amount} USDC to {wd_wallet}")

                tx_signature = await solana_client.send_usdc(
                    to_wallet=wd_wallet,
                    amount=wd_amount,
                )

                if not tx_signature:
                    raise Exception("No signature returned from blockchain")

                withdrawal.status = constants.STATUS_COMPLETED
                withdrawal.tx_hash = tx_signature
                withdrawal.completed_at = datetime.now(timezone.utc)
                await session.commit()

                logger.info(f"✅ Withdrawal {withdrawal_id} completed: {tx_signature}")

                return {
                    "success": True,
                    "tx_hash": tx_signature,
                    "amount": str(wd_amount),
                    "wallet": wd_wallet,
                }

            except Exception as e:
                logger.error(f"❌ Error sending withdrawal {withdrawal_id}: {e}", exc_info=True)

                # rollback() clears aborted-transaction state (if commit() threw)
                # AND expires all ORM attrs — that's why we cached wd_user_id /
                # wd_amount / wd_wallet above before the first commit().
                await session.rollback()

                from sqlalchemy import func as sqlfunc
                _completed2 = await session.execute(
                    select(sqlfunc.count(Withdrawal.id)).where(
                        Withdrawal.user_id == wd_user_id,
                        Withdrawal.status == constants.STATUS_COMPLETED,
                    )
                )
                _is_first2 = (_completed2.scalar() or 0) == 0

                await session.execute(
                    update(User)
                    .where(User.id == wd_user_id)
                    .values(
                        total_withdrawn=User.total_withdrawn - wd_amount,
                        last_withdrawal_at=None if _is_first2 else User.last_withdrawal_at,
                    )
                )

                withdrawal.status = constants.STATUS_FAILED
                withdrawal.error_message = str(e)
                await session.commit()

                logger.warning(f"Funds released for failed withdrawal {withdrawal_id}")
                return {"success": False, "error": str(e), "withdrawal_id": withdrawal_id}

    # WARN-2/3 FIX: Use the persistent event loop set by worker_process_init.
    # Do NOT create a new_event_loop() here — it would invalidate the asyncpg
    # connection pool (connections are bound to the loop from init_worker_db).
    try:
        _loop = asyncio.get_event_loop()
        try:
            return _loop.run_until_complete(_send())
        finally:
            pass  # WARN-2/3: Do NOT close the persistent loop
    except Exception as e:
        logger.error(f"Error in send_withdrawal task: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
