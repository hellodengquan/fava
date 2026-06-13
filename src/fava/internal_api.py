"""Internal API.

This is used to pre-process some data that is used in the templates, allowing
this part of the functionality to be tested and allowing some end-to-end tests
for the frontend data validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import current_app
from flask import url_for
from flask_babel import gettext

from fava.context import g
from fava.core import ReportContext
from fava.util.excel import HAVE_EXCEL

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence
    from typing import Literal

    from fava.beans.abc import Meta
    from fava.beans.abc import Query
    from fava.core.accounts import AccountDict
    from fava.core.charts import DateAndBalance
    from fava.core.charts import DateAndBalanceWithBudget
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


class ChartApi:
    """Functions to generate chart data.

    All chart generation methods should use the same ReportContext as the
    corresponding table data to ensure consistency. The context provides
    a single source of truth for all filtering parameters (time, account,
    filter, conversion, interval).
    """

    @staticmethod
    def account_balance(
        account_name: str,
        *,
        context: ReportContext | None = None,
    ) -> ChartData:
        """Generate data for an account balances chart.

        Args:
            account_name: The account to generate balance data for.
            context: Optional ReportContext to use. If not provided,
                uses the current request context.
        """
        ctx = context or g.report_context
        filtered = ctx.create_filtered_ledger(g.ledger)
        return BalancesChart(
            gettext("Account Balance"),
            g.ledger.charts.linechart(
                filtered,
                account_name,
                ctx.parsed_conversion,
            ),
        )

    @staticmethod
    def hierarchy(
        account_name: str,
        *,
        label: str | None = None,
        context: ReportContext | None = None,
    ) -> ChartData:
        """Generate data for an account hierarchy chart.

        Args:
            account_name: The root account for the hierarchy.
            label: Optional label for the chart.
            context: Optional ReportContext to use. If not provided,
                uses the current request context.
        """
        ctx = context or g.report_context
        filtered = ctx.create_filtered_ledger(g.ledger)
        return HierarchyChart(
            label or account_name,
            g.ledger.charts.hierarchy(
                filtered,
                account_name,
                ctx.parsed_conversion,
            ),
        )

    @staticmethod
    def interval_totals(
        account_name: str | tuple[str, ...],
        label: str | None = None,
        *,
        invert: bool = False,
        context: ReportContext | None = None,
    ) -> ChartData:
        """Generate data for an account per interval chart.

        The interval is automatically derived from the context, ensuring
        consistency with the table data.

        Args:
            account_name: The account(s) to generate totals for.
            label: Optional label for the chart.
            invert: Whether to invert the values.
            context: Optional ReportContext to use. If not provided,
                uses the current request context.
        """
        ctx = context or g.report_context
        filtered = ctx.create_filtered_ledger(g.ledger)
        return BarChart(
            label or str(account_name),
            g.ledger.charts.interval_totals(
                filtered,
                ctx.parsed_interval,
                account_name,
                ctx.parsed_conversion,
                invert=invert,
            ),
        )

    @staticmethod
    def net_worth(
        *,
        context: ReportContext | None = None,
    ) -> ChartData:
        """Generate data for net worth chart.

        Args:
            context: Optional ReportContext to use. If not provided,
                uses the current request context.
        """
        ctx = context or g.report_context
        filtered = ctx.create_filtered_ledger(g.ledger)
        return BalancesChart(
            gettext("Net Worth"),
            g.ledger.charts.net_worth(
                filtered, ctx.parsed_interval, ctx.parsed_conversion
            ),
        )
