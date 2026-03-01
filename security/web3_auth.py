"""
✅ FIXED v2.3: Web3 Authentication — Solana Ed25519 signature verification

CRIT-5 FIX: Redis GETDEL (Redis 6.2+) replaced with GET+DEL inside a pipeline.
  Pipeline executes both commands atomically in a single round-trip.
  Works with Redis 4.0+ (LTS versions: 5.x, 6.0, 6.1 all supported).
  If Redis is unavailable — logs ERROR and raises, does NOT silently fall back
  to in-memory (which would allow DoS by exhausting the in-memory nonce store).

SEC-01 original fix still present: nonces in Redis, not in worker memory.
"""

import logging
from typing import Optional

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
import base58

logger = logging.getLogger(__name__)

_redis_client = None
_NONCE_TTL = 300   # 5 minutes


def _get_redis():
    """
    Return shared Redis client. Created once per process.
    Raises RuntimeError if Redis is not configured — no silent fallback.
    """
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            from config.settings import settings
            # ARCH-4 FIX: Use Redis DB 4 for nonces, separate from app cache (DB 0).
            # This prevents a FLUSHDB on the cache DB from silently invalidating
            # all active auth nonces.
            # DB layout: 0=cache, 1=rate-limit, 2=celery-broker, 3=celery-results, 4=auth-nonces
            import re as _re
            _base_url = settings.REDIS_URL
            # ARCH-4 edge-case fix: split off query params before replacing DB number,
            # so "redis://host/0?timeout=100" → "redis://host/4?timeout=100"
            # and NOT "redis://host/0?timeout=100/4".
            _qs_sep   = _base_url.find('?')
            _url_path = _base_url[:_qs_sep] if _qs_sep != -1 else _base_url
            _url_qs   = _base_url[_qs_sep:] if _qs_sep != -1 else ''
            _url_path = _re.sub(r'/\d+$', '/4', _url_path) if _re.search(r'/\d+$', _url_path) else _url_path + '/4'
            _nonce_url = _url_path + _url_qs
            _redis_client = aioredis.from_url(
                _nonce_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
        except Exception as e:
            logger.error(f"Cannot create Redis client: {e}")
            raise RuntimeError("Redis not available — Web3Auth requires Redis") from e
    return _redis_client


class Web3Auth:
    """
    Web3 authentication with Redis-backed nonces.
    All nonce operations are atomic via pipeline — safe under concurrent load.
    """

    async def generate_nonce(self) -> str:
        """
        Generate a one-time nonce and store in Redis with TTL.
        Raises if Redis is unavailable.
        """
        import secrets
        nonce = secrets.token_hex(16)
        redis = _get_redis()
        # SETNX sets only if key doesn't exist — extremely unlikely collision
        await redis.setex(f"nonce:{nonce}", _NONCE_TTL, "1")
        return nonce

    async def consume_nonce(self, nonce: str) -> bool:
        """
        Atomically check and delete nonce in a single pipeline round-trip.

        CRIT-5 FIX: GETDEL is Redis 6.2+ only. We use GET + DEL inside a
        pipeline. A pipeline sends both commands in one TCP packet and Redis
        executes them sequentially without interleaving other clients' commands
        (single-threaded Redis event loop). This is effectively atomic for our
        purposes: no other client can see the nonce between our GET and DEL.

        Compatible with Redis 4.0, 5.x, 6.0, 6.1, 6.2, 7.x.
        """
        redis = _get_redis()
        key = f"nonce:{nonce}"

        try:
            # HIGH-2 FIX: Use transaction=True (MULTI/EXEC) for true atomicity.
            # pipeline(transaction=False) is only a network-level batch — it does NOT
            # prevent another Redis client from interleaving between our GET and DEL.
            # Two concurrent requests could both execute GET before either executes DEL,
            # both see the nonce as valid, and both pass → replay attack.
            # transaction=True wraps commands in MULTI/EXEC which Redis executes
            # as an atomic unit — no other client can interleave.
            async with redis.pipeline(transaction=True) as pipe:
                pipe.get(key)
                pipe.delete(key)
                results = await pipe.execute()

            value = results[0]   # result of GET
            # deleted = results[1]  # result of DEL (1 if existed, 0 if not)

            if value is None:
                logger.warning(f"Nonce not found or already used: {nonce}")
                return False

            return True

        except Exception as e:
            logger.error(f"Redis nonce consume error: {e}", exc_info=True)
            # Do NOT fall back to in-memory — that opens DoS vector.
            # Raise so the caller returns 500, not silently accepts the nonce.
            raise RuntimeError("Nonce storage unavailable") from e

    async def verify_signature(
        self,
        message: str,
        signature: str,
        wallet_address: str,
    ) -> bool:
        """
        Verify Solana Ed25519 wallet signature.

        Args:
            message:        Exact string that was passed to signMessage() on frontend
            signature:      Base58-encoded 64-byte Ed25519 signature
            wallet_address: Solana base58 public key (32 bytes decoded)

        Returns:
            True only if signature is cryptographically valid for this message+key.
        """
        try:
            if not _is_valid_solana_address(wallet_address):
                logger.warning(f"Invalid Solana address: {wallet_address!r}")
                return False

            try:
                sig_bytes = base58.b58decode(signature)
            except Exception:
                logger.warning("Signature base58 decode failed")
                return False

            if len(sig_bytes) != 64:
                logger.warning(f"Signature wrong length: {len(sig_bytes)} (need 64)")
                return False

            try:
                pub_bytes = base58.b58decode(wallet_address)
            except Exception:
                logger.warning("Wallet address base58 decode failed")
                return False

            if len(pub_bytes) != 32:
                logger.warning(f"Public key wrong length: {len(pub_bytes)} (need 32)")
                return False

            verify_key = VerifyKey(pub_bytes)
            verify_key.verify(message.encode("utf-8"), sig_bytes)

            logger.info(f"✅ Signature valid for {wallet_address}")
            return True

        except BadSignatureError:
            logger.warning(f"❌ Bad signature for wallet {wallet_address}")
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}", exc_info=True)
            return False


def _is_valid_solana_address(addr: str) -> bool:
    if not addr or not (32 <= len(addr) <= 44):
        return False
    try:
        return len(base58.b58decode(addr)) == 32
    except Exception:
        return False


# ==================== SINGLETON ====================

_instance: Optional[Web3Auth] = None


def _web3_auth() -> Web3Auth:
    global _instance
    if _instance is None:
        _instance = Web3Auth()
    return _instance


# ==================== PUBLIC HELPERS ====================

async def verify_solana_signature(message: str, signature: str, wallet: str) -> bool:
    """Verify Solana wallet signature. Used by withdrawal endpoint."""
    return await _web3_auth().verify_signature(message, signature, wallet)


async def generate_nonce() -> str:
    """Generate a one-time auth nonce. Used by frontend auth flow."""
    return await _web3_auth().generate_nonce()


async def consume_nonce(nonce: str) -> bool:
    """
    Atomically consume a nonce (check + delete).
    CRIT-5: Uses GET+DEL pipeline, not GETDEL (Redis 6.2+).
    """
    return await _web3_auth().consume_nonce(nonce)


def withdrawal_message(amount, destination: str) -> str:
    """
    Canonical withdrawal message format.
    Must match frontend: `Withdraw ${amount.toFixed(2)} USDC to ${wallet}`

    SIG-1 FIX: formatted with :.2f to match withdraw_funds route which signs
    f"Withdraw {request.amount:.2f} USDC to ...".
    Previously no :.2f here -> frontend using this helper always got 401.
    """
    from decimal import Decimal as _D
    amt = _D(str(amount)) if not isinstance(amount, _D) else amount
    return f"Withdraw {amt:.2f} USDC to {destination}"
