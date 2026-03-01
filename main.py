"""
SOLDIA v2.8 - Main Application
Production-ready FastAPI application with PostgreSQL, Redis, and enhanced security

ИСПРАВЛЕНИЯ v2.7: BUG-1..4, OBS-1..9, SIG-1, N1..3, VER — все ошибки устранены
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Sentry for error tracking
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from config.settings import settings, validate_configuration
from database.manager import db_manager
from cache.manager import cache_manager
from security.auth import rate_limit_utils


# C1 FIX: Create logs directory BEFORE configuring logging.
# logging.basicConfig() with FileHandler immediately opens the file —
# if the directory doesn't exist yet the process crashes on first start.
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

# Configure logging (FileHandler is safe now — directory exists)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.LOG_FILE) if settings.LOG_FILE else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

# Financial operations logger (separate file)
financial_logger = logging.getLogger('financial')
financial_handler = logging.FileHandler(log_dir / 'financial.log')
financial_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
)
financial_logger.addHandler(financial_handler)
financial_logger.setLevel(logging.INFO)


# ==================== SENTRY INITIALIZATION ====================

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration()
        ],
        # Send PII data only in development
        send_default_pii=settings.DEBUG
    )
    logger.info("✅ Sentry initialized")


# ==================== APPLICATION LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # ==================== STARTUP ====================
    logger.info("=" * 60)
    logger.info("🚀 Starting SOLDIA v2.8...")
    logger.info("=" * 60)
    
    # Validate configuration
    try:
        validate_configuration()
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
    
    # Initialize database
    try:
        await db_manager.init()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    
    # Initialize Redis cache
    try:
        await cache_manager.init()
        logger.info("✅ Redis cache initialized")
    except Exception as e:
        logger.error(f"Redis initialization failed: {e}")
        raise
    
    # Check health
    db_healthy = await db_manager.health_check()
    redis_healthy = await cache_manager.health_check()
    
    if not db_healthy:
        logger.error("❌ Database health check failed!")
        raise RuntimeError("Database is not healthy")
    
    if not redis_healthy:
        logger.warning("⚠️  Redis health check failed - continuing without cache")
    
    logger.info("=" * 60)
    logger.info("✅ SOLDIA v2.8 is ready!")
    logger.info(f"🌍 Environment: {settings.ENVIRONMENT}")
    logger.info(f"🔧 Debug mode: {settings.DEBUG}")
    logger.info("=" * 60)
    
    yield
    
    # ==================== SHUTDOWN ====================
    logger.info("=" * 60)
    logger.info("🛑 Shutting down SOLDIA v2.8...")
    logger.info("=" * 60)
    
    # Close database connections
    await db_manager.close()
    logger.info("✅ Database connections closed")
    
    # Close Redis connections
    await cache_manager.close()
    logger.info("✅ Redis connections closed")

    # ARCH-2 FIX: Close Solana RPC HTTP session.
    # SolanaClient holds an aiohttp/httpx ClientSession — must be closed on shutdown
    # to avoid "Unclosed client session" warnings and resource leaks.
    try:
        from blockchain.solana_client import solana_client
        await solana_client.close()
        logger.info("✅ Solana RPC connection closed")
    except Exception as e:
        logger.warning(f"Solana client close error (non-fatal): {e}")
    
    logger.info("=" * 60)
    logger.info("👋 SOLDIA v2.8 shutdown complete")
    logger.info("=" * 60)


# ==================== APPLICATION INSTANCE ====================

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="SOLDIA - Exponential Wealth Network API",
    docs_url="/docs" if settings.DEBUG else None,  # Disable docs in production
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan
)


# ==================== RATE LIMITING ====================

def get_rate_limit_key(request: Request) -> str:
    """
    Custom rate limit key function - uses IP address fingerprinting
    
    SECURITY: Does NOT trust X-User-ID header (can be spoofed)
    Instead uses IP + User-Agent hash for fingerprinting
    """
    ip = rate_limit_utils.get_client_ip(request)
    user_agent = rate_limit_utils.get_user_agent(request)
    
    # Try to extract user ID from JWT token (if present)
    # Only use if JWT is valid (not spoofable like X-User-ID header)
    user_id = None
    auth_header = request.headers.get("Authorization", "")
    
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header[7:]
            from security.auth import token_manager
            payload = token_manager.verify_token(token, token_type="access")
            if payload:
                user_id = payload.get("sub")
        except Exception:
            pass
    
    # If we have validated JWT user ID, use it for per-user rate limiting
    if user_id:
        return f"user:{user_id}"
    
    # Otherwise, use IP + User-Agent fingerprint
    # This prevents spoofing while still allowing tracking
    import hashlib
    fingerprint = hashlib.sha256(
        f"{ip}:{user_agent}".encode()
    ).hexdigest()[:16]
    
    return f"ip:{ip}:{fingerprint}"


limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri=settings.RATE_LIMIT_STORAGE if settings.RATE_LIMIT_ENABLED else None,
    enabled=settings.RATE_LIMIT_ENABLED
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ==================== MIDDLEWARE ====================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Rate-Limit-Remaining"]
)

# GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Trusted host (only in production)
if settings.ENVIRONMENT == "production":
    # Extract domains from ALLOWED_ORIGINS
    trusted_hosts = []
    for origin in settings.ALLOWED_ORIGINS:
        # Remove protocol and get domain
        domain = origin.replace("https://", "").replace("http://", "")
        if ":" in domain:
            domain = domain.split(":")[0]
        trusted_hosts.append(domain)
    
    if trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=trusted_hosts
        )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    import time
    
    start_time = time.time()
    
    # Get client info
    client_ip = rate_limit_utils.get_client_ip(request)
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Log request
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.3f}s - "
        f"IP: {client_ip}"
    )
    
    # Add custom headers
    response.headers["X-Process-Time"] = str(duration)
    
    return response


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Content Security Policy (IMPROVED - no unsafe-eval)
    if settings.ENVIRONMENT == "production":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com; "  # no unsafe-eval
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.mainnet-beta.solana.com https://api.devnet.solana.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    
    return response


# ==================== EXCEPTION HANDLERS ====================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.warning(f"Validation error: {exc.errors()}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Validation error",
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # Don't expose internal errors in production
    if settings.ENVIRONMENT == "production":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Internal server error"
            }
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Internal server error",
                "details": str(exc)
            }
        )


# ==================== HEALTH CHECK ENDPOINTS ====================

@app.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "version": settings.API_VERSION,
        "environment": settings.ENVIRONMENT
    }


@app.get("/health/detailed")
@limiter.limit("10/minute")
async def detailed_health_check(
    request: Request,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
):
    """Detailed health check with component status.
    Pool stats are only returned when X-Admin-Key is valid (INFO-1 FIX).
    """
    import hmac
    is_admin = bool(
        x_admin_key and
        hmac.compare_digest(x_admin_key.encode(), settings.ADMIN_API_KEY.encode())
    )

    db_healthy = await db_manager.health_check()
    redis_healthy = await cache_manager.health_check()

    db_info: dict = {"healthy": db_healthy}
    if is_admin:
        db_info["stats"] = db_manager.get_stats()  # sync method, no await

    return {
        "status": "healthy" if (db_healthy and redis_healthy) else "degraded",
        "version": settings.API_VERSION,
        "environment": settings.ENVIRONMENT,
        "components": {
            "database": db_info,
            "redis": {"healthy": redis_healthy},
        },
    }

@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "message": "SOLDIA API v2.8",
        "version": settings.API_VERSION,
        "docs": "/docs" if settings.DEBUG else None,
        "status": "operational"
    }


# ==================== STATIC FILES (Frontend) ====================

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Serve static files (CSS, JS, images)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"✅ Static files mounted from {static_dir}")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend HTML page"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": "SOLDIA API v2.8",
        "version": settings.API_VERSION,
        "note": "Frontend not found. Add index.html to /static/ directory.",
        "api_docs": "/docs" if settings.DEBUG else None
    }


# ==================== MAINTENANCE MODE ====================

@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    """Block requests if in maintenance mode"""
    if settings.MAINTENANCE_MODE:
        # Allow health checks
        if request.url.path in ["/health", "/health/detailed"]:
            return await call_next(request)
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "error": "Service temporarily unavailable for maintenance",
                "retry_after": 3600  # 1 hour
            }
        )
    
    return await call_next(request)


# ==================== IMPORT ROUTERS ====================

from api.routes import (
    users_router,
    deposits_router,
    withdrawals_router,
    referrals_router
)

# Include routers
app.include_router(
    users_router,
    prefix=f"{settings.API_PREFIX}/users",
    tags=["Users"]
)
app.include_router(
    deposits_router,
    prefix=f"{settings.API_PREFIX}/deposits",
    tags=["Deposits"]
)
app.include_router(
    withdrawals_router,
    prefix=f"{settings.API_PREFIX}/withdrawals",
    tags=["Withdrawals"]
)
app.include_router(
    referrals_router,
    prefix=f"{settings.API_PREFIX}/referrals",
    tags=["Referrals"]
)

logger.info("✅ API routes registered")


# ==================== RUN APPLICATION ====================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(settings.PORT if hasattr(settings, 'PORT') else 8000),
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
        workers=1 if settings.DEBUG else 4
    )
