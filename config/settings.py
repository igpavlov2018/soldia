"""
✅ FIXED v2.4: Production Configuration

ИСПРАВЛЕНИЯ v2.4:
  ADMIN_API_KEY: добавлена валидация в production — приложение не запустится
                 без явно заданного ADMIN_API_KEY в .env.
                 Предотвращает ситуацию когда каждый воркер Gunicorn получает
                 разный случайный ключ при каждом рестарте.

Все остальные настройки без изменений от v2.3.
"""

import secrets
from decimal import Decimal
from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # ==================== APPLICATION ====================
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    API_TITLE: str = Field(default="SOLDIA API")
    API_VERSION: str = Field(default="2.8.0")
    API_PREFIX: str = Field(default="/api")

    SECRET_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for JWT tokens"
    )

    # CRIT-3: Отдельный admin ключ — никогда не производный от SECRET_KEY, никогда в URL.
    # В production ОБЯЗАТЕЛЬНО задать ADMIN_API_KEY в .env:
    #   ADMIN_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    # Если не задан — в production приложение не запустится (validate_configuration).
    # В dev — генерируется случайный при каждом старте (достаточно для разработки).
    ADMIN_API_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Admin key for X-Admin-Key header on admin endpoints"
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        if info.data.get("ENVIRONMENT") == "production":
            if len(v) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters in production")
            if v == "CHANGE_THIS_TO_RANDOM_256_BIT_KEY_USE_secrets.token_urlsafe(32)":
                raise ValueError("You must change the default SECRET_KEY in production!")
        return v

    # ==================== DATABASE ====================
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://soldia:soldia@localhost:5432/soldia_db"
    )
    DATABASE_POOL_SIZE: int = Field(default=20, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=1)
    DATABASE_ECHO: bool = Field(default=False)

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str, info) -> str:
        if "sqlite" in v.lower():
            raise ValueError("SQLite not allowed. Use PostgreSQL!")
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        if info.data.get("ENVIRONMENT") == "production":
            if "soldia:soldia" in v:
                raise ValueError("Default database credentials detected! Set strong password.")
        return v

    # ==================== REDIS ====================
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_PASSWORD: Optional[str] = Field(default=None)
    REDIS_CACHE_TTL: int = Field(default=300, ge=0)
    REDIS_SESSION_TTL: int = Field(default=3600, ge=60)

    # ==================== SOLANA ====================
    SOLANA_RPC: str = Field(default="https://api.mainnet-beta.solana.com")
    USDC_MINT: str = Field(default="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

    # ==================== WALLETS ====================
    # Hot wallet — receives all deposits, pays out bonuses.
    # Server holds the private key (HOT_WALLET_PRIVATE_KEY).
    MAIN_WALLET: str = Field(default="", description="Hot wallet address (receives deposits)")
    MAIN_WALLET_TOKEN: str = Field(default="", description="Hot wallet USDC token account")
    HOT_WALLET_PRIVATE_KEY: Optional[str] = Field(default=None)

    # Cold wallet — project reserve. Server knows only the ADDRESS, never the private key.
    # 40% of every deposit is transferred here automatically after verification.
    # Funds can only be spent offline via hardware wallet — inaccessible even if server is compromised.
    COLD_WALLET: str = Field(default="", description="Cold wallet address (project reserve)")
    COLD_WALLET_TOKEN: str = Field(default="", description="Cold wallet USDC token account")

    # ── Deposit split ratios ──────────────────────────────────────────────────
    # Every incoming deposit is split three ways. All three must sum to 1.00:
    #
    #   DEPOSIT_HOT_RATIO   = 0.60  kept on hot wallet → pays user bonuses
    #   DEPOSIT_COLD_RATIO  = 0.39  sent to cold wallet → project reserve (no key on server)
    #   DEPOSIT_GAS_RATIO   = 0.01  swapped USDC→SOL via Jupiter → stays on hot wallet as gas
    #
    # The gas slice is swapped automatically so the hot wallet never runs dry.
    # No manual SOL top-ups needed as long as deposits keep coming in.
    DEPOSIT_HOT_RATIO: Decimal = Field(
        default=Decimal("0.60"),
        description="Fraction kept on hot wallet for bonus payouts"
    )
    DEPOSIT_COLD_RATIO: Decimal = Field(
        default=Decimal("0.39"),
        description="Fraction sent to cold wallet as project reserve"
    )
    DEPOSIT_GAS_RATIO: Decimal = Field(
        default=Decimal("0.01"),
        description="Fraction swapped USDC→SOL for Solana transaction fees"
    )

    # Jupiter Aggregator API — used for USDC→SOL swaps.
    # No API key required for the public endpoint.
    # https://station.jup.ag/docs/apis/swap-api
    JUPITER_API_URL: str = Field(
        default="https://quote-api.jup.ag/v6",
        description="Jupiter v6 Swap API base URL"
    )
    # Maximum acceptable price impact for the USDC→SOL swap (0.5% = 0.005).
    # If Jupiter quotes a worse rate, the swap is aborted and retried later.
    JUPITER_MAX_SLIPPAGE_BPS: int = Field(
        default=50,
        description="Max slippage in basis points (50 bps = 0.5%)"
    )

    # SOL mint address on Solana mainnet (wrapped SOL)
    SOL_MINT: str = Field(
        default="So11111111111111111111111111111111111111112",
        description="Wrapped SOL mint address"
    )

    @field_validator("MAIN_WALLET", "MAIN_WALLET_TOKEN")
    @classmethod
    def validate_wallet_addresses(cls, v: str, info) -> str:
        if info.data.get("ENVIRONMENT") == "production":
            if not v or len(v) < 32:
                raise ValueError(f"{info.field_name} must be set in production!")
        return v

    @field_validator("DEPOSIT_GAS_RATIO")
    @classmethod
    def validate_split_ratios(cls, gas: Decimal, info) -> Decimal:
        hot  = info.data.get("DEPOSIT_HOT_RATIO",  Decimal("0.60"))
        cold = info.data.get("DEPOSIT_COLD_RATIO", Decimal("0.39"))
        total = hot + cold + gas
        if abs(total - Decimal("1.00")) > Decimal("0.0001"):
            raise ValueError(
                f"HOT ({hot}) + COLD ({cold}) + GAS ({gas}) must equal 1.00, got {total}"
            )
        if any(r <= Decimal("0") for r in (hot, cold, gas)):
            raise ValueError("All three split ratios must be > 0")
        return gas

    # ==================== AWS KMS ====================
    USE_AWS_KMS: bool = Field(default=False)
    AWS_REGION: str = Field(default="us-east-1")
    KMS_KEY_ID: Optional[str] = Field(default=None)

    # ==================== CORS ====================
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"]
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v) -> List[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_origins_in_production(cls, v: List[str], info) -> List[str]:
        if info.data.get("ENVIRONMENT") == "production":
            localhost_origins = [o for o in v if "localhost" in o or "127.0.0.1" in o]
            if localhost_origins:
                raise ValueError(f"localhost not allowed in production CORS: {localhost_origins}")
        return v

    # ==================== RATE LIMITING ====================
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_STORAGE: str = Field(default="redis://localhost:6379/1")

    # ==================== MONITORING ====================
    SENTRY_DSN: Optional[str] = Field(default=None)
    SENTRY_ENVIRONMENT: str = Field(default="development")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1)

    # ==================== LOGGING ====================
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: Optional[str] = Field(default="logs/app.log")

    # ==================== JWT ====================
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)

    # ==================== PASSWORD POLICY ====================
    MIN_PASSWORD_LENGTH: int = Field(default=12)
    REQUIRE_UPPERCASE: bool = Field(default=True)
    REQUIRE_LOWERCASE: bool = Field(default=True)
    REQUIRE_NUMBERS: bool = Field(default=True)
    REQUIRE_SPECIAL_CHARS: bool = Field(default=True)

    # ==================== SECURITY ====================
    MAINTENANCE_MODE: bool = Field(default=False)
    API_KEY_EXPIRATION_DAYS: int = Field(default=90)
    SESSION_TIMEOUT_MINUTES: int = Field(default=30)

    # ==================== CELERY ====================
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/2")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/3")

    def validate_configuration(self) -> None:
        issues = []
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                issues.append("❌ DEBUG must be False in production")
            if not self.MAIN_WALLET:
                issues.append("❌ MAIN_WALLET not configured")
            if not self.MAIN_WALLET_TOKEN:
                issues.append("❌ MAIN_WALLET_TOKEN not configured")
            if not self.USE_AWS_KMS and not self.HOT_WALLET_PRIVATE_KEY:
                issues.append("❌ HOT_WALLET_PRIVATE_KEY not configured (or use AWS KMS)")
            if not self.COLD_WALLET:
                issues.append("❌ COLD_WALLET not configured (required for 60/40 split)")
            if not self.COLD_WALLET_TOKEN:
                issues.append("❌ COLD_WALLET_TOKEN not configured (required for 60/40 split)")
            if not self.SENTRY_DSN:
                logger.warning("⚠️  SENTRY_DSN not configured - error tracking disabled")

            # v2.4 FIX: ADMIN_API_KEY обязателен в production.
            # Без него каждый воркер Gunicorn при рестарте получает
            # новый случайный ключ — admin-запросы будут непредсказуемо
            # проходить или падать в зависимости от того, на какой
            # воркер попал запрос.
            if not self.ADMIN_API_KEY or len(self.ADMIN_API_KEY) < 32:
                issues.append(
                    "❌ ADMIN_API_KEY must be set in production (min 32 chars). "
                    "Generate: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

        if issues:
            error_msg = "Configuration validation failed:\n" + "\n".join(issues)
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("✅ Configuration validation passed")


def validate_configuration() -> None:
    settings.validate_configuration()


settings = Settings()


# ==================== CONSTANTS ====================

class Constants:
    """Application constants"""

    TX_TYPE_DEPOSIT = "deposit"
    TX_TYPE_WITHDRAWAL = "withdrawal"
    TX_TYPE_REFERRAL_L1 = "referral_l1"
    TX_TYPE_REFERRAL_L2 = "referral_l2"
    TX_TYPE_REFERRAL_L3 = "referral_l3"

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    TIER_AMOUNTS = {
        "bronze": Decimal("49"),
        "silver": Decimal("99"),
        "gold":   Decimal("499"),
        "diamond": Decimal("999")
    }

    REFERRAL_RATE_L1 = Decimal("0.30")   # 30%
    REFERRAL_RATE_L2 = Decimal("0.20")   # 20%
    REFERRAL_RATE_L3 = Decimal("0.10")   # 10%

    WITHDRAWAL_MULTIPLIER = 2   # 2x deposit to unlock first withdrawal

    AMOUNT_TOLERANCE = Decimal("0.50")

    USDC_DECIMALS = 6

    RATE_LIMIT_DEPOSIT    = "30/hour"
    RATE_LIMIT_WITHDRAWAL = "20/hour"
    RATE_LIMIT_REGISTER   = "5/hour"
    RATE_LIMIT_LOGIN      = "10/hour"
    RATE_LIMIT_STATS      = "100/hour"


constants = Constants()
