"""
✅ FIXED v2.3: Security Module

CRIT-4 FIX: get_client_ip now uses X-Real-IP (set by nginx from $remote_addr).
  X-Forwarded-For[0] is client-controlled and trivially spoofed — removed.
  X-Real-IP is set server-side by nginx and cannot be forged by the client.

All other code unchanged from v2.1 (Argon2, JWT, etc.).
"""

import secrets
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from config.settings import settings

logger = logging.getLogger(__name__)


class PasswordManager:
    """Secure password hashing with Argon2"""

    def __init__(self):
        self.argon2 = PasswordHasher(
            time_cost=2, memory_cost=65536, parallelism=4,
            hash_len=32, salt_len=16
        )
        self.bcrypt = CryptContext(
            schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12
        )

    def hash_password(self, password: str) -> str:
        try:
            return self.argon2.hash(password)
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            raise ValueError("Failed to hash password")

    def verify_password(self, password: str, hashed: str) -> bool:
        try:
            self.argon2.verify(hashed, password)
            if self.argon2.check_needs_rehash(hashed):
                logger.info("Password needs rehash")
            return True
        except VerifyMismatchError:
            return False
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False

    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        if len(password) < settings.MIN_PASSWORD_LENGTH:
            return False, f"Min {settings.MIN_PASSWORD_LENGTH} characters"
        if settings.REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
            return False, "Must contain uppercase"
        if settings.REQUIRE_LOWERCASE and not any(c.islower() for c in password):
            return False, "Must contain lowercase"
        if settings.REQUIRE_NUMBERS and not any(c.isdigit() for c in password):
            return False, "Must contain a digit"
        if settings.REQUIRE_SPECIAL_CHARS:
            if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
                return False, "Must contain a special character"
        return True, ""


class TokenManager:
    """JWT token creation and validation"""

    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_expire = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=self.access_expire))
        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=self.refresh_expire))
        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("type") != token_type:
                return None
            return payload
        except (jwt.ExpiredSignatureError, JWTError):
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None

    def get_user_id_from_token(self, token: str) -> Optional[int]:
        payload = self.verify_token(token)
        if payload:
            try:
                return int(payload.get("sub"))
            except (TypeError, ValueError):
                return None
        return None


class SecurityUtils:
    """Various security utilities"""

    @staticmethod
    def generate_referral_code(length: int = 8) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def generate_api_key() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def verify_api_key(api_key: str, hashed_key: str) -> bool:
        return hashlib.sha256(api_key.encode()).hexdigest() == hashed_key

    @staticmethod
    def is_valid_wallet_address(address: str) -> bool:
        if not address or not (32 <= len(address) <= 44):
            return False
        base58_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return all(c in base58_chars for c in address)

    @staticmethod
    def sanitize_input(text: str, max_length: int = 255) -> str:
        if not text:
            return ""
        return text.replace('\x00', '').strip()[:max_length]


class RateLimitUtils:
    """Rate limiting utilities"""

    @staticmethod
    def get_client_ip(request) -> str:
        """
        CRIT-4 FIX: Use X-Real-IP only — set by nginx from $remote_addr.

        nginx MUST be configured with:
          proxy_set_header X-Real-IP $remote_addr;

        DO NOT use X-Forwarded-For[0]:
          - It's the first IP in a client-supplied list
          - Any client can send: X-Forwarded-For: 1.2.3.4, real.ip
          - This completely bypasses rate limiting

        X-Real-IP is set by the server (nginx), not the client.
        A client cannot override it because nginx overwrites it unconditionally.
        """
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Direct connection — only in dev, nginx is not in front
        return request.client.host if request.client else "0.0.0.0"

    @staticmethod
    def get_user_agent(request) -> str:
        return request.headers.get("User-Agent", "unknown")


# ==================== SINGLETONS ====================

password_manager = PasswordManager()
token_manager = TokenManager()
security_utils = SecurityUtils()
rate_limit_utils = RateLimitUtils()
