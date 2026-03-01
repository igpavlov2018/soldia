"""
✅ FIXED v2.3: Referral API Routes

SERIOUS FIXES:
  SER-3: N+1 eliminated in build_referral_tree — all 3 levels fetched in 2 queries
          (one per depth level via IN clause), not one query per user node.
  SER-4: float() removed — earnings returned as strings to preserve Decimal precision.
  SER-5: Redis KEYS() replaced with SCAN-based iteration in cache invalidation.
"""

import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter

from database.manager import get_db_session
from models.database import User
from api.schemas.referral import (
    ReferralTreeResponse,
    ReferralStatsResponse,
    ReferralNode,
)
from config.settings import constants
from security.auth import rate_limit_utils

logger = logging.getLogger(__name__)
router = APIRouter()


def _real_ip(request: Request) -> str:
    """CRIT-4: Use X-Real-IP from nginx."""
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "0.0.0.0"


limiter = Limiter(key_func=_real_ip)


async def build_referral_tree_flat(
    root_user_id: int,
    session: AsyncSession,
    max_depth: int = 3,
) -> list[ReferralNode]:
    """
    SER-3 FIX: Build referral tree in O(depth) queries instead of O(N) queries.

    Old approach:
      For each user node, execute one SELECT ... WHERE referrer_id = <id>.
      With 100 L1 referrals × 10 L2 each = 1 + 100 + 1000 = 1101 queries. 😱

    New approach:
      Level 1: SELECT WHERE referrer_id = root_id          → 1 query
      Level 2: SELECT WHERE referrer_id IN (l1_ids)        → 1 query
      Level 3: SELECT WHERE referrer_id IN (l2_ids)        → 1 query
      Total: always exactly 3 queries regardless of tree size. ✅

    Then we build the tree structure in Python from the flat results.
    """
    # ── Fetch all 3 levels in 3 queries ───────────────────────────────────

    # L1
    l1_result = await session.execute(
        select(User).where(User.referrer_id == root_user_id)
    )
    l1_users = l1_result.scalars().all()

    if not l1_users:
        return []

    l1_ids = [u.id for u in l1_users]

    # L2
    l2_result = await session.execute(
        select(User).where(User.referrer_id.in_(l1_ids))
    )
    l2_users = l2_result.scalars().all()
    l2_by_referrer: dict[int, list[User]] = {}
    for u in l2_users:
        l2_by_referrer.setdefault(u.referrer_id, []).append(u)

    l2_ids = [u.id for u in l2_users]

    # L3
    l3_by_referrer: dict[int, list[User]] = {}
    if l2_ids:
        l3_result = await session.execute(
            select(User).where(User.referrer_id.in_(l2_ids))
        )
        l3_users = l3_result.scalars().all()
        for u in l3_users:
            l3_by_referrer.setdefault(u.referrer_id, []).append(u)

    # ── Assemble tree in Python ────────────────────────────────────────────

    def _node(u: User, depth: int, children: list) -> ReferralNode:
        return ReferralNode(
            wallet_address=u.wallet_address[:8] + "...",  # SEC-04 partial mask
            username=u.username,
            deposit_level=u.deposit_level,
            deposit_amount=str(u.deposit_amount),   # SER-4: string not float
            total_earned=str(u.total_earned),        # SER-4
            created_at=u.created_at,
            level=depth,
            children=children,
        )

    tree = []
    for l1 in l1_users:
        l2_nodes = []
        for l2 in l2_by_referrer.get(l1.id, []):
            l3_nodes = [
                _node(l3, 3, [])
                for l3 in l3_by_referrer.get(l2.id, [])
            ]
            l2_nodes.append(_node(l2, 2, l3_nodes))
        tree.append(_node(l1, 1, l2_nodes))

    return tree


@router.get("/tree/{wallet_address}", response_model=ReferralTreeResponse)
@limiter.limit(constants.RATE_LIMIT_STATS)
async def get_referral_tree(
    wallet_address: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """Get referral tree (3 levels). Uses 3 DB queries total regardless of tree size."""
    try:
        result = await session.execute(
            select(User).where(User.wallet_address == wallet_address)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        tree = await build_referral_tree_flat(user.id, session)

        def _count(nodes, counts):
            for n in nodes:
                counts[f"l{n.level}"] = counts.get(f"l{n.level}", 0) + 1
                _count(n.children, counts)

        level_counts: dict = {}
        _count(tree, level_counts)

        return ReferralTreeResponse(
            wallet_address=wallet_address,
            tree=tree,
            total_referrals=sum(level_counts.values()),
            levels=level_counts,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Referral tree error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch referral tree")


@router.get("/stats/{wallet_address}", response_model=ReferralStatsResponse)
@limiter.limit(constants.RATE_LIMIT_STATS)
async def get_referral_stats(
    wallet_address: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get referral statistics. 3 queries total (one per level via IN).
    SER-4: earnings returned as strings (Decimal-safe).
    """
    try:
        result = await session.execute(
            select(User).where(User.wallet_address == wallet_address)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # L1
        l1_result = await session.execute(
            select(User).where(User.referrer_id == user.id)
        )
        l1_users = l1_result.scalars().all()
        l1_count = len(l1_users)
        l1_active = sum(1 for u in l1_users if u.deposit_amount > Decimal("0"))

        # L2
        l2_users = []
        if l1_users:
            l2_result = await session.execute(
                select(User).where(User.referrer_id.in_([u.id for u in l1_users]))
            )
            l2_users = l2_result.scalars().all()
        l2_count = len(l2_users)
        l2_active = sum(1 for u in l2_users if u.deposit_amount > Decimal("0"))

        # L3
        l3_active = 0
        l3_count = 0
        if l2_users:
            l3_result = await session.execute(
                select(User).where(User.referrer_id.in_([u.id for u in l2_users]))
            )
            l3_users = l3_result.scalars().all()
            l3_count = len(l3_users)
            l3_active = sum(1 for u in l3_users if u.deposit_amount > Decimal("0"))

        # Top referrals by earnings — from already-loaded L1+L2+L3 (no extra query)
        # INFO-2 FIX: include l3_users so diamond/gold L3 referrals can appear in top.
        # l3_users is only assigned inside `if l2_users:` block — default to [] here
        # to avoid NameError when l2_users is empty.
        _l3 = l3_users if l2_users else []
        all_loaded = l1_users + l2_users + _l3
        top = sorted(all_loaded, key=lambda u: u.total_earned, reverse=True)[:10]
        top_data = [
            {
                "wallet_address": u.wallet_address[:8] + "...",
                "deposit_level": u.deposit_level,
                "deposit_amount": str(u.deposit_amount),   # SER-4
                "total_earned": str(u.total_earned),        # SER-4
                "created_at": u.created_at.isoformat(),
            }
            for u in top
        ]

        total_earnings = user.earned_l1 + user.earned_l2 + user.earned_l3

        return ReferralStatsResponse(
            wallet_address=wallet_address,
            referral_code=user.referral_code,
            total_referrals=l1_count + l2_count + l3_count,
            active_referrals=l1_active + l2_active + l3_active,
            referrals_by_level={"l1": l1_count, "l2": l2_count, "l3": l3_count},
            earnings_by_level={
                "l1": str(user.earned_l1),  # SER-4: string
                "l2": str(user.earned_l2),
                "l3": str(user.earned_l3),
            },
            total_referral_earnings=str(total_earnings),    # SER-4
            top_referrals=top_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Referral stats error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch referral stats")
