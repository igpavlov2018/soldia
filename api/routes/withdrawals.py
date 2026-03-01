"""
✅ FIXED v2.5: Withdrawal API Routes

ИСПРАВЛЕНИЯ v2.5:
  OBS-1: Platform balance check (Solana RPC) перенесён ДО SELECT FOR UPDATE.
         Ранее RPC-вызов выполнялся внутри validate_withdrawal() пока удерживался
         row lock — 2-10 сек блокировали все параллельные запросы пользователя.

Без изменений от v2.3/v2.4: CRIT-1..4, SER-1..2, idempotency, rollback.
"""

import logging
import json
import hmac
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from slowapi import Limiter
from pydantic import BaseModel

from database.manager import get_db_session
from models.database import User, Withdrawal, AuditLog
from config.settings import constants, settings

logger = logging.getLogger(__name__)
financial_logger = logging.getLogger('financial')
router = APIRouter()


# ==================== RATE LIMIT KEY: trusted IP from nginx ====================

def _real_ip(request: Request) -> str:
    """
    CRIT-4 FIX: Use X-Real-IP (set by nginx from $remote_addr — cannot be spoofed).
    NEVER use X-Forwarded-For[0] — that's the client-supplied value.
    nginx config must include: proxy_set_header X-Real-IP $remote_addr;
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    # Fallback for dev/direct connections only
    return request.client.host if request.client else "0.0.0.0"


limiter = Limiter(key_func=_real_ip)


# ==================== SCHEMAS ====================

class WithdrawRequest(BaseModel):
    wallet_address: str
    amount: Decimal
    signature: str
    idempotency_key: str  # SER-1: client-supplied unique key per attempt


class WithdrawResponse(BaseModel):
    success: bool
    tx_hash: str
    amount: Decimal
    message: str
    idempotent: bool = False


# ==================== ADMIN KEY CHECK ====================

def _require_admin(x_admin_key: Optional[str]) -> None:
    """
    CRIT-3 FIX: Admin key in request header X-Admin-Key, never in URL.

    URL query params are logged by: nginx access log, AWS CloudTrail,
    browser history, CDN logs, Sentry breadcrumbs, etc.
    Headers are not logged by default in any of these.

    Uses hmac.compare_digest for constant-time comparison (timing-attack safe).
    """
    expected = settings.ADMIN_API_KEY
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )


# ==================== VALIDATION ====================

async def validate_withdrawal(
    user: User,
    amount: Decimal,
    session: AsyncSession,
) -> tuple[bool, str]:
    """
    Validate withdrawal request.
    User row is already locked via SELECT FOR UPDATE before this is called.
    All comparisons use Decimal — no float() anywhere.

    OBS-1 FIX: Platform balance check (Solana RPC call) has been REMOVED
    from here and moved to BEFORE the SELECT FOR UPDATE in withdraw_funds().
    Calling the RPC while holding a row lock blocked all concurrent requests
    from the same user for the duration of the network round-trip (2-10 sec).
    """
    if not user.is_active:
        return False, "Account inactive."

    if user.deposit_amount <= Decimal("0"):
        return False, "No deposit on record."

    # 2x rule — only before first withdrawal
    if user.last_withdrawal_at is None:
        threshold = user.deposit_amount * Decimal("2")
        if user.total_earned < threshold:
            remaining = threshold - user.total_earned
            return False, (
                f"Withdrawal locked. Need {threshold} USDC (2x deposit) total earned. "
                f"Current: {user.total_earned}. Remaining: {remaining} USDC."
            )

    if amount <= Decimal("0"):
        return False, "Amount must be positive."

    available = user.total_earned - user.total_withdrawn
    if amount > available:
        return False, f"Insufficient balance. Available: {available} USDC."

    return True, ""


# ==================== WITHDRAW ====================

@router.post("/withdraw", response_model=WithdrawResponse)
@limiter.limit("20/hour")
async def withdraw_funds(
    body: WithdrawRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> WithdrawResponse:
    """
    Process withdrawal with all critical fixes.

    Flow:
      1. Idempotency check — duplicate key returns existing result without re-processing
      2. Verify Ed25519 wallet signature
      3. SELECT user FOR UPDATE (CRIT-1) — row lock prevents concurrent double-spend
      4. Validate (2x only on first withdrawal)
      5. Capture prev_last_withdrawal_at before update (CRIT-2)
      6. Reserve funds in DB (status=pending) and commit
      7. Send USDC on-chain
      8. Success: mark completed, commit
      9. Failure: rollback DB reservation using captured prev value (CRIT-2)
    """
    ip = _real_ip(request)
    ua = request.headers.get("User-Agent", "unknown")

    try:
        # ── 1. IDEMPOTENCY ─────────────────────────────────────────────────
        existing = await session.execute(
            select(Withdrawal).where(
                Withdrawal.idempotency_key == body.idempotency_key
            )
        )
        existing_wd = existing.scalar_one_or_none()
        if existing_wd:
            if existing_wd.status == constants.STATUS_COMPLETED:
                logger.info(f"Idempotent return for key={body.idempotency_key}")
                return WithdrawResponse(
                    success=True,
                    tx_hash=existing_wd.tx_hash or "",
                    amount=existing_wd.amount,
                    message="Already processed.",
                    idempotent=True,
                )
            elif existing_wd.status == constants.STATUS_FAILED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Previous attempt failed. Use a new idempotency_key."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Withdrawal still processing."
                )

        # ── 2. VERIFY SIGNATURE ────────────────────────────────────────────
        message = f"Withdraw {body.amount:.2f} USDC to {body.wallet_address}"
        from security.web3_auth import verify_solana_signature
        if not await verify_solana_signature(message, body.signature, body.wallet_address):
            _log(session, "withdrawal_bad_signature", None, ip, ua,
                 {"wallet": body.wallet_address}, False, "Invalid signature")
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid wallet signature.",
            )

        # ── 2b. PLATFORM BALANCE CHECK (before lock) ───────────────────────
        # OBS-1 FIX: Check platform USDC balance BEFORE acquiring the row lock.
        # Previously this RPC call happened inside validate_withdrawal() which
        # runs while SELECT FOR UPDATE holds the user row lock.
        # A 2-10 second Solana RPC round-trip while holding the lock blocks ALL
        # concurrent requests from this user (and any other user sharing the
        # same PostgreSQL lock wait queue).
        # Moving it here — before the lock — eliminates that problem entirely.
        from blockchain.solana_client import solana_client as _sc
        _platform_balance = Decimal(str(await _sc.get_usdc_balance(settings.MAIN_WALLET)))
        if _platform_balance < body.amount:
            logger.warning(f"Platform balance {_platform_balance} < requested {body.amount}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Platform balance insufficient. Try later.",
            )

        # ── 3. LOCK ROW: SELECT FOR UPDATE ─────────────────────────────────
        # CRIT-1: Row lock ensures only one concurrent request can proceed.
        # The second concurrent request blocks here until the first commits,
        # then sees the updated total_withdrawn and fails balance check.
        result = await session.execute(
            select(User)
            .where(User.wallet_address == body.wallet_address)
            .with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        # ── 4. VALIDATE ────────────────────────────────────────────────────
        ok, err = await validate_withdrawal(user, body.amount, session)
        if not ok:
            _log(session, "withdrawal_validation_failed", user.id, ip, ua,
                 {"error": err, "amount": str(body.amount)}, False, err)
            await session.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

        # ── 5. CAPTURE prev_last_withdrawal_at BEFORE any UPDATE ───────────
        # CRIT-2 FIX: After the UPDATE below, the ORM object `user` in memory
        # will reflect the new value if SQLAlchemy refreshes it.
        # We capture the ORIGINAL value here in a plain Python variable so the
        # rollback path can restore it exactly, regardless of ORM state.
        prev_last_withdrawal_at = user.last_withdrawal_at

        # ── 6. RESERVE FUNDS IN DB ─────────────────────────────────────────
        now = datetime.now(timezone.utc)
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                total_withdrawn=User.total_withdrawn + body.amount,
                last_withdrawal_at=now,
            )
        )
        wd = Withdrawal(
            user_id=user.id,
            amount=body.amount,
            wallet_address=body.wallet_address,
            idempotency_key=body.idempotency_key,
            status="processing",  # RACE FIX: set 'processing' immediately, never expose 'pending'
        )
        session.add(wd)
        await session.flush()   # assign wd.id
        # RACE FIX: commit with status='processing' in a single step.
        # Previously: commit(PENDING) then commit(processing) — between those two
        # commits the Celery task could see status=PENDING and also call send_usdc,
        # resulting in a double USDC transfer.
        # Fix: write status='processing' directly on INSERT so the record is never
        # visible to Celery as PENDING. One commit instead of two.
        await session.commit()  # lock released here — reservation is durable
        _reservation_committed = True

        logger.info(f"Reserved {body.amount} USDC for user {user.id} (wd #{wd.id})")

        # ── 7. SEND ON-CHAIN ───────────────────────────────────────────────
        from blockchain.solana_client import solana_client
        tx_sig = await solana_client.send_usdc(
            to_wallet=body.wallet_address,
            amount=body.amount,
        )

        if not tx_sig:
            # ── 9. ROLLBACK RESERVATION ────────────────────────────────────
            # CRIT-2 FIX: Use prev_last_withdrawal_at (local var) not user.last_withdrawal_at
            logger.error(f"Blockchain failed for wd #{wd.id} — rolling back")
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    total_withdrawn=User.total_withdrawn - body.amount,
                    last_withdrawal_at=prev_last_withdrawal_at,  # ← correct original value
                )
            )
            wd.status = constants.STATUS_FAILED
            wd.error_message = "Blockchain returned no signature"
            _log(session, "withdrawal_blockchain_failed", user.id, ip, ua,
                 {"amount": str(body.amount)}, False, "Blockchain failed")
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Blockchain failed. Funds released — try again."
            )

        # ── 8. SUCCESS ─────────────────────────────────────────────────────
        wd.status = constants.STATUS_COMPLETED
        wd.tx_hash = tx_sig
        wd.completed_at = now
        _log(session, "withdrawal_success", user.id, ip, ua,
             {"amount": str(body.amount), "tx_hash": tx_sig}, True)
        await session.commit()

        financial_logger.info(
            f"WITHDRAWAL | user={user.id} | amount={body.amount} | tx={tx_sig} | ip={ip}"
        )

        return WithdrawResponse(
            success=True,
            tx_hash=tx_sig,
            amount=body.amount,
            message=f"Withdrawal of {body.amount} USDC complete.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Withdrawal error: {e}", exc_info=True)
        try:
            # Only roll back the reservation if the first commit (which increased
            # total_withdrawn) actually succeeded. If the exception happened before
            # that commit, total_withdrawn was never increased — decrementing it
            # would corrupt the balance.
            if locals().get('_reservation_committed') and 'wd' in locals() and 'user' in locals():
                # Rollback first: if the exception came from a failed commit(),
                # PostgreSQL puts the transaction in aborted state — any further
                # execute() without a prior rollback() will fail with
                # "current transaction is aborted".
                await session.rollback()
                await session.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(
                        total_withdrawn=User.total_withdrawn - body.amount,
                        last_withdrawal_at=prev_last_withdrawal_at,
                    )
                )
                wd.status = constants.STATUS_FAILED
                wd.error_message = str(e)
                await session.commit()
            else:
                await session.rollback()
        except Exception as rollback_err:
            logger.error(f"Failed to release funds after error: {rollback_err}", exc_info=True)
            await session.rollback()
        raise HTTPException(status_code=500, detail="Withdrawal failed — contact support.")


# ==================== STATS ====================

@router.get("/stats")
@limiter.limit(constants.RATE_LIMIT_STATS)
async def withdrawal_stats(
    wallet_address: str,
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    session: AsyncSession = Depends(get_db_session),
):
    """User withdrawal stats. Requires X-Signature (sign 'Stats {wallet_address}').
    MEDIUM-2 FIX: was public — anyone could read any user's balance and threshold.
    """
    from security.web3_auth import verify_solana_signature
    if not x_signature or not await verify_solana_signature(
        f"Stats {wallet_address}", x_signature, wallet_address
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Signature header required (sign 'Stats {wallet_address}')."
        )
    result = await session.execute(
        select(User).where(User.wallet_address == wallet_address)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    available = user.total_earned - user.total_withdrawn
    threshold = user.deposit_amount * Decimal("2")
    remaining = max(Decimal("0"), threshold - user.total_earned)

    return {
        "wallet": wallet_address,
        "deposit_amount": str(user.deposit_amount),
        "total_earned": str(user.total_earned),
        "total_withdrawn": str(user.total_withdrawn),
        "available": str(available),
        # WARN-1 FIX: withdrawal_unlocked is True when user CAN withdraw.
        # Correct condition: threshold has been met (first-time unlock) OR user
        # has already made at least one withdrawal (2x rule no longer applies).
        # Old: last_withdrawal_at is not None — was False even when threshold IS met
        # (user ready for first withdrawal) — frontend incorrectly blocked the UI.
        "withdrawal_unlocked": user.withdrawal_threshold_met or user.last_withdrawal_at is not None,
        "threshold": str(threshold),
        "threshold_met": user.withdrawal_threshold_met,
        "remaining_to_threshold": str(remaining),
        "last_withdrawal": user.last_withdrawal_at.isoformat() if user.last_withdrawal_at else None,
    }


# ==================== ADMIN: PENDING WITHDRAWALS ====================

@router.get("/pending")
@limiter.limit("30/hour")
async def pending_withdrawals(
    request: Request,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Admin endpoint — list pending withdrawals.
    CRIT-3: Key must be in X-Admin-Key header, never in URL.
    """
    _require_admin(x_admin_key)

    result = await session.execute(
        select(Withdrawal)
        .where(Withdrawal.status == constants.STATUS_PENDING)
        .order_by(Withdrawal.created_at.asc())
        .limit(200)
    )
    rows = result.scalars().all()

    return {
        "count": len(rows),
        "withdrawals": [
            {
                "id": w.id,
                "user_id": w.user_id,
                "amount": str(w.amount),   # SER-2: string not float
                "wallet": w.wallet_address,
                "status": w.status,
                "created_at": w.created_at.isoformat(),
            }
            for w in rows
        ],
    }


# ==================== HELPER ====================

def _log(session, event, user_id, ip, ua, details, success, error=None):
    session.add(AuditLog(
        event_type=event,
        user_id=user_id,
        ip_address=ip,
        user_agent=ua,
        details=json.dumps(details),
        success=success,
        error_message=error,
    ))