"""Shared cache backend abstraction layer for Fava.

This module provides a pluggable cache backend system that supports:
1. In-memory caching (process-local, for single-worker deployments)
2. Redis caching (cross-worker shared, for multi-worker deployments)
3. Automatic fallback/degradation when Redis is unavailable

The cache backend abstraction defines a standard interface that can be
extended with additional backend implementations in the future.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import threading
import time
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

log = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION: int = 1
"""Schema version for cached data structures.

Bump this constant whenever the format of cached values changes in a
backward-incompatible way. Since the schema version is embedded in the
cache key namespace, old schema values will naturally become misses
after an upgrade instead of causing deserialization errors.
"""


@dataclass(frozen=True)
class CacheConfig:
    """Configuration for the cache backend.

    This configuration can be loaded from environment variables or set
    programmatically. Environment variables use the FAVA_ prefix.

    Environment variables:
        FAVA_CACHE_BACKEND: 'inmemory' or 'redis' (default: 'inmemory')
        FAVA_CACHE_TTL: Default TTL in seconds (default: 300)
        FAVA_REDIS_URL: Redis connection URL (default: 'redis://localhost:6379/0')
        FAVA_REDIS_KEY_PREFIX: Key prefix for Redis (default: 'fava:chart:')
        FAVA_REDIS_MAX_RETRIES: Max retries before fallback (default: 3)
        FAVA_REDIS_RETRY_DELAY: Delay between retries in seconds (default: 0.5)
        FAVA_REDIS_FALLBACK_DURATION: Duration to use fallback in seconds after failure (default: 60)
    """

    backend_type: str = "inmemory"
    default_ttl: int = 300
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "fava:chart:"
    redis_max_retries: int = 3
    redis_retry_delay: float = 0.5
    redis_fallback_duration: int = 60

    @classmethod
    def from_env(cls) -> "CacheConfig":
        """Load configuration from environment variables."""
        backend_type = os.environ.get("FAVA_CACHE_BACKEND", "inmemory").lower()
        if backend_type not in ("inmemory", "redis"):
            log.warning(
                "Unknown cache backend type '%s', falling back to 'inmemory'",
                backend_type,
            )
            backend_type = "inmemory"

        default_ttl = int(os.environ.get("FAVA_CACHE_TTL", "300"))
        redis_url = os.environ.get("FAVA_REDIS_URL", "redis://localhost:6379/0")
        redis_key_prefix = os.environ.get("FAVA_REDIS_KEY_PREFIX", "fava:chart:")
        redis_max_retries = int(os.environ.get("FAVA_REDIS_MAX_RETRIES", "3"))
        redis_retry_delay = float(os.environ.get("FAVA_REDIS_RETRY_DELAY", "0.5"))
        redis_fallback_duration = int(
            os.environ.get("FAVA_REDIS_FALLBACK_DURATION", "60")
        )

        return cls(
            backend_type=backend_type,
            default_ttl=default_ttl,
            redis_url=redis_url,
            redis_key_prefix=redis_key_prefix,
            redis_max_retries=redis_max_retries,
            redis_retry_delay=redis_retry_delay,
            redis_fallback_duration=redis_fallback_duration,
        )

    @classmethod
    def from_options(cls, options: Mapping[str, Any] | None) -> "CacheConfig":
        """Load configuration from a mapping (e.g., FavaOptions)."""
        config = cls.from_env()

        if options is None:
            return config

        backend_type = options.get("cache_backend")
        if isinstance(backend_type, str) and backend_type.lower() in (
            "inmemory",
            "redis",
        ):
            config = _replace_field(config, "backend_type", backend_type.lower())

        default_ttl = options.get("cache_default_ttl")
        if isinstance(default_ttl, int) and default_ttl > 0:
            config = _replace_field(config, "default_ttl", default_ttl)

        redis_url = options.get("cache_redis_url")
        if isinstance(redis_url, str):
            config = _replace_field(config, "redis_url", redis_url)

        redis_key_prefix = options.get("cache_redis_key_prefix")
        if isinstance(redis_key_prefix, str):
            config = _replace_field(config, "redis_key_prefix", redis_key_prefix)

        return config


def _replace_field(config: CacheConfig, field: str, value: Any) -> CacheConfig:
    """Create a new CacheConfig with one field replaced."""
    from dataclasses import replace

    return replace(config, **{field: value})


@dataclass(frozen=True)
class CacheStats:
    """Statistics for cache operations.

    Attributes:
        hits: Number of cache hits.
        misses: Number of cache misses.
        errors: Number of backend errors (e.g., Redis connection failures).
        fallbacks: Number of times fallback to in-memory occurred.
        total_requests: Total number of cache requests.
        hit_rate: Cache hit rate (0.0 to 1.0).
    """

    hits: int = 0
    misses: int = 0
    errors: int = 0
    fallbacks: int = 0

    @property
    def total_requests(self) -> int:
        """Total number of cache requests."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a float between 0 and 1."""
        total = self.total_requests
        return self.hits / total if total > 0 else 0.0

    def record_hit(self) -> "CacheStats":
        """Record a cache hit and return updated stats."""
        from dataclasses import replace

        return replace(self, hits=self.hits + 1)

    def record_miss(self) -> "CacheStats":
        """Record a cache miss and return updated stats."""
        from dataclasses import replace

        return replace(self, misses=self.misses + 1)

    def record_error(self) -> "CacheStats":
        """Record a backend error and return updated stats."""
        from dataclasses import replace

        return replace(self, errors=self.errors + 1)

    def record_fallback(self) -> "CacheStats":
        """Record a fallback event and return updated stats."""
        from dataclasses import replace

        return replace(self, fallbacks=self.fallbacks + 1)

    def reset(self) -> "CacheStats":
        """Reset all statistics."""
        return CacheStats()


def make_cache_key(
    *parts: Any,
    time_window_start: str | None = None,
    time_window_end: str | None = None,
    currency: str | None = None,
    **kwargs: Any,
) -> str:
    """Generate a deterministic cache key from parameters.

    This function ensures that cache keys consistently include:
    - Optional time window (start/end dates)
    - Optional currency
    - Any additional positional/keyword arguments

    Args:
        *parts: Additional positional parts for the key.
        time_window_start: Start date of time window (ISO format).
        time_window_end: End date of time window (ISO format).
        currency: Currency identifier.
        **kwargs: Additional keyword arguments.

    Returns:
        A hex-encoded MD5 hash string representing the cache key.
    """
    key_parts = []

    for part in parts:
        key_parts.append(str(part))

    if time_window_start is not None:
        key_parts.append(f"__tw_start={time_window_start}")
    if time_window_end is not None:
        key_parts.append(f"__tw_end={time_window_end}")
    if currency is not None:
        key_parts.append(f"__currency={currency}")

    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")

    key_str = "|".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


def ledger_namespace_hash(ledger_path: str | None) -> str:
    """Generate a stable namespace prefix for a ledger.

    Uses the absolute path of the ledger's beancount file to create a
    short, deterministic hash that serves as a namespace prefix for all
    cache keys. This ensures that multiple ledgers sharing the same
    Redis instance will never have key collisions.

    When ledger_path is None (e.g., in standalone testing), returns
    'default' as a fallback namespace.

    Args:
        ledger_path: Absolute path to the ledger's beancount file.

    Returns:
        A short hex string (8 chars) suitable for use as a key prefix.
    """
    if ledger_path is None:
        return "default"

    from pathlib import Path

    absolute_path = str(Path(ledger_path).resolve())
    full_hash = hashlib.sha256(absolute_path.encode()).hexdigest()
    return full_hash[:8]


def build_full_namespace(
    ledger_namespace: str,
    schema_version: int | None = None,
) -> str:
    """Build the full namespace prefix including schema version.

    The full namespace consists of a schema version segment plus the
    ledger hash segment. When the schema version changes, all cached
    values under the old schema naturally become misses.

    Args:
        ledger_namespace: The ledger namespace hash from ledger_namespace_hash().
        schema_version: Schema version to use. Defaults to CACHE_SCHEMA_VERSION.

    Returns:
        Full namespace string in the format "s{version}:{ledger_namespace}".
    """
    version = schema_version if schema_version is not None else CACHE_SCHEMA_VERSION
    return f"s{version}:{ledger_namespace}"


def namespaced_ledger_key(
    ledger_namespace: str,
    base_key: str,
    *,
    schema_version: int | None = None,
) -> str:
    """Combine a ledger namespace (with schema version) with a base cache key.

    Args:
        ledger_namespace: The ledger namespace hash from ledger_namespace_hash().
        base_key: The base cache key (e.g., from make_cache_key()).
        schema_version: Optional schema version override.
            Defaults to :data:`CACHE_SCHEMA_VERSION`.

    Returns:
        A composite key in the format "s{version}:<ledger_namespace>:<base_key>".
    """
    full_ns = build_full_namespace(ledger_namespace, schema_version)
    return f"{full_ns}:{base_key}"


class CacheBackend(ABC):
    """Abstract base class for cache backends.

    All cache backends must implement this interface to be pluggable
    into Fava's cache system.
    """

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value, or None if not found or expired.

        Raises:
            CacheBackendError: If the backend encounters an error
                (e.g., Redis connection failure).
        """
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Time-to-live in seconds. If None, uses the backend's default.

        Raises:
            CacheBackendError: If the backend encounters an error.
        """
        ...

    @abstractmethod
    def ttl(self, key: str) -> int | None:
        """Get the remaining TTL for a key.

        Args:
            key: The cache key.

        Returns:
            Remaining TTL in seconds, None if key doesn't exist,
            or -1 if the key has no expiration.

        Raises:
            CacheBackendError: If the backend encounters an error.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all entries from the cache.

        Raises:
            CacheBackendError: If the backend encounters an error.
        """
        ...

    @property
    @abstractmethod
    def stats(self) -> CacheStats:
        """Get cache operation statistics."""
        ...

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        ...  # noqa: D401 - default no-op

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is currently available for use."""
        ...


class CacheBackendError(Exception):
    """Raised when a cache backend encounters an error.

    This exception is used to signal that the primary backend has
    failed and the caller should consider using a fallback.
    """


class InMemoryCacheBackend(CacheBackend):
    """Process-local in-memory TTL cache backend.

    This backend is suitable for single-worker deployments. In multi-worker
    deployments, each worker maintains its own independent cache.

    Thread-safe.
    """

    @dataclass
    class _Entry:
        """Internal cache entry."""

        value: Any
        expiry: float

    def __init__(self, default_ttl: int = 300) -> None:
        """Initialize the in-memory cache.

        Args:
            default_ttl: Default TTL for cache entries in seconds.
        """
        self._default_ttl = default_ttl
        self._cache: dict[str, InMemoryCacheBackend._Entry] = {}
        self._lock = threading.Lock()
        self._stats = CacheStats()

    def get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if now < entry.expiry:
                    self._stats = self._stats.record_hit()
                    return entry.value
                del self._cache[key]
            self._stats = self._stats.record_miss()
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in the cache."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expiry = time.time() + effective_ttl
        with self._lock:
            self._cache[key] = InMemoryCacheBackend._Entry(
                value=value, expiry=expiry
            )

    def ttl(self, key: str) -> int | None:
        """Get the remaining TTL for a key."""
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            remaining = entry.expiry - now
            if remaining <= 0:
                del self._cache[key]
                return None
            return int(remaining)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    @property
    def stats(self) -> CacheStats:
        """Get cache operation statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        with self._lock:
            self._stats = CacheStats()

    @property
    def is_available(self) -> bool:
        """In-memory cache is always available."""
        return True

    def clear_expired(self) -> int:
        """Clear all expired entries from the cache.

        Returns:
            Number of entries removed.
        """
        now = time.time()
        removed = 0
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if now >= v.expiry
            ]
            for k in expired_keys:
                del self._cache[k]
                removed += 1
        return removed

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        with self._lock:
            return len(self._cache)


class RedisCacheBackend(CacheBackend):
    """Redis-backed shared cache for multi-worker deployments.

    This backend uses Redis to provide a shared cache across multiple
    worker processes. It includes automatic retry logic and failure
    detection for graceful degradation.

    Uses lazy initialization for the Redis connection so that it fails
    gracefully if redis is not installed.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "fava:chart:",
        default_ttl: int = 300,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> None:
        """Initialize the Redis cache backend.

        Args:
            redis_url: Redis connection URL.
            key_prefix: Prefix to prepend to all cache keys.
            default_ttl: Default TTL for cache entries in seconds.
            max_retries: Maximum number of retry attempts per operation.
            retry_delay: Delay between retry attempts in seconds.
        """
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._max_retries = max_retries
        self._retry_delay = retry_delay

        self._client: Any = None
        self._stats = CacheStats()
        self._available = True
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        """Get or create the Redis client.

        Lazy initialization - only creates client when first needed.

        Returns:
            The Redis client.

        Raises:
            CacheBackendError: If redis package is not installed or
                connection fails during initial ping.
        """
        if self._client is not None:
            return self._client

        try:
            import redis
        except ImportError as err:
            raise CacheBackendError(
                "Redis backend requires 'redis' package. "
                "Install with: pip install redis"
            ) from err

        try:
            self._client = redis.Redis.from_url(
                self._redis_url,
                decode_responses=False,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            self._client.ping()
            return self._client
        except Exception as err:
            self._available = False
            raise CacheBackendError(
                f"Failed to connect to Redis at {self._redis_url}: {err}"
            ) from err

    def _full_key(self, key: str) -> str:
        """Get the full Redis key with prefix."""
        return f"{self._key_prefix}{key}"

    def _serialize(self, value: Any) -> bytes:
        """Serialize a value for storage in Redis."""
        try:
            return pickle.dumps(value)
        except Exception:
            serialized = json.dumps(value, default=str, ensure_ascii=False)
            return serialized.encode("utf-8")

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize a value from Redis."""
        try:
            return pickle.loads(data)
        except Exception:
            try:
                return json.loads(data.decode("utf-8"))
            except Exception:
                return data

    def _execute_with_retry(
        self, operation: str, func: Callable[[Any], Any]
    ) -> Any:
        """Execute a Redis operation with retry logic.

        Args:
            operation: Operation name for logging.
            func: Function to execute with Redis client as argument.

        Returns:
            The result of the operation.

        Raises:
            CacheBackendError: If all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                client = self._get_client()
                result = func(client)
                self._available = True
                return result
            except CacheBackendError:
                raise
            except Exception as err:
                last_error = err
                log.warning(
                    "Redis %s attempt %d/%d failed: %s",
                    operation,
                    attempt + 1,
                    self._max_retries,
                    err,
                )
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)

        self._available = False
        self._stats = self._stats.record_error()
        raise CacheBackendError(
            f"Redis {operation} failed after {self._max_retries} attempts: "
            f"{last_error}"
        )

    def get(self, key: str) -> Any | None:
        """Get a value from Redis."""
        full_key = self._full_key(key)

        def _op(client: Any) -> Any:
            data = client.get(full_key)
            if data is None:
                return None
            return self._deserialize(data)

        try:
            result = self._execute_with_retry("get", _op)
            if result is None:
                self._stats = self._stats.record_miss()
            else:
                self._stats = self._stats.record_hit()
            return result
        except CacheBackendError:
            raise

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in Redis."""
        full_key = self._full_key(key)
        effective_ttl = ttl if ttl is not None else self._default_ttl
        serialized = self._serialize(value)

        def _op(client: Any) -> None:
            client.setex(full_key, effective_ttl, serialized)

        try:
            self._execute_with_retry("set", _op)
        except CacheBackendError:
            raise

    def ttl(self, key: str) -> int | None:
        """Get remaining TTL for a key in Redis."""
        full_key = self._full_key(key)

        def _op(client: Any) -> int | None:
            result = client.ttl(full_key)
            if result == -2:
                return None
            if result == -1:
                return -1
            return int(result)

        try:
            return self._execute_with_retry("ttl", _op)
        except CacheBackendError:
            raise

    def clear(self) -> None:
        """Clear all entries matching the key prefix."""

        def _op(client: Any) -> None:
            pattern = f"{self._key_prefix}*"
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    client.delete(*keys)
                if cursor == 0:
                    break

        try:
            self._execute_with_retry("clear", _op)
        except CacheBackendError:
            raise

    @property
    def stats(self) -> CacheStats:
        """Get cache operation statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        with self._lock:
            self._stats = CacheStats()

    @property
    def is_available(self) -> bool:
        """Check if Redis backend is available."""
        return self._available

    def check_health(self) -> bool:
        """Check if Redis is reachable.

        Attempts to ping Redis. Updates the availability flag.

        Returns:
            True if Redis is reachable, False otherwise.
        """
        try:
            client = self._get_client()
            client.ping()
            self._available = True
            return True
        except Exception:
            self._available = False
            return False


class FallbackCacheManager(CacheBackend):
    """Cache manager with automatic fallback to in-memory cache.

    This manager wraps a primary cache backend (typically Redis) and
    automatically falls back to an in-memory cache when the primary
    backend is unavailable. Fallback behavior includes:

    1. Transparent read-through to fallback when primary fails
    2. Write-through to both backends when possible
    3. Temporarily disable primary after repeated failures
    4. Periodically attempt to restore primary connectivity
    5. Log warning when fallback is activated
    """

    def __init__(
        self,
        primary: CacheBackend,
        fallback: CacheBackend | None = None,
        fallback_duration: int = 60,
    ) -> None:
        """Initialize the fallback cache manager.

        Args:
            primary: Primary cache backend (e.g., Redis).
            fallback: Fallback backend (default: InMemoryCacheBackend).
            fallback_duration: Seconds to use fallback before rechecking primary.
        """
        self._primary = primary
        self._fallback = fallback or InMemoryCacheBackend()
        self._fallback_duration = fallback_duration

        self._fallback_active = False
        self._fallback_until: float = 0.0
        self._lock = threading.Lock()
        self._stats = CacheStats()

    def _should_use_fallback(self) -> bool:
        """Check if we should currently use the fallback backend."""
        now = time.time()
        if self._fallback_active and now < self._fallback_until:
            return True

        if self._fallback_active and now >= self._fallback_until:
            self._fallback_active = False
            log.info("Fallback period expired, attempting to restore primary cache")

        return False

    def _activate_fallback(self, reason: str) -> None:
        """Activate fallback mode and log a warning."""
        with self._lock:
            self._fallback_active = True
            self._fallback_until = time.time() + self._fallback_duration
            self._stats = self._stats.record_fallback()
        log.warning(
            "Cache fallback activated for %d seconds: %s. "
            "Using in-memory cache instead.",
            self._fallback_duration,
            reason,
        )

    def _try_primary_operation(
        self,
        operation_name: str,
        func: Callable[[CacheBackend], Any],
    ) -> Any:
        """Try an operation on primary, falling back if necessary.

        Args:
            operation_name: Name of the operation for logging.
            func: Function taking a backend and returning the result.

        Returns:
            The operation result.
        """
        if self._should_use_fallback():
            return func(self._fallback)

        try:
            return func(self._primary)
        except CacheBackendError as err:
            self._activate_fallback(str(err))
            return func(self._fallback)

    def get(self, key: str) -> Any | None:
        """Get a value, falling back to in-memory if primary fails."""
        result = self._try_primary_operation(
            "get", lambda backend: backend.get(key)
        )
        return result

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in both primary (if available) and fallback."""
        try:
            if not self._should_use_fallback():
                self._primary.set(key, value, ttl)
        except CacheBackendError as err:
            self._activate_fallback(str(err))

        try:
            self._fallback.set(key, value, ttl)
        except Exception:
            pass

    def ttl(self, key: str) -> int | None:
        """Get TTL from primary or fallback."""
        return self._try_primary_operation(
            "ttl", lambda backend: backend.ttl(key)
        )

    def clear(self) -> None:
        """Clear both primary and fallback caches."""
        try:
            if not self._should_use_fallback():
                self._primary.clear()
        except CacheBackendError as err:
            self._activate_fallback(str(err))

        try:
            self._fallback.clear()
        except Exception:
            pass

    @property
    def stats(self) -> CacheStats:
        """Get combined statistics from primary, fallback, and fallback events."""
        primary_stats = self._primary.stats
        fallback_stats = self._fallback.stats

        return CacheStats(
            hits=primary_stats.hits + fallback_stats.hits,
            misses=primary_stats.misses + fallback_stats.misses,
            errors=primary_stats.errors + fallback_stats.errors,
            fallbacks=self._stats.fallbacks,
        )

    def reset_stats(self) -> None:
        """Reset statistics on all backends."""
        self._primary.reset_stats()
        self._fallback.reset_stats()
        with self._lock:
            self._stats = CacheStats()

    @property
    def is_available(self) -> bool:
        """Check if either backend is available (fallback always is)."""
        return self._primary.is_available or self._fallback.is_available

    @property
    def primary(self) -> CacheBackend:
        """Access the primary backend."""
        return self._primary

    @property
    def fallback(self) -> CacheBackend:
        """Access the fallback backend."""
        return self._fallback

    @property
    def is_fallback_active(self) -> bool:
        """Check if we are currently operating in fallback mode."""
        return self._fallback_active and time.time() < self._fallback_until

    def restore_primary(self) -> bool:
        """Attempt to restore primary backend connectivity.

        Returns:
            True if primary is now available.
        """
        with self._lock:
            self._fallback_active = False
            self._fallback_until = 0.0

        if hasattr(self._primary, "check_health"):
            return self._primary.check_health()  # type: ignore[attr-defined]
        return self._primary.is_available


def create_cache_backend(config: CacheConfig | None = None) -> CacheBackend:
    """Create a cache backend based on configuration.

    Automatically wraps non-in-memory backends with FallbackCacheManager.

    Args:
        config: Cache configuration (default: loaded from environment).

    Returns:
        A configured CacheBackend instance.
    """
    if config is None:
        config = CacheConfig.from_env()

    log.info("Creating cache backend: type=%s", config.backend_type)

    if config.backend_type == "redis":
        primary = RedisCacheBackend(
            redis_url=config.redis_url,
            key_prefix=config.redis_key_prefix,
            default_ttl=config.default_ttl,
            max_retries=config.redis_max_retries,
            retry_delay=config.redis_retry_delay,
        )
        fallback = InMemoryCacheBackend(default_ttl=config.default_ttl)
        return FallbackCacheManager(
            primary=primary,
            fallback=fallback,
            fallback_duration=config.redis_fallback_duration,
        )

    return InMemoryCacheBackend(default_ttl=config.default_ttl)


class TTLCache(InMemoryCacheBackend):
    """Backward-compatible TTL cache with the legacy (*parts, **kwargs) key API.

    This class exists to keep existing tests and call sites working after
    the cache backend refactor. New code should use :class:`InMemoryCacheBackend`
    (or the higher-level :class:`ChartDataService`) directly, which operates
    on plain string keys produced by :func:`make_cache_key`.

    Legacy API:
        ``cache.set(value, *parts, **kwargs)``
        ``cache.get(*parts, **kwargs)``
    """

    def __init__(self, ttl: int = 300, default_ttl: int | None = None) -> None:
        super().__init__(default_ttl=default_ttl if default_ttl is not None else ttl)

    def set(  # type: ignore[override]
        self,
        value: Any,
        *parts: Any,
        ttl: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Set a cache entry using legacy (*parts, **kwargs) key syntax.

        Args:
            value: The value to store.
            *parts: Positional parts that are combined into the cache key.
            ttl: Optional custom TTL for this entry (in seconds).
            **kwargs: Keyword parts that are combined into the cache key.
        """
        key = make_cache_key(*parts, **kwargs)
        super().set(key, value, ttl=ttl)

    def get(self, *parts: Any, **kwargs: Any) -> Any | None:  # type: ignore[override]
        """Get a cache entry using legacy (*parts, **kwargs) key syntax.

        Args:
            *parts: Positional parts that are combined into the cache key.
            **kwargs: Keyword parts that are combined into the cache key.

        Returns:
            The cached value, or None if not found / expired.
        """
        key = make_cache_key(*parts, **kwargs)
        return super().get(key)


if TYPE_CHECKING:
    from collections.abc import Callable
