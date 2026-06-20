"""Internal API.

This is used to pre-process some data that is used in the templates, allowing
this part of the functionality to be tested and allowing some end-to-end tests
for the frontend data validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from flask import current_app
from flask import url_for
from flask_babel import gettext

from fava.context import g
from fava.core import charts
from fava.core.conversion import conversion_from_str
from fava.util.excel import HAVE_EXCEL

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence
    from typing import Literal

    from fava.beans.abc import Meta
    from fava.beans.abc import Query
    from fava.core.accounts import AccountDict
    from fava.core.charts import DateAndBalance
    from fava.core.charts import DateAndBalanceWithBudget
    from fava.core.conversion import Conversion
    from fava.core.extensions import ExtensionDetails
    from fava.core.fava_options import FavaOptions
    from fava.core.tree import SerialisedTreeNode
    from fava.helpers import BeancountError
    from fava.util.date import Interval


@dataclass(frozen=True)
class SerialisedError:
    """A Beancount error, as passed to the frontend."""

    type: str
    source: Meta | None
    message: str

    @staticmethod
    def from_beancount_error(err: BeancountError) -> SerialisedError:
        """Get a serialisable error from a Beancount error."""
        source = dict(err.source) if err.source is not None else None
        if source is not None:
            source.pop("__tolerances__", None)
        return SerialisedError(err.__class__.__name__, source, err.message)


@dataclass(frozen=True)
class LedgerData:
    """This is used as report-independent data in the frontend."""

    accounts: Sequence[str]
    account_details: AccountDict
    base_url: str
    currencies: Sequence[str]
    currency_names: dict[str, str]
    errors: Sequence[SerialisedError]
    fava_options: FavaOptions
    incognito: bool
    have_excel: bool
    links: Sequence[str]
    options: dict[str, str | Sequence[str]]
    payees: Sequence[str]
    precisions: dict[str, int]
    tags: Sequence[str]
    years: Sequence[str]
    user_queries: Sequence[Query]
    upcoming_events_count: int
    extensions: Sequence[ExtensionDetails]
    sidebar_links: Sequence[tuple[str, str]]
    other_ledgers: Sequence[tuple[str, str]]


def get_errors() -> list[SerialisedError]:
    """Serialise errors (do not pass entry as that might fail serialisation."""
    return [SerialisedError.from_beancount_error(e) for e in g.ledger.errors]


def _get_options() -> dict[str, str | Sequence[str]]:
    options = g.ledger.options
    return {
        "documents": options["documents"],
        "filename": options["filename"],
        "include": options["include"],
        "operating_currency": options["operating_currency"],
        "title": options["title"],
        "name_assets": options["name_assets"],
        "name_liabilities": options["name_liabilities"],
        "name_equity": options["name_equity"],
        "name_income": options["name_income"],
        "name_expenses": options["name_expenses"],
    }


def get_ledger_data() -> LedgerData:
    """Get the report-independent ledger data."""
    ledger = g.ledger
    all_queries = ledger.all_entries_by_type.Query

    return LedgerData(
        ledger.attributes.accounts,
        ledger.accounts,
        url_for("index"),
        ledger.attributes.currencies,
        ledger.commodities.names,
        get_errors(),
        ledger.fava_options,
        current_app.config["INCOGNITO"],
        HAVE_EXCEL,
        ledger.attributes.links,
        _get_options(),
        ledger.attributes.payees,
        ledger.format_decimal.precisions,
        ledger.attributes.tags,
        ledger.attributes.years,
        all_queries[: ledger.fava_options.sidebar_show_queries],
        len(ledger.misc.upcoming_events),
        ledger.extensions.extension_details,
        ledger.misc.sidebar_links,
        [
            (ledger.options["title"], url_for("index", bfile=file_slug))
            for (file_slug, ledger) in current_app.config["LEDGERS"].items()
            if file_slug != g.beancount_file_slug
        ],
    )


@dataclass(frozen=True)
class BalancesChart:
    """Data for a balances chart."""

    label: str
    data: Sequence[DateAndBalance]
    type: Literal["balances"] = "balances"


@dataclass(frozen=True)
class BarChart:
    """Data for a bar chart."""

    label: str
    data: Sequence[DateAndBalanceWithBudget]
    type: Literal["bar"] = "bar"


@dataclass(frozen=True)
class HierarchyChart:
    """Data for a hierarchy chart."""

    label: str
    data: SerialisedTreeNode
    type: Literal["hierarchy"] = "hierarchy"


if TYPE_CHECKING:  # pragma: no cover
    ChartData = BalancesChart | BarChart | HierarchyChart


class ChartDataLoader:
    """Load raw chart data from the ledger with caching.

    This class is responsible for fetching data from the ledger's chart
    functions. It depends on the Flask request context (via ``g``) for
    retrieving the current ledger state, but delegates the actual data
    generation to pure functions in :mod:`fava.core.charts`.

    Results are cached using the ledger's content hash as part of the
    cache key, so cached data is automatically invalidated when any
    ledger file (including includes) changes.

    The cache maxsize defaults to 2x the ledger's
    ``ledger_cache_maxsize`` option (since chart queries tend to be
    more numerous than filtered-ledger lookups).
    """

    _DEFAULT_CHART_CACHE_MAXSIZE: int = 32
    _MIN_CHART_CACHE_MAXSIZE: int = 1
    _MAX_CHART_CACHE_MAXSIZE: int = 8192

    @staticmethod
    def _chart_cache_maxsize() -> int:
        """Get the chart cache maxsize from the ledger config.

        The value is clamped to a safe range [1, 8192] to prevent
        misconfiguration from disabling the cache entirely or causing
        excessive memory use.
        """
        try:
            from fava.context import g

            base = max(
                g.ledger.fava_options.ledger_cache_maxsize * 2,
                ChartDataLoader._DEFAULT_CHART_CACHE_MAXSIZE,
            )
            return max(
                ChartDataLoader._MIN_CHART_CACHE_MAXSIZE,
                min(base, ChartDataLoader._MAX_CHART_CACHE_MAXSIZE),
            )
        except RuntimeError:  # pragma: no cover
            return ChartDataLoader._DEFAULT_CHART_CACHE_MAXSIZE

    @staticmethod
    def _filter_key() -> tuple[str, str, str]:
        """Get a hashable key for the current filtered ledger.

        Directly reads filter parameters from the Flask request args,
        which is the authoritative source for how the current filtered
        ledger was constructed.
        """
        from flask import request

        return (
            request.args.get("account", ""),
            request.args.get("filter", ""),
            request.args.get("time", ""),
        )

    @staticmethod
    def _content_hash() -> int:
        """Get a hash that changes when any ledger content changes.

        Combines the watcher's ``last_checked`` and ``last_notified``
        timestamps. ``last_notified`` is updated immediately when a file
        change is reported (e.g. via editor save), even before the full
        ledger reload has completed. This ensures the chart cache
        invalidates promptly when any watched file (including ``include``
        sub-files) changes, not just the main ledger file.
        """
        from fava.context import g

        return max(
            g.ledger.watcher.last_checked,
            g.ledger.watcher.last_notified,
        )

    @staticmethod
    @lru_cache(maxsize=32)
    def _cached_linechart(
        mtime: int,
        filter_key: tuple[str, str, str],
        account_name: str,
        conversion_str: str,
    ) -> Sequence[DateAndBalance]:
        """Cached linechart data generation."""
        _ = filter_key  # passed for cache invalidation
        return charts.linechart(
            g.filtered,
            account_name,
            conversion_str,
            g.ledger.prices,
        )

    @staticmethod
    def account_balance(account_name: str) -> Sequence[DateAndBalance]:
        """Load data for an account balances chart."""
        return ChartDataLoader._cached_linechart(
            ChartDataLoader._content_hash(),
            ChartDataLoader._filter_key(),
            account_name,
            str(g.conv),
        )

    @staticmethod
    @lru_cache(maxsize=32)
    def _cached_hierarchy(
        mtime: int,
        filter_key: tuple[str, str, str],
        account_name: str,
        conversion_str: str,
    ) -> SerialisedTreeNode:
        """Cached hierarchy data generation."""
        _ = filter_key  # passed for cache invalidation
        return charts.hierarchy(
            g.filtered,
            account_name,
            conversion_from_str(conversion_str),
            g.ledger.prices,
        )

    @staticmethod
    def hierarchy(account_name: str) -> SerialisedTreeNode:
        """Load data for an account hierarchy chart."""
        return ChartDataLoader._cached_hierarchy(
            ChartDataLoader._content_hash(),
            ChartDataLoader._filter_key(),
            account_name,
            str(g.conv),
        )

    @staticmethod
    @lru_cache(maxsize=32)
    def _cached_interval_totals(
        mtime: int,
        filter_key: tuple[str, str, str],
        interval: Interval,
        accounts: str | tuple[str, ...],
        conversion_str: str,
        invert: bool,
    ) -> Sequence[DateAndBalanceWithBudget]:
        """Cached interval totals data generation."""
        _ = filter_key  # passed for cache invalidation
        return charts.interval_totals(
            g.filtered,
            interval,
            accounts,
            conversion_str,
            g.ledger.prices,
            g.ledger.budgets.calculate_children
            if isinstance(accounts, str)
            else None,
            invert=invert,
        )

    @staticmethod
    def interval_totals(
        interval: Interval,
        accounts: str | tuple[str, ...],
        conversion: str | Conversion | None = None,
        *,
        invert: bool = False,
    ) -> Sequence[DateAndBalanceWithBudget]:
        """Load data for an account per interval chart."""
        conv_str = str(conversion or g.conv)
        return ChartDataLoader._cached_interval_totals(
            ChartDataLoader._content_hash(),
            ChartDataLoader._filter_key(),
            interval,
            accounts,
            conv_str,
            invert,
        )

    @staticmethod
    @lru_cache(maxsize=32)
    def _cached_net_worth(
        mtime: int,
        filter_key: tuple[str, str, str],
        interval: Interval,
        conversion_str: str,
    ) -> Sequence[DateAndBalance]:
        """Cached net worth data generation."""
        _ = filter_key  # passed for cache invalidation
        return charts.net_worth(
            g.filtered,
            interval,
            conversion_str,
            g.ledger.prices,
            (
                g.ledger.options["name_assets"],
                g.ledger.options["name_liabilities"],
            ),
        )

    @staticmethod
    def net_worth() -> Sequence[DateAndBalance]:
        """Load data for net worth chart."""
        return ChartDataLoader._cached_net_worth(
            ChartDataLoader._content_hash(),
            ChartDataLoader._filter_key(),
            g.interval,
            str(g.conv),
        )

    @classmethod
    def rebuild_cache(cls) -> None:
        """Rebuild all cached methods with the current maxsize config.

        Call this after the ledger config has been loaded and the
        ``ledger_cache_maxsize`` option might have changed.
        """
        maxsize = cls._chart_cache_maxsize()
        cls._cached_linechart = lru_cache(maxsize=maxsize)(
            cls._cached_linechart.__wrapped__,
        )
        cls._cached_hierarchy = lru_cache(maxsize=maxsize)(
            cls._cached_hierarchy.__wrapped__,
        )
        cls._cached_interval_totals = lru_cache(maxsize=maxsize)(
            cls._cached_interval_totals.__wrapped__,
        )
        cls._cached_net_worth = lru_cache(maxsize=maxsize)(
            cls._cached_net_worth.__wrapped__,
        )

    @staticmethod
    def clear_cache() -> None:
        """Clear all cached chart data."""
        ChartDataLoader._cached_linechart.cache_clear()
        ChartDataLoader._cached_hierarchy.cache_clear()
        ChartDataLoader._cached_interval_totals.cache_clear()
        ChartDataLoader._cached_net_worth.cache_clear()


class ChartApi:
    """Build chart data structures from pre-loaded data.

    This class only focuses on data structure construction and has no
    dependency on the Flask request context.
    """

    @staticmethod
    def account_balance(data: Sequence[DateAndBalance]) -> ChartData:
        """Build a balances chart from pre-loaded data."""
        return BalancesChart(gettext("Account Balance"), data)

    @staticmethod
    def hierarchy(
        data: SerialisedTreeNode,
        *,
        label: str | None = None,
    ) -> ChartData:
        """Build a hierarchy chart from pre-loaded data."""
        return HierarchyChart(label or data.account, data)

    @staticmethod
    def interval_totals(
        data: Sequence[DateAndBalanceWithBudget],
        *,
        label: str | None = None,
        account_name: str | tuple[str, ...] | None = None,
    ) -> ChartData:
        """Build a bar chart from pre-loaded data."""
        return BarChart(label or str(account_name or ""), data)

    @staticmethod
    def net_worth(data: Sequence[DateAndBalance]) -> ChartData:
        """Build a net worth chart from pre-loaded data."""
        return BalancesChart(gettext("Net Worth"), data)
