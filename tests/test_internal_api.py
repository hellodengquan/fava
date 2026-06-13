"""Tests for Fava's main Flask app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fava.core import ReportContext
from fava.internal_api import BalancesChart
from fava.internal_api import BarChart
from fava.internal_api import ChartApi
from fava.internal_api import get_ledger_data
from fava.internal_api import HierarchyChart

if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask

    from .conftest import SnapshotFunc


def test_get_ledger_data(app: Flask, snapshot: SnapshotFunc) -> None:
    """The currently filtered journal can be downloaded."""
    with app.test_request_context("/long-example/"):
        app.preprocess_request()
        snapshot(get_ledger_data(), json=True)


def test_chart_api(app: Flask, snapshot: SnapshotFunc) -> None:
    """The serialisation and generation of charts works."""
    with app.test_request_context("/long-example/"):
        app.preprocess_request()

        hierarchy = ChartApi.hierarchy("Assets")
        assert isinstance(hierarchy, HierarchyChart)
        assert hierarchy.data.account == "Assets"
        assert hierarchy.label == "Assets"
        assert hierarchy.type == "hierarchy"

        balances = ChartApi.account_balance("Assets:US:Vanguard:Cash")
        assert isinstance(balances, BalancesChart)
        assert len(balances.data) == 117
        assert balances.label == "Account Balance"
        assert balances.type == "balances"

        net_worth = ChartApi.net_worth()
        assert isinstance(net_worth, BalancesChart)
        assert len(net_worth.data) == 197
        assert net_worth.label == "Net Worth"
        assert net_worth.type == "balances"

        interval_totals = ChartApi.interval_totals("Income")
        assert isinstance(interval_totals, BarChart)
        assert len(interval_totals.data) == 100
        assert interval_totals.label == "Income"
        assert interval_totals.type == "bar"

        snapshot(
            [hierarchy, balances, net_worth, interval_totals],
            json=True,
        )


def test_chart_api_with_context(app: Flask, snapshot: SnapshotFunc) -> None:
    """Chart API works with explicit ReportContext."""
    with app.test_request_context("/long-example/"):
        app.preprocess_request()

        ctx_year = ReportContext(interval="year")
        interval_totals_year = ChartApi.interval_totals(
            "Income", context=ctx_year
        )
        assert isinstance(interval_totals_year, BarChart)
        assert interval_totals_year.type == "bar"

        ctx_quarter = ReportContext(interval="quarter")
        interval_totals_quarter = ChartApi.interval_totals(
            "Income", context=ctx_quarter
        )
        assert isinstance(interval_totals_quarter, BarChart)

        assert len(interval_totals_year.data) != len(
            interval_totals_quarter.data
        )
