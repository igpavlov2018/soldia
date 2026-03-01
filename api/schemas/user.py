"""
User API Schemas
"""

from decimal import Decimal
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    """Request to register new user"""
    wallet_address: str = Field(..., min_length=32, max_length=64)
    referral_code: Optional[str] = Field(None, max_length=16)
    telegram_id: Optional[str] = Field(None, max_length=64)
    username: Optional[str] = Field(None, max_length=64)


class UserRegisterResponse(BaseModel):
    """Response after user registration"""
    success: bool
    user_id: int
    wallet_address: str
    referral_code: str
    message: str


class UserStatsResponse(BaseModel):
    """User statistics"""
    wallet_address: str
    deposit_level: Optional[str]
    deposit_amount: Decimal
    total_earned: Decimal
    total_withdrawn: Decimal
    earned_l1: Decimal
    earned_l2: Decimal
    earned_l3: Decimal
    withdrawal_threshold_met: bool
    referral_code: str
    referral_count_l1: int
    referral_count_l2: int
    referral_count_l3: int
    created_at: datetime
    first_deposit_at: Optional[datetime]


class TransactionHistoryItem(BaseModel):
    """Single transaction in history"""
    id: int
    type: str
    amount: Decimal
    status: str
    tx_hash: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class UserHistoryResponse(BaseModel):
    """User transaction history"""
    wallet_address: str
    transactions: List[TransactionHistoryItem]
    total_count: int
