"""
API Routes
"""

from .users import router as users_router
from .deposits import router as deposits_router
from .withdrawals import router as withdrawals_router
from .referrals import router as referrals_router

__all__ = [
    "users_router",
    "deposits_router",
    "withdrawals_router",
    "referrals_router",
]
