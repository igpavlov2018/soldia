"""
✅ FIXED v2.8: Deposit Processing Tasks

ИСПРАВЛЕНИЯ v2.8:
  БАГ-A: check_pending_deposits использовал один db session на весь batch.
         После session.rollback() в except блоке SQLAlchemy async expiry
         ВСЕ объекты в сессии (это не настраивается через expire_on_commit).
         Следующая итерация обращалась к tx.tx_hash expired объекта →
         lazy load в asyncio → MissingGreenlet exception → cascade fallout
         для всего оставшегося batch.
         Исправление: каждая транзакция обрабатывается в своей сессии.
         Rollback одной записи не затрагивает другие.

  АРХ-1: process_referral_earnings вынесена в services/referral.py.
         Celery task не должен импортировать из api/routes/ (инверсия слоёв).

ИСПРАВЛЕНИЯ v2.7 (сохранены):
  OBS-5: check_pending_deposits реализует полную бизнес-логику:
         user.deposit_amount / deposit_level / first_deposit_at,
         process_referral_earnings(), ProcessedTransaction, IntegrityError,
         SKIP LOCKED.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from tasks.worker import celery
from database.manager import db_manager
from models.database import Transaction, User, ProcessedTransaction
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from config.settings import constants

logger = logging.getLogger(__name__)


@celery.task(name='tasks.deposits.check_pending_deposits')
def check_pending_deposits():
    """
    Периодическая задача верификации pending депозитов.

    БАГ-A FIX: Каждая транзакция обрабатывается в отдельной сессии.
    Это гарантирует что rollback/ошибка на одной записи не влияет на
    остальные записи в batch — у них своя изолированная сессия.

    OBS-5 FIX: Реализована полная бизнес-логика:
      1. Получаем ID pending Transaction записей (SKIP LOCKED)
      2. Для каждой — новая сессия, полная обработка
      3. Устанавливаем user.deposit_amount / deposit_level / first_deposit_at
      4. Начисляем реферальные доходы через process_referral_earnings()
      5. Создаём ProcessedTransaction (идемпотентность)
      6. Защита от race condition через IntegrityError
    """
    import asyncio
    from blockchain.solana_client import solana_client
    from config.settings import settings
    from services.referral import process_referral_earnings
    from services.deposit_split import split_deposit

    async def _process_one(tx_id: int) -> bool:
        """
        Обрабатывает одну pending транзакцию в изолированной сессии.
        Возвращает True если депозит успешно верифицирован.
        """
        async with db_manager.session() as session:
            # Берём запись с блокировкой. SKIP LOCKED — если другой воркер
            # уже взял эту запись, мы её пропускаем без ошибки.
            result = await session.execute(
                select(Transaction).where(
                    Transaction.id == tx_id,
                    Transaction.status == constants.STATUS_PENDING
                ).with_for_update(skip_locked=True)
            )
            tx = result.scalar_one_or_none()

            if not tx:
                # Либо уже обработана другим воркером, либо заблокирована — ok
                return False

            # Сохраняем нужные значения в локальные переменные сразу.
            # Это защищает от любых проблем с ORM state в процессе работы.
            tx_id_val = tx.id
            tx_hash = tx.tx_hash
            tx_amount = tx.amount
            tx_user_id = tx.user_id

            logger.info(f"Verifying TX: {tx_hash}, Amount: {tx_amount} USDC")

            # Проверяем идемпотентность — не обработана ли уже
            already = await session.execute(
                select(ProcessedTransaction).where(
                    ProcessedTransaction.tx_hash == tx_hash
                )
            )
            if already.scalar_one_or_none():
                logger.warning(f"TX {tx_hash} already processed — marking completed")
                tx.status = constants.STATUS_COMPLETED
                await session.commit()
                return False

            # Получаем пользователя с блокировкой строки
            user_result = await session.execute(
                select(User).where(
                    User.id == tx_user_id
                ).with_for_update()
            )
            user = user_result.scalar_one_or_none()

            if not user:
                logger.error(f"User {tx_user_id} not found for TX {tx_hash}")
                tx.status = constants.STATUS_FAILED
                tx.error_message = f"User {tx_user_id} not found"
                await session.commit()
                return False

            # Один депозит на пользователя
            if user.deposit_amount > Decimal("0"):
                logger.warning(f"User {user.id} already has deposit — marking TX completed")
                tx.status = constants.STATUS_COMPLETED
                await session.commit()
                return False

            # Верификация в блокчейне
            verification = await solana_client.verify_usdc_transaction(
                tx_hash=tx_hash,
                expected_recipient=settings.MAIN_WALLET_TOKEN,
                expected_amount=Decimal(str(tx_amount)),
                tolerance=constants.AMOUNT_TOLERANCE
            )

            if not verification["valid"]:
                logger.warning(
                    f"⚠️ Verification failed for {tx_hash}: {verification.get('error')}"
                )
                # Не помечаем как failed — может быть временная ошибка RPC
                return False

            # Определяем уровень депозита
            deposit_level = None
            for level, tier_amount in constants.TIER_AMOUNTS.items():
                if abs(tx_amount - tier_amount) <= constants.AMOUNT_TOLERANCE:
                    deposit_level = level
                    break

            if not deposit_level:
                logger.error(f"Invalid deposit amount {tx_amount} for TX {tx_hash}")
                tx.status = constants.STATUS_FAILED
                tx.error_message = f"Invalid deposit amount: {tx_amount}"
                await session.commit()
                return False

            # OBS-5 FIX: Обновляем пользователя
            user.deposit_amount = tx_amount
            user.deposit_level = deposit_level
            user.deposit_tx_hash = tx_hash
            user.first_deposit_at = datetime.now(timezone.utc)

            # Обновляем статус транзакции
            tx.status = constants.STATUS_COMPLETED
            tx.completed_at = datetime.now(timezone.utc)

            # OBS-5 FIX: Начисляем реферальные доходы
            await process_referral_earnings(user, tx_amount, session)

            # OBS-5 FIX: Создаём ProcessedTransaction для идемпотентности
            processed = ProcessedTransaction(
                tx_hash=tx_hash,
                user_id=user.id,
                transaction_type=constants.TX_TYPE_DEPOSIT
            )
            session.add(processed)

            # Commit с защитой от race condition
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.warning(
                    f"Concurrent deposit processing for {tx_hash} — skipping"
                )
                return False

            logger.info(
                f"✅ Deposit processed: user={user.id} "
                f"amount={tx_amount} level={deposit_level} tx={tx_hash}"
            )

            # ── 60/40 SPLIT ───────────────────────────────────────────────
            # Non-fatal: deposit is already committed above.
            # Split failure is logged to audit_logs and retried by Celery.
            split_result = await split_deposit(
                deposit_amount=tx_amount,
                user_id=user.id,
                tx_hash=tx_hash,
                session=session,
            )
            if split_result["cold_success"]:
                logger.info(
                    f"💸 Cold split: {split_result['cold_amount']} USDC → cold wallet "
                    f"(tx: {split_result['cold_tx']})"
                )
            else:
                logger.warning(
                    f"⚠️ Cold split failed for {tx_hash}: "
                    f"{split_result['cold_error']} — will retry automatically"
                )
            if split_result["gas_success"]:
                logger.info(
                    f"⛽ Gas swap: {split_result['gas_amount']} USDC → SOL "
                    f"(tx: {split_result['gas_swap_tx']})"
                )
            else:
                logger.warning(
                    f"⚠️ Gas swap failed for {tx_hash}: "
                    f"{split_result['gas_error']} — will retry automatically"
                )
            # Commit audit logs written by split_deposit
            try:
                await session.commit()
            except Exception as commit_err:
                logger.warning(f"Split audit log commit failed (non-fatal): {commit_err}")

            return True

    async def _check():
        logger.info("🔍 Checking for pending deposits...")

        # Шаг 1: получаем только ID pending записей в короткой сессии.
        # Не держим долгую блокировку на весь batch — только считываем ID.
        async with db_manager.session() as session:
            result = await session.execute(
                select(Transaction.id).where(
                    Transaction.type == constants.TX_TYPE_DEPOSIT,
                    Transaction.status == constants.STATUS_PENDING
                ).limit(10)
            )
            pending_ids = result.scalars().all()

        if not pending_ids:
            logger.info("No pending deposits")
            return 0

        logger.info(f"Found {len(pending_ids)} pending deposits")

        # Шаг 2: каждый ID обрабатывается в своей изолированной сессии.
        # Ошибка/rollback на одном ID никак не влияет на другие.
        verified_count = 0
        for tx_id in pending_ids:
            try:
                ok = await _process_one(tx_id)
                if ok:
                    verified_count += 1
            except Exception as e:
                logger.error(f"Error processing deposit id={tx_id}: {e}", exc_info=True)
                # Продолжаем — следующий tx_id в своей сессии

        logger.info(f"Processed {verified_count}/{len(pending_ids)} deposits")
        return verified_count

    # WARN-2/3 FIX: Use the persistent event loop set by worker_process_init.
    # Do NOT create a new_event_loop() here — it would invalidate the asyncpg
    # connection pool (connections are bound to the loop from init_worker_db).
    try:
        _loop = asyncio.get_event_loop()
        try:
            return _loop.run_until_complete(_check())
        finally:
            pass  # WARN-2/3: Do NOT close the persistent loop
    except Exception as e:
        logger.error(f"Error in check_pending_deposits: {e}", exc_info=True)
        return 0


@celery.task(name='tasks.deposits.verify_deposit')
def verify_deposit(tx_hash: str, wallet_address: str, amount: str):
    """
    Verify specific deposit transaction.

    Args:
        tx_hash: Solana transaction signature
        wallet_address: User's wallet address
        amount: Expected amount in USDC as string (avoids float JSON precision loss)

    Returns:
        bool: True if verified successfully
    """
    import asyncio
    from blockchain.solana_client import solana_client
    from config.settings import settings

    async def _verify():
        logger.info(f"🔍 Verifying deposit: {tx_hash}")
        try:
            verification = await solana_client.verify_usdc_transaction(
                tx_hash=tx_hash,
                expected_recipient=settings.MAIN_WALLET_TOKEN,
                expected_amount=Decimal(str(amount)),
                tolerance=constants.AMOUNT_TOLERANCE
            )
            if verification["valid"]:
                logger.info(f"✅ Deposit verified: {tx_hash}")
                logger.info(f"  Amount: {verification['amount']} USDC")
                logger.info(f"  Sender: {verification['sender']}")
                return True
            else:
                logger.error(f"❌ Verification failed: {verification.get('error')}")
                return False
        except Exception as e:
            logger.error(f"❌ Error during verification: {e}")
            return False

    # WARN-2/3 FIX: Use the persistent event loop set by worker_process_init.
    # Do NOT create a new_event_loop() here — it would invalidate the asyncpg
    # connection pool (connections are bound to the loop from init_worker_db).
    try:
        _loop = asyncio.get_event_loop()
        try:
            return _loop.run_until_complete(_verify())
        finally:
            pass  # WARN-2/3: Do NOT close the persistent loop
    except Exception as e:
        logger.error(f"Error verifying deposit: {e}", exc_info=True)
        return False
