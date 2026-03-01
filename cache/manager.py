"""
✅ FIXED v2.3: Redis Cache Manager

SER-5 FIX: Replaced redis.keys(pattern) with SCAN-based iteration.
  KEYS blocks the entire Redis event loop until complete — O(N) over all keys.
  With 100k keys in Redis, KEYS('user_stats:*') can freeze Redis for seconds,
  blocking ALL other clients during that time.
  SCAN iterates in small batches (cursor-based), non-blocking.
"""

import json
import logging
from typing import Any, Optional, AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from config.settings import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis cache manager with SCAN-safe key enumeration"""

    def __init__(self):
        self._redis: Optional[Redis] = None

    async def init(self):
        if self._redis is not None:
            return
        logger.info("Initializing Redis connection...")
        try:
            # C2 FIX: Use REDIS_URL exactly as configured — do NOT inject the password
            # a second time. In Docker deployments REDIS_URL already contains the password:
            #   redis://:mypass@redis:6379/0
            # The old code did url.replace("redis://", f"redis://:{pw}@") which produced:
            #   redis://:mypass@:mypass@redis:6379/0  ← invalid, raises ValueError on connect.
            # If a bare redis://host URL is used (dev without password), REDIS_PASSWORD can
            # still be passed to from_url via the password= kwarg without corrupting the URL.
            url = settings.REDIS_URL
            kwargs: dict = dict(
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
                socket_keepalive=True,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            # Only supply password kwarg when URL has no credentials embedded
            if settings.REDIS_PASSWORD and "@" not in url.replace("redis://", ""):
                kwargs["password"] = settings.REDIS_PASSWORD

            self._redis = await redis.from_url(url, **kwargs)
            await self._redis.ping()
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def health_check(self) -> bool:
        if not self._redis:
            return False
        try:
            return bool(await self._redis.ping())
        except RedisError:
            return False

    # ── Basic ──────────────────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            return await self._redis.get(key)
        except RedisError as e:
            logger.error(f"Redis GET {key!r}: {e}")
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        if not self._redis:
            return False
        try:
            if ttl:
                await self._redis.setex(key, ttl, value)
            else:
                await self._redis.set(key, value)
            return True
        except RedisError as e:
            logger.error(f"Redis SET {key!r}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        if not self._redis:
            return False
        try:
            await self._redis.delete(key)
            return True
        except RedisError as e:
            logger.error(f"Redis DEL {key!r}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        if not self._redis:
            return False
        try:
            return bool(await self._redis.exists(key))
        except RedisError:
            return False

    # ── JSON ───────────────────────────────────────────────────────────────

    async def get_json(self, key: str) -> Optional[Any]:
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {key!r}: {e}")
            return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        try:
            return await self.set(key, json.dumps(value), ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON encode error for {key!r}: {e}")
            return False

    # ── SER-5: SCAN-based pattern operations ──────────────────────────────

    async def scan_keys(self, pattern: str, count: int = 100) -> AsyncIterator[str]:
        """
        SER-5 FIX: Iterate keys matching pattern using SCAN (non-blocking).

        KEYS(pattern) is O(N) and BLOCKS Redis while running — forbidden in prod.
        SCAN uses cursor-based pagination:
          - Returns at most `count` keys per call (default 100)
          - Does not block other Redis clients between iterations
          - O(N) total work but amortized over many small steps

        Usage:
            async for key in cache_manager.scan_keys("user_stats:*"):
                await cache_manager.delete(key)
        """
        if not self._redis:
            return

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match=pattern, count=count
            )
            for key in keys:
                yield key
            if cursor == 0:
                break

    async def delete_pattern(self, pattern: str) -> int:
        """
        SER-5 FIX: Delete all keys matching pattern using SCAN + pipeline.

        Collects keys in batches of 100 and deletes each batch atomically.
        Non-blocking — does not freeze Redis event loop.
        """
        if not self._redis:
            return 0

        deleted = 0
        batch = []

        async for key in self.scan_keys(pattern):
            batch.append(key)
            if len(batch) >= 100:
                try:
                    deleted += await self._redis.delete(*batch)
                except RedisError as e:
                    logger.error(f"Redis batch delete error: {e}")
                batch = []

        if batch:
            try:
                deleted += await self._redis.delete(*batch)
            except RedisError as e:
                logger.error(f"Redis batch delete error: {e}")

        return deleted

    # ── Hash operations ────────────────────────────────────────────────────

    async def hget(self, name: str, key: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            return await self._redis.hget(name, key)
        except RedisError as e:
            logger.error(f"Redis HGET: {e}")
            return None

    async def hset(self, name: str, key: str, value: str) -> bool:
        if not self._redis:
            return False
        try:
            await self._redis.hset(name, key, value)
            return True
        except RedisError as e:
            logger.error(f"Redis HSET: {e}")
            return False

    async def hgetall(self, name: str) -> dict:
        if not self._redis:
            return {}
        try:
            return await self._redis.hgetall(name)
        except RedisError as e:
            logger.error(f"Redis HGETALL: {e}")
            return {}

    async def hdel(self, name: str, *keys: str) -> bool:
        if not self._redis:
            return False
        try:
            await self._redis.hdel(name, *keys)
            return True
        except RedisError as e:
            logger.error(f"Redis HDEL: {e}")
            return False

    # ── Counters ───────────────────────────────────────────────────────────

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        if not self._redis:
            return None
        try:
            return await self._redis.incr(key, amount)
        except RedisError as e:
            logger.error(f"Redis INCR: {e}")
            return None

    # ── Utility ────────────────────────────────────────────────────────────

    async def expire(self, key: str, ttl: int) -> bool:
        if not self._redis:
            return False
        try:
            return bool(await self._redis.expire(key, ttl))
        except RedisError:
            return False

    async def info(self) -> dict:
        if not self._redis:
            return {}
        try:
            return await self._redis.info()
        except RedisError:
            return {}


# ── Global instance ────────────────────────────────────────────────────────

cache_manager = CacheManager()


@asynccontextmanager
async def lifespan_cache(app):
    await cache_manager.init()
    yield
    await cache_manager.close()
