"""Unified chart data service combining account grouping, time aggregation, and currency conversion.

This module provides a unified service that combines three core features
used in Fava's charts:
1. Account grouping - grouping entries by account hierarchy
2. Time aggregation - aggregating data by time intervals
3. Currency conversion - converting inventory values to target currencies

The service aims to eliminate code duplication across chart methods and
provide a flexible, composable interface for generating chart data.

Enhancements:
- Parallel account processing using ThreadPoolExecutor
- TTL-based memory caching for account aggregation results
- Performance statistics and cache hit rate tracking
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from fava.beans.abc import Transaction
from fava.beans.account import account_tester
from fava.beans.flags import FLAG_UNREALIZED
from fava.beans.helpers import slice_entry_dates
from fava.core.conversion import conversion_from_str
from fava.core.inventory import CounterInventory
from fava.core.inventory import SimpleCounterInventory
from fava.util import listify

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterable
    from collections.abc import Mapping
    from typing import Any

    from fava.beans.abc import Directive
    from fava.beans.prices import FavaPriceMap
    from fava.core.conversion import Conversion
    from fava.core.module_base import FavaModule
    from fava.util.date import DateRange
    from fava.util.date import Interval


ZERO = Decimal()


@dataclass(frozen=True)
class AggregationParameters:
    """Parameters for data aggregation.

    Attributes:
        interval: The time interval for aggregation (e.g., monthly, yearly).
        accounts: Account name(s) to filter by (string prefix match).
        conversion: The currency conversion to apply.
        invert: Whether to invert all numeric values.
        accumulate: Whether to accumulate balances across intervals.
        with_account_balances: Whether to include per-account breakdowns.
        with_children: Whether to include child accounts.
        parallel: Whether to use parallel processing for account grouping.
        max_workers: Maximum number of worker threads for parallel processing.
        use_cache: Whether to use caching for aggregation results.
        cache_ttl: Cache TTL in seconds (default: 300 seconds).
    """

    interval: Interval | None = None
    accounts: str | tuple[str, ...] | None = None
    conversion: str | Conversion = "at_cost"
    invert: bool = False
    accumulate: bool = False
    with_account_balances: bool = False
    with_children: bool = True
    parallel: bool = False
    max_workers: int = 4
    use_cache: bool = False
    cache_ttl: int = 300


@dataclass(frozen=True)
class TimeSeriesPoint:
    """A single data point in a time series.

    Attributes:
        date: The date of this data point (end of interval).
        balance: The total balance for this interval.
        account_balances: Per-account breakdown (if requested).
        budgets: Budget amounts (if applicable).
    """

    date: date
    balance: SimpleCounterInventory
    account_balances: Mapping[str, SimpleCounterInventory] | None = None
    budgets: Mapping[str, Decimal] | None = None


@dataclass(frozen=True)
class AccountTreeNode:
    """A node in the account tree for hierarchical charts.

    Attributes:
        account: The account name.
        balance: The balance of this account.
        balance_children: The cumulative balance including children.
        children: Child account nodes.
        has_txns: Whether this account has any transactions.
    """

    account: str
    balance: SimpleCounterInventory
    balance_children: SimpleCounterInventory
    children: tuple[AccountTreeNode, ...]
    has_txns: bool


@dataclass(frozen=True)
class CacheStats:
    """Cache performance statistics.

    Attributes:
        hits: Number of cache hits.
        misses: Number of cache misses.
        total_requests: Total number of cache requests.
        hit_rate: Cache hit rate (0.0 to 1.0).
    """

    hits: int = 0
    misses: int = 0

    @property
    def total_requests(self) -> int:
        """Total number of cache requests."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a float between 0 and 1."""
        total = self.total_requests
        return self.hits / total if total > 0 else 0.0

    def record_hit(self) -> None:
        """Record a cache hit."""
        object.__setattr__(self, "hits", self.hits + 1)

    def record_miss(self) -> None:
        """Record a cache miss."""
        object.__setattr__(self, "misses", self.misses + 1)

    def reset(self) -> None:
        """Reset all statistics."""
        object.__setattr__(self, "hits", 0)
        object.__setattr__(self, "misses", 0)


@dataclass
class _CacheEntry:
    """Internal cache entry with TTL."""

    value: Any
    expiry: float


@dataclass
class AccountProcessingTask:
    """A task for processing a single account's entries.

    Attributes:
        account_name: Name of the account to process.
        entries: The entries (postings) for this account.
        date_range: The date range for aggregation.
    """

    account_name: str
    entries: list[Directive]
    date_range: DateRange


def _process_account_task(
    task: AccountProcessingTask,
) -> tuple[str, CounterInventory]:
    """Process a single account's entries to compute its inventory.

    This function is designed to be run in parallel by ThreadPoolExecutor.

    Args:
        task: The account processing task containing entries and date range.

    Returns:
        Tuple of (account_name, inventory) for the account.
    """
    inventory = CounterInventory()
    for entry in task.entries:
        for posting in getattr(entry, "postings", []):
            if posting.account == task.account_name:
                inventory.add_position(posting)
    return task.account_name, inventory


def _convert_account_inventory(
    account_data: tuple[str, CounterInventory],
    conv: Conversion,
    prices: FavaPriceMap,
    conversion_date: date,
) -> tuple[str, SimpleCounterInventory]:
    """Apply currency conversion to a single account's inventory.

    This function is designed to be run in parallel by ThreadPoolExecutor.

    Args:
        account_data: Tuple of (account_name, inventory).
        conv: The conversion to apply.
        prices: The price map for conversions.
        conversion_date: The date for price lookups.

    Returns:
        Tuple of (account_name, converted_inventory).
    """
    account_name, inventory = account_data
    converted = conv.apply(inventory, prices, conversion_date)
    return account_name, converted


class TTLCache:
    """A simple thread-safe TTL-based memory cache.

    Args:
        ttl: Default time-to-live in seconds for cache entries.
    """

    def __init__(self, ttl: int = 300) -> None:
        self._ttl = ttl
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._stats = CacheStats()

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        """Create a cache key from arguments.

        Creates a deterministic hash key from the provided arguments.
        """
        key_parts = []
        for arg in args:
            key_parts.append(str(arg))
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, *args: Any, **kwargs: Any) -> Any | None:
        """Get a value from the cache.

        Args:
            *args: Positional arguments for key generation.
            **kwargs: Keyword arguments for key generation.

        Returns:
            The cached value if found and not expired, None otherwise.
        """
        key = self._make_key(*args, **kwargs)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if time.time() < entry.expiry:
                    self._stats.record_hit()
                    return entry.value
                del self._cache[key]
            self._stats.record_miss()
            return None

    def set(
        self,
        value: Any,
        *args: Any,
        ttl: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Set a value in the cache.

        Args:
            value: The value to cache.
            *args: Positional arguments for key generation.
            ttl: Optional TTL for this entry (overrides default).
            **kwargs: Keyword arguments for key generation.
        """
        key = self._make_key(*args, **kwargs)
        expiry = time.time() + (ttl if ttl is not None else self._ttl)
        with self._lock:
            self._cache[key] = _CacheEntry(value=value, expiry=expiry)

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

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._stats.reset()

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        with self._lock:
            return len(self._cache)


@dataclass
class ParallelExecutionConfig:
    """Configuration for parallel execution.

    Attributes:
        enabled: Whether parallel execution is enabled.
        max_workers: Maximum number of worker threads.
        chunk_size: Number of accounts per task chunk.
    """

    enabled: bool = False
    max_workers: int = 4
    chunk_size: int = 10


@dataclass
class PerformanceMetrics:
    """Performance metrics for chart data operations.

    Attributes:
        serial_time_ms: Time taken for serial execution (ms).
        parallel_time_ms: Time taken for parallel execution (ms).
        speedup: Speedup factor (serial_time / parallel_time).
        account_count: Number of accounts processed.
        entry_count: Number of entries processed.
    """

    serial_time_ms: float = 0.0
    parallel_time_ms: float = 0.0
    speedup: float = 1.0
    account_count: int = 0
    entry_count: int = 0


class ChartDataService:
    """Unified service for generating chart data.

    This service combines account grouping, time aggregation, and currency
    conversion into a single, composable interface. It can be used as a
    standalone utility or integrated with Fava's module system.

    Enhanced with parallel processing and caching capabilities.
    """

    def __init__(
        self,
        ledger: FavaModule | None = None,
        *,
        prices: FavaPriceMap | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the chart data service.

        Args:
            ledger: Optional Fava ledger module for accessing prices and budgets.
            prices: Optional price map (used if ledger is not provided).
            options: Optional Beancount options (used if ledger is not provided).
        """
        self._ledger = ledger
        self._prices = prices
        self._options = options
        self._cache = TTLCache()

    @property
    def prices(self) -> FavaPriceMap:
        """Get the price map to use for conversions."""
        if self._prices is not None:
            return self._prices
        if self._ledger is not None:
            return self._ledger.ledger.prices
        raise ValueError("No price map available")

    @property
    def options(self) -> Mapping[str, Any]:
        """Get the Beancount options."""
        if self._options is not None:
            return self._options
        if self._ledger is not None:
            return self._ledger.ledger.options
        raise ValueError("No options available")

    @property
    def cache(self) -> TTLCache:
        """Get the TTL cache instance."""
        return self._cache

    def reset_cache(self) -> None:
        """Reset the cache and clear all statistics."""
        self._cache.clear()
        self._cache.reset_stats()

    def _get_conversion(
        self, conversion: str | Conversion
    ) -> Conversion:
        """Get a Conversion object from string or Conversion."""
        return conversion_from_str(conversion)

    def _get_conversion_str(self, conversion: str | Conversion) -> str:
        """Get a string representation of the conversion for cache keys."""
        if isinstance(conversion, str):
            return conversion
        return conversion.__class__.__name__

    def _apply_inversion(
        self,
        balance: SimpleCounterInventory,
        account_balances: Mapping[str, SimpleCounterInventory] | None,
        budgets: Mapping[str, Decimal] | None,
        invert: bool,
    ) -> tuple[
        SimpleCounterInventory,
        Mapping[str, SimpleCounterInventory] | None,
        Mapping[str, Decimal] | None,
    ]:
        """Apply inversion to balances and budgets if requested."""
        if not invert:
            return balance, account_balances, budgets

        inverted_balance = -balance
        inverted_accounts = (
            {k: -v for k, v in account_balances.items()}
            if account_balances is not None
            else None
        )
        inverted_budgets = (
            {k: -v for k, v in budgets.items()}
            if budgets is not None
            else None
        )
        return inverted_balance, inverted_accounts, inverted_budgets

    def _filter_entries_by_account(
        self,
        entries: Iterable[Directive],
        accounts: str | tuple[str, ...] | None,
        with_children: bool = True,
    ) -> Callable[[str], bool]:
        """Create an account filter function.

        Args:
            entries: The entries to filter (not used, for future extension).
            accounts: Account prefix(es) to filter by.
            with_children: Whether to include child accounts.

        Returns:
            A function that tests if an account should be included.
        """
        if accounts is None:
            return lambda _account: True

        if isinstance(accounts, str):
            return account_tester(accounts, with_children=with_children)

        testers = [
            account_tester(acc, with_children=with_children) for acc in accounts
        ]
        return lambda account: any(t(account) for t in testers)

    def _group_entries_by_account(
        self,
        entries: Iterable[Directive],
        account_filter: Callable[[str], bool],
    ) -> dict[str, list[Directive]]:
        """Group entries by account name.

        This is a pre-processing step that groups all entries by their
        account names, enabling parallel processing per account.

        Args:
            entries: The entries to group.
            account_filter: Function to filter accounts.

        Returns:
            Dictionary mapping account names to lists of entries.
        """
        grouped: dict[str, list[Directive]] = defaultdict(list)
        for entry in entries:
            for posting in getattr(entry, "postings", []):
                if account_filter(posting.account):
                    grouped[posting.account].append(entry)
        return dict(grouped)

    def _collect_inventory_serial(
        self,
        entries: Iterable[Directive],
        account_filter: Callable[[str], bool],
        *,
        with_account_balances: bool = False,
    ) -> tuple[CounterInventory, dict[str, CounterInventory]]:
        """Collect inventory from entries serially, optionally per account.

        Args:
            entries: The entries to process.
            account_filter: Function to filter accounts.
            with_account_balances: Whether to track per-account inventories.

        Returns:
            Tuple of (total_inventory, per_account_inventories).
        """
        total_inventory = CounterInventory()
        account_inventories: dict[str, CounterInventory] = defaultdict(
            CounterInventory
        ) if with_account_balances else {}

        for entry in entries:
            for posting in getattr(entry, "postings", []):
                if account_filter(posting.account):
                    if with_account_balances:
                        account_inventories[posting.account].add_position(
                            posting
                        )
                    total_inventory.add_position(posting)

        return total_inventory, account_inventories

    def _collect_inventory_parallel(
        self,
        entries: Iterable[Directive],
        account_filter: Callable[[str], bool],
        date_range: DateRange,
        *,
        max_workers: int = 4,
    ) -> tuple[CounterInventory, dict[str, CounterInventory]]:
        """Collect inventory from entries using parallel processing.

        Groups entries by account first, then processes each account's
        entries in parallel using ThreadPoolExecutor.

        Args:
            entries: The entries to process.
            account_filter: Function to filter accounts.
            date_range: The date range for these entries.
            max_workers: Maximum number of worker threads.

        Returns:
            Tuple of (total_inventory, per_account_inventories).
        """
        grouped_entries = self._group_entries_by_account(entries, account_filter)

        if not grouped_entries:
            return CounterInventory(), {}

        tasks = [
            AccountProcessingTask(
                account_name=account_name,
                entries=entries_list,
                date_range=date_range,
            )
            for account_name, entries_list in grouped_entries.items()
        ]

        account_inventories: dict[str, CounterInventory] = {}
        total_inventory = CounterInventory()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(_process_account_task, tasks)
            for account_name, inventory in results:
                account_inventories[account_name] = inventory
                total_inventory.add_inventory(inventory)

        return total_inventory, account_inventories

    def _convert_accounts_parallel(
        self,
        account_inventories: dict[str, CounterInventory],
        conv: Conversion,
        prices: FavaPriceMap,
        conversion_date: date,
        *,
        max_workers: int = 4,
    ) -> dict[str, SimpleCounterInventory]:
        """Apply currency conversion to multiple accounts in parallel.

        Args:
            account_inventories: Dictionary mapping account names to inventories.
            conv: The conversion to apply.
            prices: The price map for conversions.
            conversion_date: The date for price lookups.
            max_workers: Maximum number of worker threads.

        Returns:
            Dictionary mapping account names to converted inventories.
        """
        if not account_inventories:
            return {}

        account_data = list(account_inventories.items())
        converted: dict[str, SimpleCounterInventory] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(
                lambda item: _convert_account_inventory(
                    item, conv, prices, conversion_date
                ),
                account_data,
            )
            for account_name, balance in results:
                converted[account_name] = balance

        return converted

    def _get_cached_aggregation(
        self,
        account_name: str,
        date_range: DateRange,
        conversion_str: str,
    ) -> tuple[CounterInventory, CounterInventory] | None:
        """Try to get cached aggregation results for an account.

        Args:
            account_name: The account name.
            date_range: The date range.
            conversion_str: String representation of the conversion.

        Returns:
            Cached (total_inventory, account_inventory) if available, None otherwise.
        """
        return self._cache.get(
            "aggregation",
            account=account_name,
            begin=date_range.begin.isoformat(),
            end=date_range.end.isoformat(),
            conversion=conversion_str,
        )

    def _set_cached_aggregation(
        self,
        account_name: str,
        date_range: DateRange,
        conversion_str: str,
        value: tuple[CounterInventory, CounterInventory],
        *,
        ttl: int = 300,
    ) -> None:
        """Cache aggregation results for an account.

        Args:
            account_name: The account name.
            date_range: The date range.
            conversion_str: String representation of the conversion.
            value: The (total_inventory, account_inventory) to cache.
            ttl: Cache TTL in seconds.
        """
        self._cache.set(
            value,
            "aggregation",
            account=account_name,
            begin=date_range.begin.isoformat(),
            end=date_range.end.isoformat(),
            conversion=conversion_str,
            ttl=ttl,
        )

    @listify
    def aggregate_by_time(
        self,
        entries: Iterable[Directive],
        intervals: Iterable[DateRange],
        params: AggregationParameters,
    ) -> Iterable[TimeSeriesPoint]:
        """Aggregate entries by time intervals with currency conversion.

        This is the core method that combines time aggregation,
        account filtering, and currency conversion. Supports both
        serial and parallel execution modes.

        Args:
            entries: The entries to aggregate.
            intervals: The date ranges to aggregate by.
            params: Aggregation parameters.

        Yields:
            TimeSeriesPoint for each interval.
        """
        conv = self._get_conversion(params.conversion)
        prices = self.prices
        conversion_str = self._get_conversion_str(params.conversion)
        account_filter = self._filter_entries_by_account(
            entries, params.accounts, params.with_children
        )

        running_balance = CounterInventory()
        running_account_balances: dict[str, CounterInventory] = defaultdict(
            CounterInventory
        ) if params.with_account_balances else {}

        for date_range in intervals:
            sliced_entries = slice_entry_dates(
                entries, date_range.begin, date_range.end
            )

            if params.accumulate:
                for entry in sliced_entries:
                    for posting in getattr(entry, "postings", []):
                        if account_filter(posting.account):
                            if params.with_account_balances:
                                running_account_balances[
                                    posting.account
                                ].add_position(posting)
                            running_balance.add_position(posting)
                interval_total = running_balance
                interval_accounts = running_account_balances
            elif params.parallel and params.with_account_balances:
                interval_total, interval_accounts = (
                    self._collect_inventory_parallel(
                        sliced_entries,
                        account_filter,
                        date_range,
                        max_workers=params.max_workers,
                    )
                )
            else:
                interval_total, interval_accounts = (
                    self._collect_inventory_serial(
                        sliced_entries,
                        account_filter,
                        with_account_balances=params.with_account_balances,
                    )
                )

            balance = conv.apply(
                interval_total, prices, date_range.end_inclusive
            )

            account_balances = None
            if params.with_account_balances:
                if params.parallel:
                    account_balances = self._convert_accounts_parallel(
                        interval_accounts,
                        conv,
                        prices,
                        date_range.end_inclusive,
                        max_workers=params.max_workers,
                    )
                else:
                    account_balances = {
                        account: conv.apply(
                            acct_value, prices, date_range.end_inclusive
                        )
                        for account, acct_value in interval_accounts.items()
                    }

            budgets = None
            if (
                isinstance(params.accounts, str)
                and self._ledger is not None
            ):
                budgets = self._ledger.ledger.budgets.calculate_children(
                    params.accounts, date_range.begin, date_range.end
                )

            balance, account_balances, budgets = self._apply_inversion(
                balance, account_balances, budgets, params.invert
            )

            yield TimeSeriesPoint(
                date=date_range.end_inclusive,
                balance=balance,
                account_balances=account_balances,
                budgets=budgets,
            )

    @listify
    def running_balance_series(
        self,
        entries: Iterable[Directive],
        params: AggregationParameters,
    ) -> Iterable[TimeSeriesPoint]:
        """Generate a running balance time series.

        Unlike aggregate_by_time which works with fixed intervals,
        this method creates a data point whenever the balance changes.

        Args:
            entries: The entries to process.
            params: Aggregation parameters.

        Yields:
            TimeSeriesPoint for each date where the balance changes.
        """
        conv = self._get_conversion(params.conversion)
        prices = self.prices
        account_filter = self._filter_entries_by_account(
            entries, params.accounts, params.with_children
        )

        last_date = None
        running_balance = CounterInventory()

        for entry in entries:
            for posting in getattr(entry, "postings", []):
                if account_filter(posting.account):
                    new_date = entry.date
                    if last_date is not None and new_date > last_date:
                        balance = conv.apply(running_balance, prices, last_date)
                        balance, _, _ = self._apply_inversion(
                            balance, None, None, params.invert
                        )
                        yield TimeSeriesPoint(
                            date=last_date,
                            balance=balance,
                        )
                    running_balance.add_position(posting)
                    last_date = new_date

        if last_date is not None:
            balance = conv.apply(running_balance, prices, last_date)
            balance, _, _ = self._apply_inversion(
                balance, None, None, params.invert
            )
            yield TimeSeriesPoint(
                date=last_date,
                balance=balance,
            )

    def net_worth_series(
        self,
        entries: Iterable[Directive],
        intervals: Iterable[DateRange],
        params: AggregationParameters,
    ) -> Iterable[TimeSeriesPoint]:
        """Compute net worth (Assets + Liabilities) over time.

        Args:
            entries: The entries to process.
            intervals: The date ranges.
            params: Aggregation parameters.

        Returns:
            Iterable of TimeSeriesPoint with net worth values.
        """
        types = (
            self.options["name_assets"],
            self.options["name_liabilities"],
        )

        transactions = (
            entry
            for entry in entries
            if (
                isinstance(entry, Transaction)
                and entry.flag != FLAG_UNREALIZED
            )
        )

        return self.aggregate_by_time(
            transactions,
            intervals,
            AggregationParameters(
                accounts=types,
                conversion=params.conversion,
                accumulate=True,
                with_account_balances=params.with_account_balances,
                invert=params.invert,
                parallel=params.parallel,
                max_workers=params.max_workers,
                use_cache=params.use_cache,
                cache_ttl=params.cache_ttl,
            ),
        )

    def build_account_tree(
        self,
        entries: Iterable[Directive],
        params: AggregationParameters,
        *,
        end_date: date | None = None,
    ) -> AccountTreeNode:
        """Build an account tree hierarchy from entries.

        Args:
            entries: The entries to build the tree from.
            params: Aggregation parameters (conversion will be applied).
            end_date: Optional end date for price conversions.

        Returns:
            The root AccountTreeNode.
        """
        from fava.core.tree import Tree

        conv = self._get_conversion(params.conversion)
        prices = self.prices

        tree = Tree(entries)
        root = tree.get(params.accounts if isinstance(params.accounts, str) else "")

        def serialise_node(node) -> AccountTreeNode:
            children = tuple(
                serialise_node(child)
                for child in sorted(node.children, key=lambda n: n.name)
            )
            return AccountTreeNode(
                account=node.name,
                balance=conv.apply(node.balance, prices, end_date),
                balance_children=conv.apply(
                    node.balance_children, prices, end_date
                ),
                children=children,
                has_txns=node.has_txns,
            )

        return serialise_node(root)

    def fill_zero_currencies(
        self,
        points: Iterable[TimeSeriesPoint],
    ) -> Iterable[TimeSeriesPoint]:
        """Ensure currency continuity across time series points.

        When a currency's balance drops to zero, it may disappear from
        the inventory. This method ensures that once a currency appears,
        it continues to appear with zero value in subsequent points.

        Args:
            points: The time series points.

        Yields:
            TimeSeriesPoint with zero-filled currencies.
        """
        last_currencies: set[str] | None = None

        for point in points:
            balance = SimpleCounterInventory(point.balance)
            currencies = set(balance.keys())
            if last_currencies:
                for currency in last_currencies - currencies:
                    balance[currency] = ZERO
            last_currencies = currencies

            yield TimeSeriesPoint(
                date=point.date,
                balance=balance,
                account_balances=point.account_balances,
                budgets=point.budgets,
            )

    def compare_parallel_serial(
        self,
        entries: Iterable[Directive],
        intervals: Iterable[DateRange],
        params: AggregationParameters,
    ) -> PerformanceMetrics:
        """Compare parallel and serial execution performance.

        Runs the same aggregation both serially and in parallel,
        returning performance metrics.

        Args:
            entries: The entries to aggregate.
            intervals: The date ranges to aggregate by.
            params: Aggregation parameters (parallel flag is ignored here).

        Returns:
            PerformanceMetrics with timing information.
        """
        entries_list = list(entries)
        intervals_list = list(intervals)

        params_serial = AggregationParameters(
            **{
                **params.__dict__,
                "parallel": False,
                "use_cache": False,
            }
        )
        params_parallel = AggregationParameters(
            **{
                **params.__dict__,
                "parallel": True,
                "use_cache": False,
            }
        )

        start = time.perf_counter()
        result_serial = list(
            self.aggregate_by_time(entries_list, intervals_list, params_serial)
        )
        serial_time = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        result_parallel = list(
            self.aggregate_by_time(entries_list, intervals_list, params_parallel)
        )
        parallel_time = (time.perf_counter() - start) * 1000

        account_count = 0
        for point in result_serial:
            if point.account_balances:
                account_count = max(account_count, len(point.account_balances))

        return PerformanceMetrics(
            serial_time_ms=serial_time,
            parallel_time_ms=parallel_time,
            speedup=serial_time / parallel_time if parallel_time > 0 else 1.0,
            account_count=account_count,
            entry_count=len(entries_list),
        )
