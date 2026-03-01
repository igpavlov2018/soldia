"""
tasks/split_retry.py — Retry failed cold wallet splits and gas swaps.

When split_deposit() fails on either step, it writes audit_log entries:
  event_type="deposit_split_cold_failed"  — cold wallet transfer failed
  event_type="deposit_split_gas_failed"   — USDC→SOL gas swap failed

This task runs every 30 minutes, finds those entries, and retries each
step independently. A partial failure (cold ok, gas failed) only retries
the gas swap — not the cold transfer again.

Runs via Celery Beat every 30 minutes.
"""

import logging
import ast
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from tasks.worker import celery
from database.manager import db_manager
from models.database import AuditLog
from sqlalchemy import select
from config.settings import settings

logger = logging.getLogger(__name__)

RETRY_WINDOW_DAYS = 7


@celery.task(name='tasks.split_retry.retry_failed_splits')
def retry_failed_splits():
    import asyncio

    async def _retry():
        logger.info("🔄 Checking for failed deposit splits to retry...")

        async with db_manager.session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=RETRY_WINDOW_DAYS)

            # Fetch all failed split logs within window
            result = await session.execute(
                select(AuditLog).where(
                    AuditLog.event_type.in_([
                        "deposit_split_cold_failed",
                        "deposit_split_gas_failed",
                    ]),
                    AuditLog.created_at >= cutoff,
                ).order_by(AuditLog.created_at.asc()).limit(40)
            )
            failed_logs = result.scalars().all()

            if not failed_logs:
                logger.info("No failed splits to retry")
                return 0

            # Build set of deposit_txs that already succeeded per step
            success_result = await session.execute(
                select(AuditLog).where(
                    AuditLog.event_type.in_([
                        "deposit_split_cold_success",
                        "deposit_split_gas_success",
                    ]),
                    AuditLog.created_at >= cutoff,
                )
            )
            succeeded_cold = set()
            succeeded_gas  = set()
            for log in success_result.scalars().all():
                try:
                    d = ast.literal_eval(log.details or "{}")
                    dep_tx = d.get("deposit_tx")
                    if dep_tx:
                        if log.event_type == "deposit_split_cold_success":
                            succeeded_cold.add(dep_tx)
                        else:
                            succeeded_gas.add(dep_tx)
                except Exception:
                    pass

            from blockchain.solana_client import solana_client
            from blockchain.jupiter_client import jupiter_client

            retried = 0

            for log in failed_logs:
                try:
                    details = ast.literal_eval(log.details or "{}")
                except Exception:
                    continue

                deposit_tx = details.get("deposit_tx")
                amount_str = details.get("amount")
                if not deposit_tx or not amount_str:
                    continue

                amount  = Decimal(amount_str)
                user_id = log.user_id or 0

                # ── Retry cold transfer ───────────────────────────────────────
                if (log.event_type == "deposit_split_cold_failed"
                        and deposit_tx not in succeeded_cold):

                    logger.info(f"Retrying cold split for {deposit_tx}: {amount} USDC")
                    try:
                        tx = await solana_client.send_usdc(
                            to_wallet=settings.COLD_WALLET,
                            amount=amount,
                        )
                        if tx:
                            session.add(AuditLog(
                                event_type="deposit_split_cold_success",
                                user_id=user_id,
                                details=str({
                                    "deposit_tx": deposit_tx,
                                    "cold_tx": tx,
                                    "cold_amount": str(amount),
                                    "retried": True,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }),
                                success=True,
                            ))
                            succeeded_cold.add(deposit_tx)
                            retried += 1
                            logger.info(f"✅ Cold retry succeeded: {tx}")
                        else:
                            logger.warning(f"Cold retry still failed for {deposit_tx}")
                    except Exception as e:
                        logger.error(f"Cold retry exception for {deposit_tx}: {e}")

                # ── Retry gas swap ────────────────────────────────────────────
                elif (log.event_type == "deposit_split_gas_failed"
                        and deposit_tx not in succeeded_gas):

                    logger.info(f"Retrying gas swap for {deposit_tx}: {amount} USDC→SOL")
                    try:
                        tx = await jupiter_client.swap_usdc_to_sol(amount)
                        if tx:
                            session.add(AuditLog(
                                event_type="deposit_split_gas_success",
                                user_id=user_id,
                                details=str({
                                    "deposit_tx":  deposit_tx,
                                    "gas_swap_tx": tx,
                                    "gas_amount":  str(amount),
                                    "retried":     True,
                                    "timestamp":   datetime.now(timezone.utc).isoformat(),
                                }),
                                success=True,
                            ))
                            succeeded_gas.add(deposit_tx)
                            retried += 1
                            logger.info(f"✅ Gas swap retry succeeded: {tx}")
                        else:
                            logger.warning(f"Gas swap retry still failed for {deposit_tx}")
                    except Exception as e:
                        logger.error(f"Gas swap retry exception for {deposit_tx}: {e}")

            try:
                await session.commit()
            except Exception as e:
                logger.warning(f"Retry commit failed (non-fatal): {e}")

            logger.info(f"Split retry complete: {retried} succeeded")
            return retried

    try:
        _loop = asyncio.get_event_loop()
        return _loop.run_until_complete(_retry())
    except Exception as e:
        logger.error(f"Error in retry_failed_splits: {e}", exc_info=True)
        return 0
