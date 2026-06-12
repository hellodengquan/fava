"""Tests for the shared cache backend abstraction layer.

Covers three required scenarios:
1. Switching cache backends at runtime
2. Redis backend failure with automatic fallback to InMemory
3. Cache key generation including time window and currency
"""

from __future__ import annotations

import time
from datetime import date
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from fava.core.cache_backend import (
    CacheBackend,
    CacheBackendError,
    CacheConfig,
    CacheStats,
    FallbackCacheManager,
    InMemoryCacheBackend,
    RedisCacheBackend,
    create_cache_backend,
    make_cache_key,
)
from fava.core.chart_data_service import ChartDataService

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def inmemory_backend() -> InMemoryCacheBackend:
    """Create a fresh InMemoryCacheBackend instance."""
    return InMemoryCacheBackend(default_ttl=300)


@pytest.fixture
def fallback_manager() -> FallbackCacheManager:
    """Create a FallbackCacheManager with a mock Redis primary."""
    primary = InMemoryCacheBackend(default_ttl=300)
    fallback = InMemoryCacheBackend(default_ttl=300)
    return FallbackCacheManager(
        primary=primary, fallback=fallback, fallback_duration=60
    )


class TestCacheKeyGeneration:
    """Tests for cache key generation with time window and currency.

    Covers scenario 3: Cache keys must include time window and currency
    parameters to ensure proper cache isolation.
    """

    def test_key_includes_time_window(self) -> None:
        """Test that different time windows produce different keys."""
        key_jan = make_cache_key(
            "aggregation",
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            account="Expenses:Test",
        )
        key_feb = make_cache_key(
            "aggregation",
            time_window_start="2024-02-01",
            time_window_end="2024-03-01",
            account="Expenses:Test",
        )

        assert key_jan != key_feb, (
            "Different time windows must produce different cache keys"
        )

    def test_key_includes_currency(self) -> None:
        """Test that different currencies produce different keys."""
        key_usd = make_cache_key(
            "aggregation",
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            currency="USD",
            account="Expenses:Test",
        )
        key_eur = make_cache_key(
            "aggregation",
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            currency="EUR",
            account="Expenses:Test",
        )

        assert key_usd != key_eur, (
            "Different currencies must produce different cache keys"
        )

    def test_key_includes_both_time_window_and_currency(self) -> None:
        """Test that both time window and currency are included together."""
        keys = {}

        for month in range(1, 4):
            for currency in ["USD", "EUR", "GBP"]:
                key = make_cache_key(
                    "aggregation",
                    time_window_start=f"2024-{month:02d}-01",
                    time_window_end=f"2024-{month + 1:02d}-01",
                    currency=currency,
                    account="Expenses:Test",
                )
                keys[(month, currency)] = key

        unique_keys = set(keys.values())
        assert len(unique_keys) == 9, (
            "All 9 combinations of (3 months x 3 currencies) "
            "must produce unique cache keys"
        )

    def test_same_params_produce_same_key(self) -> None:
        """Test that identical parameters always produce the same key."""
        params = dict(
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            currency="USD",
            account="Expenses:Category001",
            conversion="at_cost",
        )

        key1 = make_cache_key("aggregation", **params)
        key2 = make_cache_key("aggregation", **params)

        assert key1 == key2, "Identical params must produce identical keys"

    def test_currency_none_vs_set(self) -> None:
        """Test that currency=None vs currency='USD' produce different keys."""
        key_none = make_cache_key(
            "aggregation",
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            account="Expenses:Test",
        )
        key_usd = make_cache_key(
            "aggregation",
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            currency="USD",
            account="Expenses:Test",
        )

        assert key_none != key_usd, (
            "currency=None must differ from a specific currency"
        )

    def test_time_window_start_only(self) -> None:
        """Test that only specifying start (not end) still affects key."""
        key_jan = make_cache_key(
            "aggregation",
            time_window_start="2024-01-01",
            currency="USD",
            account="Expenses:Test",
        )
        key_feb = make_cache_key(
            "aggregation",
            time_window_start="2024-02-01",
            currency="USD",
            account="Expenses:Test",
        )

        assert key_jan != key_feb

    def test_deterministic_hash(self) -> None:
        """Test that make_cache_key produces valid MD5 hex strings."""
        key = make_cache_key(
            "test",
            time_window_start="2024-01-01",
            currency="USD",
        )

        assert isinstance(key, str)
        assert len(key) == 32
        int(key, 16)


class TestSwitchBackend:
    """Tests for switching cache backends at runtime.

    Covers scenario 1: Ability to switch between InMemory and Redis
    (and vice versa) at runtime without losing functionality.
    """

    def test_set_cache_backend_switch(self) -> None:
        """Test switching cache backend on ChartDataService."""
        backend_a = InMemoryCacheBackend(default_ttl=300)
        backend_b = InMemoryCacheBackend(default_ttl=300)

        service = ChartDataService(prices=None, options={}, cache_backend=backend_a)

        assert service.cache is backend_a

        service.set_cache_backend(backend_b)
        assert service.cache is backend_b

        service.set_cache_backend(backend_a)
        assert service.cache is backend_a

    def test_switch_preserves_independent_state(self) -> None:
        """Test that switching backends keeps their data independent."""
        backend_1 = InMemoryCacheBackend(default_ttl=300)
        backend_2 = InMemoryCacheBackend(default_ttl=300)

        service = ChartDataService(prices=None, options={}, cache_backend=backend_1)

        test_key = make_cache_key(
            "test", time_window_start="2024-01-01", currency="USD"
        )

        service.cache.set(test_key, "value_in_backend_1")
        assert service.cache.get(test_key) == "value_in_backend_1"

        service.set_cache_backend(backend_2)
        assert service.cache.get(test_key) is None, (
            "New backend should not have data from old backend"
        )

        service.cache.set(test_key, "value_in_backend_2")
        assert service.cache.get(test_key) == "value_in_backend_2"

        service.set_cache_backend(backend_1)
        assert service.cache.get(test_key) == "value_in_backend_1", (
            "Switching back should restore original data"
        )

    def test_create_from_config_inmemory(self) -> None:
        """Test creating backend from config with type=inmemory."""
        config = CacheConfig(backend_type="inmemory", default_ttl=120)
        backend = create_cache_backend(config)

        assert isinstance(backend, InMemoryCacheBackend)

        test_key = make_cache_key(
            "config_test", time_window_start="2024-01-01"
        )
        backend.set(test_key, "test_value")
        assert backend.get(test_key) == "test_value"

    def test_create_from_config_redis_wraps_with_fallback(self) -> None:
        """Test creating redis backend wraps with FallbackCacheManager."""
        config = CacheConfig(
            backend_type="redis",
            default_ttl=120,
            redis_url="redis://localhost:6379/15",
        )
        backend = create_cache_backend(config)

        assert isinstance(backend, FallbackCacheManager)
        assert isinstance(backend.primary, RedisCacheBackend)
        assert isinstance(backend.fallback, InMemoryCacheBackend)

    def test_env_config_inmemory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading config from environment variables."""
        monkeypatch.setenv("FAVA_CACHE_BACKEND", "inmemory")
        monkeypatch.setenv("FAVA_CACHE_TTL", "600")

        config = CacheConfig.from_env()
        assert config.backend_type == "inmemory"
        assert config.default_ttl == 600

    def test_env_config_redis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading redis config from environment variables."""
        monkeypatch.setenv("FAVA_CACHE_BACKEND", "redis")
        monkeypatch.setenv("FAVA_REDIS_URL", "redis://myhost:6380/3")
        monkeypatch.setenv("FAVA_REDIS_KEY_PREFIX", "myapp:")

        config = CacheConfig.from_env()
        assert config.backend_type == "redis"
        assert config.redis_url == "redis://myhost:6380/3"
        assert config.redis_key_prefix == "myapp:"

    def test_config_invalid_backend_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid backend type falls back to inmemory."""
        monkeypatch.setenv("FAVA_CACHE_BACKEND", "nonexistent")

        config = CacheConfig.from_env()
        assert config.backend_type == "inmemory"


class TestRedisFallback:
    """Tests for Redis backend failure and automatic fallback.

    Covers scenario 2: When Redis is unreachable, the system should:
    1. Automatically fall back to InMemory cache
    2. Log warning messages
    3. Continue operating normally during fallback
    4. Attempt to restore Redis after the fallback period expires
    """

    def test_fallback_manager_gets_from_primary(self) -> None:
        """Test that reads go to primary when it's available."""
        primary = InMemoryCacheBackend(default_ttl=300)
        fallback = InMemoryCacheBackend(default_ttl=300)
        manager = FallbackCacheManager(primary, fallback, fallback_duration=60)

        test_key = make_cache_key(
            "test", time_window_start="2024-01-01", currency="USD"
        )

        primary.set(test_key, "primary_value")
        assert manager.get(test_key) == "primary_value"

        assert primary.stats.hits == 1
        assert fallback.stats.hits == 0

    def test_fallback_on_primary_error(self) -> None:
        """Test automatic fallback when primary raises CacheBackendError."""

        class FailingPrimary(CacheBackend):
            """A mock cache backend that always fails."""

            def __init__(self) -> None:
                self._stats = CacheStats()

            def get(self, key: str):
                raise CacheBackendError("Simulated Redis connection failure")

            def set(self, key: str, value, ttl=None):
                raise CacheBackendError("Simulated Redis connection failure")

            def ttl(self, key: str):
                raise CacheBackendError("Simulated Redis failure")

            def clear(self):
                raise CacheBackendError("Simulated Redis failure")

            @property
            def stats(self) -> CacheStats:
                return self._stats

            def reset_stats(self) -> None:
                self._stats = CacheStats()

            @property
            def is_available(self) -> bool:
                return False

        failing_primary = FailingPrimary()
        inmemory_fallback = InMemoryCacheBackend(default_ttl=300)

        manager = FallbackCacheManager(
            failing_primary, inmemory_fallback, fallback_duration=60
        )

        test_key = make_cache_key(
            "agg",
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            currency="EUR",
        )

        manager.set(test_key, "fallback_saved_value")
        result = manager.get(test_key)

        assert result == "fallback_saved_value", (
            "Should get value from fallback after primary failure"
        )
        assert manager.is_fallback_active is True
        assert inmemory_fallback.stats.hits == 1
        assert manager.stats.fallbacks >= 1

    def test_fallback_period_expires(self) -> None:
        """Test that fallback period expires and retries primary."""
        primary = InMemoryCacheBackend(default_ttl=300)
        fallback = InMemoryCacheBackend(default_ttl=300)

        manager = FallbackCacheManager(
            primary, fallback, fallback_duration=1
        )

        test_key = make_cache_key(
            "test", time_window_start="2024-01-01", currency="USD"
        )
        primary.set(test_key, "primary_data")

        manager._activate_fallback("test activation")
        assert manager.is_fallback_active is True

        fallback.set(test_key, "fallback_data")
        assert manager.get(test_key) == "fallback_data"

        time.sleep(1.2)

        result = manager.get(test_key)
        assert result == "primary_data", (
            "After fallback period, should read from primary again"
        )
        assert manager.is_fallback_active is False

    def test_write_through_to_fallback_on_primary_error(self) -> None:
        """Test that writes go to fallback when primary fails."""

        class WriteFailingPrimary(CacheBackend):
            """Mock backend that fails on writes but succeeds on reads."""

            def __init__(self) -> None:
                self._cache: dict[str, tuple] = {}
                self._stats = CacheStats()
                self._fail_count = 0

            def get(self, key: str):
                entry = self._cache.get(key)
                if entry is None:
                    self._stats = self._stats.record_miss()
                    return None
                self._stats = self._stats.record_hit()
                return entry[0]

            def set(self, key: str, value, ttl=None):
                self._fail_count += 1
                raise CacheBackendError(
                    f"Write failure #{self._fail_count}"
                )

            def ttl(self, key: str):
                return 100

            def clear(self):
                self._cache.clear()

            @property
            def stats(self) -> CacheStats:
                return self._stats

            def reset_stats(self) -> None:
                self._stats = CacheStats()

            @property
            def is_available(self) -> bool:
                return True

        write_failing = WriteFailingPrimary()
        inmemory = InMemoryCacheBackend(default_ttl=300)

        manager = FallbackCacheManager(
            write_failing, inmemory, fallback_duration=30
        )

        test_key = make_cache_key(
            "write_test",
            time_window_start="2024-01-01",
            currency="GBP",
        )

        manager.set(test_key, "persisted_value")

        assert inmemory.get(test_key) == "persisted_value", (
            "Write must succeed on fallback even when primary fails"
        )
        assert manager.stats.fallbacks >= 1

    def test_restore_primary(self) -> None:
        """Test manually attempting to restore primary connectivity."""

        class FlakyPrimary(CacheBackend):
            """Mock backend that can be toggled between available/unavailable."""

            def __init__(self) -> None:
                self._stats = CacheStats()
                self._available = False
                self._data: dict[str, Any] = {}

            def get(self, key: str):
                if not self._available:
                    raise CacheBackendError("Still down")
                v = self._data.get(key)
                if v is None:
                    self._stats = self._stats.record_miss()
                else:
                    self._stats = self._stats.record_hit()
                return v

            def set(self, key: str, value, ttl=None):
                if not self._available:
                    raise CacheBackendError("Still down")
                self._data[key] = value

            def ttl(self, key: str):
                return 100

            def clear(self):
                self._data.clear()

            def check_health(self) -> bool:
                return self._available

            @property
            def stats(self) -> CacheStats:
                return self._stats

            def reset_stats(self) -> None:
                self._stats = CacheStats()

            @property
            def is_available(self) -> bool:
                return self._available

        flaky = FlakyPrimary()
        inmemory = InMemoryCacheBackend(default_ttl=300)

        manager = FallbackCacheManager(flaky, inmemory, fallback_duration=600)

        manager._activate_fallback("primary_down")
        assert manager.is_fallback_active is True

        restored = manager.restore_primary()
        assert restored is False

        flaky._available = True
        restored = manager.restore_primary()
        assert restored is True
        assert manager.is_fallback_active is False

    def test_fallback_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that activating fallback logs a warning message."""

        class FailingGet(CacheBackend):
            def __init__(self) -> None:
                self._stats = CacheStats()

            def get(self, key: str):
                raise CacheBackendError("Redis connection refused")

            def set(self, key: str, value, ttl=None):
                pass

            def ttl(self, key: str):
                return None

            def clear(self):
                pass

            @property
            def stats(self) -> CacheStats:
                return self._stats

            def reset_stats(self) -> None:
                pass

            @property
            def is_available(self) -> bool:
                return False

        import logging

        failing = FailingGet()
        inmemory = InMemoryCacheBackend(default_ttl=300)
        manager = FallbackCacheManager(failing, inmemory, fallback_duration=60)

        with caplog.at_level(logging.WARNING):
            manager.get(make_cache_key("x"))

        warning_logs = [
            r for r in caplog.records if r.levelname == "WARNING"
        ]
        assert any("fallback" in r.getMessage().lower() for r in warning_logs), (
            "Fallback activation must log a WARNING message"
        )
        assert any("redis" in r.getMessage().lower() for r in warning_logs), (
            "Warning should mention the primary backend failure reason"
        )

    def test_chart_data_service_with_fallback_manager(self) -> None:
        """Test ChartDataService correctly uses FallbackCacheManager."""

        class UnreliablePrimary(CacheBackend):
            """Mock backend that alternates success/failure."""

            def __init__(self) -> None:
                self._stats = CacheStats()
                self._call_count = 0

            def get(self, key: str):
                self._call_count += 1
                if self._call_count <= 2:
                    raise CacheBackendError("Unavailable")
                self._stats = self._stats.record_miss()
                return None

            def set(self, key: str, value, ttl=None):
                pass

            def ttl(self, key: str):
                return None

            def clear(self):
                pass

            @property
            def stats(self) -> CacheStats:
                return self._stats

            def reset_stats(self) -> None:
                pass

            @property
            def is_available(self) -> bool:
                return True

        unreliable = UnreliablePrimary()
        inmemory = InMemoryCacheBackend(default_ttl=300)
        manager = FallbackCacheManager(unreliable, inmemory, fallback_duration=60)

        service = ChartDataService(prices=None, options={}, cache_backend=manager)

        test_key = make_cache_key(
            "svc_test",
            time_window_start="2024-01-01",
            time_window_end="2024-02-01",
            currency="USD",
        )

        service.cache.set(test_key, {"balance": 100})
        result = service.cache.get(test_key)

        assert result == {"balance": 100}, (
            "Service must work through fallback when primary is down"
        )
        assert isinstance(service.cache, FallbackCacheManager)
        assert service.cache.stats.fallbacks >= 1


class TestConfigIntegration:
    """Tests for cache configuration integration with FavaOptions."""

    def test_from_options_cache_backend(self) -> None:
        """Test CacheConfig.from_options reads cache_backend."""
        options = {
            "cache_backend": "redis",
            "cache_default_ttl": 600,
            "cache_redis_url": "redis://cache.example.com:6379/7",
            "cache_redis_key_prefix": "prod:",
        }

        config = CacheConfig.from_options(options)

        assert config.backend_type == "redis"
        assert config.default_ttl == 600
        assert config.redis_url == "redis://cache.example.com:6379/7"
        assert config.redis_key_prefix == "prod:"

    def test_from_options_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that options override environment defaults."""
        monkeypatch.setenv("FAVA_CACHE_BACKEND", "inmemory")
        monkeypatch.setenv("FAVA_CACHE_TTL", "100")

        options = {
            "cache_backend": "redis",
            "cache_default_ttl": 900,
        }

        config = CacheConfig.from_options(options)

        assert config.backend_type == "redis", (
            "Options should override env for cache_backend"
        )
        assert config.default_ttl == 900, (
            "Options should override env for cache_default_ttl"
        )

    def test_from_options_none_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that None options falls through to environment defaults."""
        monkeypatch.setenv("FAVA_CACHE_BACKEND", "redis")
        monkeypatch.setenv("FAVA_CACHE_TTL", "42")

        config = CacheConfig.from_options(None)

        assert config.backend_type == "redis"
        assert config.default_ttl == 42


class TestBackendInterfaceCompliance:
    """Tests that all backends properly implement the CacheBackend interface."""

    def test_get_set_ttl_interface(
        self, inmemory_backend: CacheBackend
    ) -> None:
        """Test that backend implements get/set/ttl methods correctly."""
        key = make_cache_key(
            "iface_test",
            time_window_start="2024-01-01",
            currency="USD",
        )
        value = {"test": "data", "nested": {"x": 1}}

        inmemory_backend.set(key, value, ttl=100)
        assert inmemory_backend.get(key) == value

        remaining = inmemory_backend.ttl(key)
        assert remaining is not None
        assert isinstance(remaining, int)
        assert 0 < remaining <= 100

    def test_get_missing_returns_none(
        self, inmemory_backend: CacheBackend
    ) -> None:
        """Test that get() returns None for missing keys."""
        result = inmemory_backend.get(
            make_cache_key("nonexistent", time_window_start="2000-01-01")
        )
        assert result is None

    def test_clear_interface(
        self, inmemory_backend: CacheBackend
    ) -> None:
        """Test that clear() removes all entries."""
        k1 = make_cache_key("a", time_window_start="2024-01-01")
        k2 = make_cache_key("b", time_window_start="2024-01-01")
        inmemory_backend.set(k1, "v1")
        inmemory_backend.set(k2, "v2")

        assert inmemory_backend.get(k1) == "v1"
        assert inmemory_backend.get(k2) == "v2"

        inmemory_backend.clear()

        assert inmemory_backend.get(k1) is None
        assert inmemory_backend.get(k2) is None

    def test_stats_interface(
        self, inmemory_backend: CacheBackend
    ) -> None:
        """Test that stats interface works correctly."""
        inmemory_backend.reset_stats()
        stats = inmemory_backend.stats
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

        k1 = make_cache_key("hit_test", time_window_start="2024-01-01")
        inmemory_backend.set(k1, "hit")

        inmemory_backend.get(k1)
        inmemory_backend.get(make_cache_key("miss", time_window_start="2024-01-01"))

        stats = inmemory_backend.stats
        assert stats.hits == 1
        assert stats.misses == 1
        assert abs(stats.hit_rate - 0.5) < 0.001

    def test_is_available_interface(self) -> None:
        """Test that backends report availability correctly."""
        inmem = InMemoryCacheBackend(default_ttl=300)
        assert inmem.is_available is True

        from dataclasses import replace

        redis_backend = RedisCacheBackend(
            redis_url="redis://127.0.0.1:1/99",
            max_retries=1,
            retry_delay=0,
        )
        try:
            redis_backend.get("any_key")
        except (CacheBackendError, Exception):
            pass
        assert redis_backend.is_available is False
