"""
✅ FIXED v2.5: Deposit API Routes

ИСПРАВЛЕНИЯ v2.5:
  OBS-3: float() → str() во всех audit log записях и financial_logger.
         Комментарий SER-2 декларировал «no float() anywhere», но 7 вызовов
         float() оставались в audit logs. Теперь все суммы — строки Decimal.

Без изменений от v2.4: CRIT-3/4, N+1, ARCH-3.
"""

import logging
import json
import hmac
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, case, and_
from slowapi import Limiter

from database.manager import get_db_session
from models.database import User, Transaction, ProcessedTransaction, AuditLog
from api.schemas.deposit import (
    DepositVerifyRequest,
    DepositVerifyResponse,
    DepositListResponse,
    PendingDeposit
)
from config.settings import constants, settings
from cache.manager import cache_manager
from security.auth import security_utils, rate_limit_utils
from services.referral import process_referral_earnings
from services.deposit_split import split_deposit

logger = logging.getLogger(__name__)
financial_logger = logging.getLogger('financial')
router = APIRouter()


# ==================== RATE LIMIT KEY: trusted IP from nginx ====================

def _real_ip(request: Request) -> str:
    """
    CRIT-4 FIX: Используем X-Real-IP (устанавливается nginx из $remote_addr).
    Клиент не может подделать этот заголовок — nginx перезаписывает его безусловно.
    В nginx.conf должно быть: proxy_set_header X-Real-IP $remote_addr;
    X-Forwarded-For[0] — клиентский заголовок, нельзя доверять.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    # Только для dev/прямых подключений без nginx
    return request.client.host if request.client else "0.0.0.0"


limiter = Limiter(key_func=_real_ip)


# ==================== ADMIN KEY CHECK ====================

def _require_admin(x_admin_key: Optional[str]) -> None:
    """
    CRIT-3 FIX: Ключ передаётся только в заголовке X-Admin-Key, не в URL.

    URL query-параметры логируются: nginx access log, AWS CloudTrail,
    история браузера, CDN логи, Sentry breadcrumbs и т.д.
    Заголовки по умолчанию не логируются ни в одном из этих мест.

    hmac.compare_digest — константное время сравнения (защита от timing-атак).
    ADMIN_API_KEY — отдельный ключ, никогда не производный от SECRET_KEY.
    """
    expected = settings.ADMIN_API_KEY
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )


# ==================== DEPOSIT VERIFY ====================

@router.post("/verify", response_model=DepositVerifyResponse)
@limiter.limit(constants.RATE_LIMIT_DEPOSIT)
async def verify_deposit(
    body: DepositVerifyRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session)
):
    """
    ✅ FIXED v2.4: Верификация и обработка депозита

    Безопасность:
    ✅ Один депозит на пользователя
    ✅ Проверка дубликата транзакции (идемпотентность)
    ✅ Верификация транзакции в блокчейне Solana
    ✅ Проверка получателя и суммы
    ✅ Атомарное начисление реферальных доходов
    ✅ Защита от race condition через IntegrityError
    ✅ Полный audit log
    ✅ CRIT-4: Лимитер использует X-Real-IP (nginx)
    """

    ip_address = rate_limit_utils.get_client_ip(request)
    user_agent = rate_limit_utils.get_user_agent(request)

    from sqlalchemy.exc import IntegrityError

    try:
        # CRIT-2 FIX: Verify Ed25519 signature before any DB operations.
        # Proves the caller owns wallet_address — prevents anyone from claiming
        # a tx_hash they don't own. Message format must match the frontend.
        from security.web3_auth import verify_solana_signature
        deposit_message = f"Deposit {body.tx_hash}"
        if not await verify_solana_signature(deposit_message, body.signature, body.wallet_address):
            audit_log = AuditLog(
                event_type="deposit_bad_signature",
                ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "wallet": body.wallet_address,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False, error_message="Invalid wallet signature"
            )
            session.add(audit_log)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid wallet signature."
            )

        # Проверка — транзакция уже обработана?
        result = await session.execute(
            select(ProcessedTransaction).where(
                ProcessedTransaction.tx_hash == body.tx_hash
            )
        )
        if result.scalar_one_or_none():
            audit_log = AuditLog(
                event_type="deposit_duplicate",
                ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "wallet": body.wallet_address,
                    "amount": str(body.amount),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False, error_message="Transaction already processed"
            )
            session.add(audit_log)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transaction already processed"
            )

        # Получаем пользователя — с блокировкой строки
        # ARCH-3 FIX: SELECT FOR UPDATE prevents race condition where two concurrent requests
        # with the same tx_hash both pass the "no deposit yet" check before either commits.
        # The second request will block here until the first commits, then see deposit_amount > 0
        # and correctly reject. Without this lock, process_referral_earnings could run twice
        # in parallel (though IntegrityError on ProcessedTransaction prevents double-commit).
        result = await session.execute(
            select(User).where(User.wallet_address == body.wallet_address).with_for_update()
        )
        user = result.scalar_one_or_none()

        if not user:
            audit_log = AuditLog(
                event_type="deposit_user_not_found",
                ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "wallet": body.wallet_address,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False, error_message="User not found"
            )
            session.add(audit_log)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please register first."
            )

        # Один депозит на пользователя
        if user.deposit_amount > Decimal("0"):
            audit_log = AuditLog(
                event_type="deposit_already_exists",
                user_id=user.id,
                ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "wallet": body.wallet_address,
                    "existing_deposit": str(user.deposit_amount),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False, error_message="User already has a deposit"
            )
            session.add(audit_log)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active deposit. Only one deposit per account is allowed."
            )

        # Верификация в блокчейне
        from blockchain.solana_client import solana_client

        tx_verification = await solana_client.verify_usdc_transaction(
            tx_hash=body.tx_hash,
            expected_recipient=settings.MAIN_WALLET_TOKEN,
            expected_amount=body.amount,
            tolerance=constants.AMOUNT_TOLERANCE
        )

        if not tx_verification["valid"]:
            logger.warning(
                f"❌ Transaction verification failed: {body.tx_hash} - {tx_verification['error']}"
            )
            audit_log = AuditLog(
                event_type="deposit_verification_failed",
                user_id=user.id, ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "error": tx_verification['error'],
                    "amount": str(body.amount),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False, error_message=tx_verification['error']
            )
            session.add(audit_log)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transaction verification failed: {tx_verification['error']}"
            )

        logger.info(
            f"✅ Blockchain verification passed: {body.tx_hash} - "
            f"{tx_verification['amount']} USDC from {tx_verification['sender']}"
        )

        # CRIT-1 FIX: Verify that the transaction sender matches the registering wallet.
        # Without this check, anyone who sees a tx_hash on the Solana explorer can call
        # /verify with their own wallet_address and claim someone else's deposit.
        # Also reject if sender is absent — a missing sender field means the RPC
        # response is incomplete and ownership cannot be proven.
        tx_sender = tx_verification.get("sender")
        if not tx_sender or tx_sender != user.wallet_address:
            logger.warning(
                f"❌ Sender mismatch: tx sender={tx_verification['sender']}, "
                f"claimed wallet={body.wallet_address}"
            )
            audit_log = AuditLog(
                event_type="deposit_sender_mismatch",
                user_id=user.id, ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "tx_sender": tx_sender or "missing",
                    "claimed_wallet": body.wallet_address,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False, error_message="Transaction sender does not match wallet address"
            )
            session.add(audit_log)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction sender does not match your wallet address."
            )

        # Определяем уровень депозита
        deposit_level = None
        for level, amount in constants.TIER_AMOUNTS.items():
            if abs(body.amount - amount) <= constants.AMOUNT_TOLERANCE:
                deposit_level = level
                break

        if not deposit_level:
            audit_log = AuditLog(
                event_type="deposit_invalid_amount",
                user_id=user.id, ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "amount": str(body.amount),
                    "valid_amounts": [str(v) for v in constants.TIER_AMOUNTS.values()],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False,
                error_message=f"Invalid deposit amount: {body.amount}"
            )
            session.add(audit_log)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid deposit amount. Must be one of: {list(constants.TIER_AMOUNTS.values())}"
            )

        # Обновляем пользователя — депозит один и навсегда
        user.deposit_amount = body.amount
        user.deposit_level = deposit_level
        user.deposit_tx_hash = body.tx_hash
        user.first_deposit_at = datetime.now(timezone.utc)

        # Создаём транзакцию депозита
        deposit_tx = Transaction(
            user_id=user.id,
            type=constants.TX_TYPE_DEPOSIT,
            amount=body.amount,
            level=deposit_level,
            tx_hash=body.tx_hash,
            status=constants.STATUS_COMPLETED,
            completed_at=datetime.now(timezone.utc)
        )
        session.add(deposit_tx)

        # Атомарно начисляем реферальные доходы
        referral_earnings = await process_referral_earnings(user, body.amount, session)

        # Помечаем транзакцию как обработанную (идемпотентность)
        processed_tx = ProcessedTransaction(
            tx_hash=body.tx_hash,
            user_id=user.id,
            transaction_type=constants.TX_TYPE_DEPOSIT
        )
        session.add(processed_tx)

        # Коммит с защитой от race condition
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning(f"Concurrent transaction processing detected: {body.tx_hash}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transaction already processed by another request"
            )

        # Инвалидируем кэш статистики пользователя
        await cache_manager.delete(f"user_stats:{body.wallet_address}")

        # ── 60/40 SPLIT: transfer cold reserve to cold wallet ──────────────
        # Non-fatal: split failure does NOT roll back the deposit.
        # Failure is written to audit_logs (event_type="deposit_split_failed")
        # and will be retried by the retry_failed_splits Celery task.
        split_result = await split_deposit(
            deposit_amount=body.amount,
            user_id=user.id,
            tx_hash=body.tx_hash,
            session=session,
        )
        if not split_result["cold_success"]:
            logger.warning(
                f"⚠️ Cold split failed for {body.tx_hash}: "
                f"{split_result['cold_error']} — will retry automatically"
            )
        if not split_result["gas_success"]:
            logger.warning(
                f"⚠️ Gas swap failed for {body.tx_hash}: "
                f"{split_result['gas_error']} — will retry automatically"
            )

        # Audit log успеха
        audit_log = AuditLog(
            event_type="deposit_success",
            user_id=user.id, ip_address=ip_address, user_agent=user_agent,
            details=json.dumps({
                "tx_hash": body.tx_hash,
                "amount": str(body.amount),
                "level": deposit_level,
                "referral_earnings": referral_earnings,
                "cold_tx": split_result.get("cold_tx"),
                "gas_swap_tx": split_result.get("gas_swap_tx"),
                "cold_amount": str(split_result.get("cold_amount", 0)),
                "gas_amount": str(split_result.get("gas_amount", 0)),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }),
            success=True
        )
        session.add(audit_log)
        await session.commit()

        financial_logger.info(
            f"DEPOSIT | User: {user.id} | Amount: {str(body.amount)} USDC | "
            f"Level: {deposit_level} | IP: {ip_address} | TxHash: {body.tx_hash} | "
            f"ColdTx: {split_result.get('cold_tx', 'N/A')} | "
            f"GasTx: {split_result.get('gas_swap_tx', 'N/A')}"
        )

        logger.info(f"✅ Deposit processed: {body.wallet_address} - {body.amount} USDC [{deposit_level}]")

        return DepositVerifyResponse(
            success=True,
            verified=True,
            deposit_level=deposit_level,
            amount=body.amount,
            referral_earnings=referral_earnings if referral_earnings else None,
            message=f"Deposit of {body.amount} USDC confirmed. Level: {deposit_level}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deposit verification error: {e}", exc_info=True)
        await session.rollback()

        try:
            audit_log = AuditLog(
                event_type="deposit_error",
                ip_address=ip_address, user_agent=user_agent,
                details=json.dumps({
                    "tx_hash": body.tx_hash,
                    "wallet": body.wallet_address,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }),
                success=False, error_message=str(e)
            )
            session.add(audit_log)
            await session.commit()
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deposit verification failed"
        )


# ==================== ADMIN: PENDING DEPOSITS ====================

@router.get("/pending", response_model=DepositListResponse)
@limiter.limit("30/hour")
async def get_pending_deposits(
    request: Request,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Админ-эндпоинт — список pending депозитов.

    CRIT-3: Ключ только в заголовке X-Admin-Key, никогда в URL.
            Использует settings.ADMIN_API_KEY + hmac.compare_digest.
    N+1 FIX: Один JOIN-запрос вместо N отдельных SELECT на каждую транзакцию.
    LIMIT:   Не более 200 строк — защита от полного скана таблицы.
    """
    _require_admin(x_admin_key)

    try:
        # Один JOIN — без N+1
        result = await session.execute(
            select(Transaction, User)
            .join(User, User.id == Transaction.user_id)
            .where(
                Transaction.type == constants.TX_TYPE_DEPOSIT,
                Transaction.status == constants.STATUS_PENDING
            )
            .order_by(Transaction.created_at.desc())
            .limit(200)
        )

        rows = result.all()

        deposits = [
            PendingDeposit(
                id=tx.id,
                wallet_address=user.wallet_address,
                amount=tx.amount,
                tx_hash=tx.tx_hash or "",
                status=tx.status,
                created_at=tx.created_at
            )
            for tx, user in rows
        ]

        return DepositListResponse(deposits=deposits, total_count=len(deposits))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pending deposits error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pending deposits"
        )
