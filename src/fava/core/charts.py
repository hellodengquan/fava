"""Provide data suitable for Fava's charts."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields
from dataclasses import is_dataclass
from datetime import date
from decimal import Decimal
from re import Pattern
from typing import Any
from typing import TYPE_CHECKING

from beancount.core.amount import Amount
from beancount.core.data import Booking
from beancount.core.number import MISSING
from flask.json.provider import JSONProvider
from simplejson import dumps as simplejson_dumps
from simplejson import loads as simplejson_loads

from fava.beans.abc import Position
from fava.core.chart_data_service import AggregationParameters
from fava.core.chart_data_service import ChartDataService
from fava.core.module_base import FavaModule
from fava.util import listify

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable
    from collections.abc import Mapping

    from fava.core import FilteredLedger
    from fava.core.conversion import Conversion
    from fava.core.inventory import SimpleCounterInventory
    from fava.core.tree import SerialisedTreeNode
    from fava.util.date import Interval


ZERO = Decimal()


def _json_default(o: Any) -> Any:
    """Specific serialisation for some data types."""
    if isinstance(o, (date, Amount, Booking, Position)):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return list(o)
    if isinstance(o, Pattern):
        return o.pattern
    if is_dataclass(o):
        return {field.name: getattr(o, field.name) for field in fields(o)}
    if o is MISSING:  # pragma: no cover
        return None
    raise TypeError  # pragma: no cover


def dumps(obj: Any, **_kwargs: Any) -> str:
    """Dump as a JSON string."""
    return simplejson_dumps(
        obj, sort_keys=True, separators=(",", ":"), default=_json_default
    )


def loads(s: str | bytes) -> Any:
    """Load a JSON string."""
    return simplejson_loads(s)


class FavaJSONProvider(JSONProvider):
    """Use custom JSON encoder and decoder."""

    def dumps(self, obj: Any, **_kwargs: Any) -> str:  # noqa: D102
        return simplejson_dumps(
            obj, sort_keys=True, separators=(",", ":"), default=_json_default
        )

    def loads(self, s: str | bytes, **_kwargs: Any) -> Any:  # noqa: D102
        return simplejson_loads(s)


@dataclass(frozen=True)
class DateAndBalance:
    """Balance at a date."""

    date: date
    balance: SimpleCounterInventory


@dataclass(frozen=True)
class DateAndBalanceWithBudget:
    """Balance at a date with a budget."""

    date: date
    balance: SimpleCounterInventory
    account_balances: Mapping[str, SimpleCounterInventory]
    budgets: Mapping[str, Decimal]


class ChartModule(FavaModule):
    """Return data for the various charts in Fava."""

    def hierarchy(
        self,
        filtered: FilteredLedger,
        account_name: str,
        conversion: Conversion,
    ) -> SerialisedTreeNode:
        """Render an account tree."""
        tree = filtered.root_tree
        return tree.get(account_name).serialise(
            conversion, self.ledger.prices, filtered.end_date
        )

    @listify
    def interval_totals(
        self,
        filtered: FilteredLedger,
        interval: Interval,
        accounts: str | tuple[str, ...],
        conversion: str | Conversion,
        *,
        invert: bool = False,
    ) -> Iterable[DateAndBalanceWithBudget]:
        """Render totals for account (or accounts) in the intervals.

        Args:
            filtered: The filtered ledger.
            interval: An interval.
            accounts: A single account (str) or a tuple of accounts.
            conversion: The conversion to use.
            invert: invert all numbers.

        Yields:
            The balances and budgets for the intervals.
        """
        service = ChartDataService(self)
        intervals = filtered.interval_ranges(interval)[-100:]

        params = AggregationParameters(
            accounts=accounts,
            conversion=conversion,
            invert=invert,
            accumulate=False,
            with_account_balances=True,
        )

        for point in service.aggregate_by_time(
            filtered.entries, intervals, params
        ):
            yield DateAndBalanceWithBudget(
                date=point.date,
                balance=point.balance,
                account_balances=point.account_balances or {},
                budgets=point.budgets or {},
            )

    @listify
    def linechart(
        self,
        filtered: FilteredLedger,
        account_name: str,
        conversion: str | Conversion,
    ) -> Iterable[DateAndBalance]:
        """Get the balance of an account as a line chart.

        Args:
            filtered: The filtered ledger.
            account_name: A string.
            conversion: The conversion to use.

        Yields:
            Dicts for all dates on which the balance of the given
            account has changed containing the balance (in units) of the
            account at that date.
        """
        service = ChartDataService(self)

        params = AggregationParameters(
            accounts=account_name,
            conversion=conversion,
            with_children=True,
        )

        points = service.running_balance_series(filtered.entries, params)
        points = service.fill_zero_currencies(points)

        for point in points:
            yield DateAndBalance(point.date, point.balance)

    @listify
    def net_worth(
        self,
        filtered: FilteredLedger,
        interval: Interval,
        conversion: str | Conversion,
    ) -> Iterable[DateAndBalance]:
        """Compute net worth.

        Args:
            filtered: The filtered ledger.
            interval: A string for the interval.
            conversion: The conversion to use.

        Yields:
            Dicts for all ends of the given interval containing the
            net worth (Assets + Liabilities) separately converted to all
            operating currencies.
        """
        service = ChartDataService(self)
        intervals = filtered.interval_ranges(interval)

        params = AggregationParameters(
            conversion=conversion,
            accumulate=True,
        )

        for point in service.net_worth_series(
            filtered.entries, intervals, params
        ):
            yield DateAndBalance(point.date, point.balance)
