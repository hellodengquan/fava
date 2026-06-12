"""Unified chart data service combining account grouping, time aggregation, and currency conversion.

This module provides a unified service that combines three core features
used in Fava's charts:
1. Account grouping - grouping entries by account hierarchy
2. Time aggregation - aggregating data by time intervals
3. Currency conversion - converting inventory values to target currencies

The service aims to eliminate code duplication across chart methods and
provide a flexible, composable interface for generating chart data.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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
    """

    interval: Interval | None = None
    accounts: str | tuple[str, ...] | None = None
    conversion: str | Conversion = "at_cost"
    invert: bool = False
    accumulate: bool = False
    with_account_balances: bool = False
    with_children: bool = True


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


class ChartDataService:
    """Unified service for generating chart data.

    This service combines account grouping, time aggregation, and currency
    conversion into a single, composable interface. It can be used as a
    standalone utility or integrated with Fava's module system.
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

    def _get_conversion(
        self, conversion: str | Conversion
    ) -> Conversion:
        """Get a Conversion object from string or Conversion."""
        return conversion_from_str(conversion)

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

    def _collect_inventory(
        self,
        entries: Iterable[Directive],
        account_filter: Callable[[str], bool],
        *,
        with_account_balances: bool = False,
    ) -> tuple[CounterInventory, dict[str, CounterInventory]]:
        """Collect inventory from entries, optionally per account.

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

    @listify
    def aggregate_by_time(
        self,
        entries: Iterable[Directive],
        intervals: Iterable[DateRange],
        params: AggregationParameters,
    ) -> Iterable[TimeSeriesPoint]:
        """Aggregate entries by time intervals with currency conversion.

        This is the core method that combines time aggregation,
        account filtering, and currency conversion.

        Args:
            entries: The entries to aggregate.
            intervals: The date ranges to aggregate by.
            params: Aggregation parameters.

        Yields:
            TimeSeriesPoint for each interval.
        """
        conv = self._get_conversion(params.conversion)
        prices = self.prices
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
            else:
                interval_total, interval_accounts = self._collect_inventory(
                    sliced_entries,
                    account_filter,
                    with_account_balances=params.with_account_balances,
                )

            balance = conv.apply(
                interval_total, prices, date_range.end_inclusive
            )

            account_balances = None
            if params.with_account_balances:
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
