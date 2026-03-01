"""
services/deposit_split.py — Automatic three-way deposit split.

After a deposit is verified and committed to DB, every incoming USDC deposit
is automatically split:

  60% → stays on hot wallet    — funds user bonus payouts
  39% → sent to cold wallet    — project reserve (server never holds the key)
   1% → swapped USDC→SOL       — refills hot wallet gas for Solana tx fees

This makes the system self-funding: as long as deposits keep coming in,
the hot wallet never runs out of SOL for transaction fees.

Execution order (all non-fatal — deposit is already committed before this runs):
  Step 1: send 39% USDC to cold wallet
  Step 2: swap 1% USDC→SOL via Jupiter (fills gas tank)

Failure policy:
  - Both steps are non-fatal: deposit succeeds regardless of split outcome.
  - Failures are written to audit_logs and retried by retry_failed_splits task.
  - Each step is tracked independently so partial retries work.

Rounding:
  cold_amount = deposit × COLD_RATIO  (rounded down to 6dp)
  gas_amount  = deposit × GAS_RATIO   (rounded down to 6dp)
  hot_amount  = deposit - cold - gas  (exact subtraction, no rounding error)
"""

import logging
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from models.database import AuditLog

logger = logging.getLogger(__name__)


async def split_deposit(
    deposit_amount: Decimal,
    user_id: int,
    tx_hash: str,
    session: AsyncSession,
) -> dict:
    """
    Execute three-way split for a confirmed deposit.

    Called after session.commit() for the deposit — deposit record is
    already durable in DB before this function runs.

    Args:
        deposit_amount: Full USDC deposit amount (e.g. Decimal("99"))
        user_id:        For audit logging
        tx_hash:        Original deposit tx_hash for traceability
        session:        DB session for audit logs (caller commits after return)

    Returns dict with keys:
        cold_success, gas_success: bool
        cold_tx, gas_swap_tx:      str|None  — Solana tx signatures
        cold_amount, gas_amount, hot_amount: Decimal
        cold_error, gas_error:     str|None
    """
    # Skip if cold wallet not configured (dev/test environments)
    if not settings.COLD_WALLET_TOKEN:
        logger.info("COLD_WALLET_TOKEN not set — skipping deposit split (dev mode)")
        return dict(
            cold_success=True, gas_success=True,
            cold_tx=None, gas_swap_tx=None,
            cold_amount=Decimal("0"), gas_amount=Decimal("0"),
            hot_amount=deposit_amount,
            cold_error=None, gas_error=None,
        )

    # ── Calculate split amounts ───────────────────────────────────────────────
    # USDC on Solana has 6 decimal places.
    # Round DOWN so we never attempt to send more than available.
    # hot_amount = exact remainder (absorbs rounding dust — always >= 0).
    #
    # Example: deposit = 99.00 USDC, ratios 0.60 / 0.39 / 0.01
    #   cold =  99.00 × 0.39 = 38.610000 USDC  → cold wallet
    #   gas  =  99.00 × 0.01 =  0.990000 USDC  → swap to SOL
    #   hot  =  99.00 - 38.61 - 0.99 = 59.400000 USDC  → stays for payouts
    quant = Decimal("0.000001")
    cold_amount = (deposit_amount * settings.DEPOSIT_COLD_RATIO).quantize(quant, rounding=ROUND_DOWN)
    gas_amount  = (deposit_amount * settings.DEPOSIT_GAS_RATIO ).quantize(quant, rounding=ROUND_DOWN)
    hot_amount  = deposit_amount - cold_amount - gas_amount

    logger.info(
        f"Deposit split [{deposit_amount} USDC]: "
        f"hot={hot_amount} ({settings.DEPOSIT_HOT_RATIO*100:.0f}%) | "
        f"cold={cold_amount} ({settings.DEPOSIT_COLD_RATIO*100:.0f}%) | "
        f"gas={gas_amount} ({settings.DEPOSIT_GAS_RATIO*100:.0f}%)"
    )

    from blockchain.solana_client import solana_client
    from blockchain.jupiter_client import jupiter_client

    cold_tx     = None
    gas_swap_tx = None
    cold_success = False
    gas_success  = False
    cold_error   = None
    gas_error    = None

    # ── Step 1: cold wallet transfer ─────────────────────────────────────────
    try:
        cold_tx = await solana_client.send_usdc(
            to_wallet=settings.COLD_WALLET,
            amount=cold_amount,
        )
        if cold_tx:
            cold_success = True
            logger.info(f"✅ Cold split: {cold_amount} USDC → cold wallet (tx: {cold_tx})")
            session.add(AuditLog(
                event_type="deposit_split_cold_success",
                user_id=user_id,
                details=str({
                    "deposit_tx":     tx_hash,
                    "cold_tx":        cold_tx,
                    "deposit_amount": str(deposit_amount),
                    "cold_amount":    str(cold_amount),
                    "timestamp":      datetime.now(timezone.utc).isoformat(),
                }),
                success=True,
            ))
        else:
            cold_error = f"send_usdc() returned None for cold transfer of {cold_amount} USDC"
            logger.error(f"❌ Cold split failed: {cold_error}")
            await _log_failure(session, "deposit_split_cold_failed",
                               user_id, tx_hash, cold_amount, cold_error)
    except Exception as e:
        cold_error = f"Exception during cold split: {e}"
        logger.error(f"❌ {cold_error}", exc_info=True)
        await _log_failure(session, "deposit_split_cold_failed",
                           user_id, tx_hash, cold_amount, cold_error)

    # ── Step 2: USDC→SOL gas swap via Jupiter ─────────────────────────────────
    # Runs independently — cold failure does not block gas swap.
    try:
        gas_swap_tx = await jupiter_client.swap_usdc_to_sol(gas_amount)
        if gas_swap_tx:
            gas_success = True
            logger.info(f"✅ Gas swap: {gas_amount} USDC → SOL (tx: {gas_swap_tx})")
            session.add(AuditLog(
                event_type="deposit_split_gas_success",
                user_id=user_id,
                details=str({
                    "deposit_tx":     tx_hash,
                    "gas_swap_tx":    gas_swap_tx,
                    "deposit_amount": str(deposit_amount),
                    "gas_amount":     str(gas_amount),
                    "timestamp":      datetime.now(timezone.utc).isoformat(),
                }),
                success=True,
            ))
        else:
            gas_error = f"Jupiter swap returned None for {gas_amount} USDC→SOL"
            logger.error(f"❌ Gas swap failed: {gas_error}")
            await _log_failure(session, "deposit_split_gas_failed",
                               user_id, tx_hash, gas_amount, gas_error)
    except Exception as e:
        gas_error = f"Exception during gas swap: {e}"
        logger.error(f"❌ {gas_error}", exc_info=True)
        await _log_failure(session, "deposit_split_gas_failed",
                           user_id, tx_hash, gas_amount, gas_error)

    return dict(
        cold_success=cold_success, gas_success=gas_success,
        cold_tx=cold_tx, gas_swap_tx=gas_swap_tx,
        cold_amount=cold_amount, gas_amount=gas_amount,
        hot_amount=hot_amount,
        cold_error=cold_error, gas_error=gas_error,
    )


async def _log_failure(
    session: AsyncSession,
    event_type: str,
    user_id: int,
    deposit_tx: str,
    amount: Decimal,
    error: str,
) -> None:
    """Write audit log for a failed split step. Never raises."""
    try:
        session.add(AuditLog(
            event_type=event_type,
            user_id=user_id,
            details=str({
                "deposit_tx": deposit_tx,
                "amount":     str(amount),
                "error":      error,
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            }),
            success=False,
            error_message=error,
        ))
    except Exception as e:
        logger.error(f"Failed to write split failure audit log ({event_type}): {e}")
