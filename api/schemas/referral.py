"""
Referral API Schemas
"""

from decimal import Decimal
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class ReferralNode(BaseModel):
    """Single node in referral tree"""
    wallet_address: str
    username: Optional[str]
    deposit_level: Optional[str]
    deposit_amount: str  # BUG-1 FIX: route passes str(Decimal) — declare as str to match exactly
    total_earned: str    # BUG-1 FIX: same — avoids silent Pydantic coercion that could break in future
    created_at: datetime
    children: List['ReferralNode'] = []
    level: int


class ReferralTreeResponse(BaseModel):
    """Referral tree structure"""
    wallet_address: str
    tree: List[ReferralNode]
    total_referrals: int
    levels: dict  # {"l1": count, "l2": count, "l3": count}


class ReferralStatsResponse(BaseModel):
    """Referral statistics"""
    wallet_address: str
    referral_code: str
    total_referrals: int
    active_referrals: int
    referrals_by_level: dict
    earnings_by_level: dict
    total_referral_earnings: str  # возвращается как строка для сохранения точности Decimal
    top_referrals: List[dict]


# Enable forward references
ReferralNode.model_rebuild()
