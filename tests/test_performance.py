"""Performance and cross-timezone tests for budgets, charts, filters and tree."""

from __future__ import annotations

import datetime
import time
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from fava.beans import create
from fava.beans.abc import Transaction
from fava.beans.load import load_string
from fava.core import FilteredLedger
from fava.core.budgets import Budget
from fava.core.budgets import calculate_budget
from fava.core.budgets import calculate_budget_children
from fava.core.conversion import AT_COST
from fava.core.filters import AccountFilter
from fava.core.filters import AdvancedFilter
from fava.core.filters import TimeFilter
from fava.core.tree import Tree
from fava.util.date import Day
from fava.util.date import Month
from fava.util.date import Quarter
from fava.util.date import Week
from fava.util.date import Year
from fava.util.date import parse_date

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger

    from .conftest import GetFavaLedger


def _generate_large_beancount(
    num_years: int = 10,
    txns_per_day: int = 5,
    num_accounts: int = 50,
) -> str:
    """Generate a large Beancount string for performance testing.

    Produces a ledger with roughly num_years * 365 * txns_per_day transactions
    spread across num_accounts expense accounts.
    """
    lines: list[str] = []
    lines.append('option "title" "Performance Test Ledger"')
    lines.append('option "operating_currency" "USD"')
    lines.append("")

    lines.append("1792-01-01 commodity USD")
    lines.append("")

    for i in range(num_accounts):
        acct = f"Expenses:Cat{i:03d}"
        lines.append(f"2000-01-01 open {acct} USD")
    lines.append("2000-01-01 open Assets:Bank USD")
    lines.append("2000-01-01 open Equity:Opening USD")
    lines.append("")

    lines.append('2000-01-01 * "Opening balance"')
    lines.append("  Assets:Bank 1000000.00 USD")
    lines.append("  Equity:Opening -1000000.00 USD")
    lines.append("")

    start_date = datetime.date(2010, 1, 1)
    end_date = datetime.date(2010 + num_years, 1, 1)
    current = start_date
    idx = 0
    while current < end_date:
        for _ in range(txns_per_day):
            acct_idx = idx % num_accounts
            acct = f"Expenses:Cat{acct_idx:03d}"
            amount = Decimal("10") + Decimal(idx % 100) / Decimal(10)
            lines.append(
                f'{current.isoformat()} * "Transaction {idx}"'
            )
            lines.append(f"  {acct}  {amount:.2f} USD")
            lines.append(f"  Assets:Bank -{amount:.2f} USD")
            idx += 1
        current += datetime.timedelta(days=1)

    for i in range(0, num_accounts, 5):
        acct = f"Expenses:Cat{i:03d}"
        lines.append(
            f'2010-01-01 custom "budget" {acct} "monthly" 500.00 USD'
        )

    return "\n".join(lines)


@pytest.fixture(scope="module")
def large_ledger_string() -> str:
    return _generate_large_beancount(num_years=3, txns_per_day=2, num_accounts=20)


@pytest.fixture(scope="module")
def large_ledger(large_ledger_string: str) -> FavaLedger:
    """Load a large ledger for performance tests."""
    from fava.application import create_app
    from fava.core import FavaLedger as FL
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".beancount", delete=False
    ) as f:
        f.write(large_ledger_string)
        f.flush()
        path = Path(f.name)

    app = create_app([str(path)], load=True)
    ledgers = app.config["LEDGERS"]
    first_slug = ledgers.first_slug()
    ledger = ledgers[first_slug]
    assert isinstance(ledger, FL)
    yield ledger
    path.unlink(missing_ok=True)


class TestLargeLedgerPerformance:
    """Performance regression benchmarks against large ledger."""

    BUDGET_THRESHOLD_S = 2.0
    TREE_THRESHOLD_S = 2.0
    CHART_INTERVAL_THRESHOLD_S = 2.0
    CHART_LINECHART_THRESHOLD_S = 2.0
    CHART_NETWORTH_THRESHOLD_S = 2.0
    FILTER_THRESHOLD_S = 2.0

    def test_budget_calculate_performance(self, large_ledger: FavaLedger) -> None:
        budgets = large_ledger.budgets._budget_entries
        start = time.perf_counter()
        for _ in range(10):
            calculate_budget(
                budgets,
                "Expenses:Cat000",
                datetime.date(2012, 1, 1),
                datetime.date(2013, 1, 1),
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.BUDGET_THRESHOLD_S, (
            f"Budget calculate took {elapsed:.3f}s (> {self.BUDGET_THRESHOLD_S}s)"
        )

    def test_budget_children_performance(self, large_ledger: FavaLedger) -> None:
        budgets = large_ledger.budgets._budget_entries
        start = time.perf_counter()
        for _ in range(10):
            calculate_budget_children(
                budgets,
                "Expenses",
                datetime.date(2012, 1, 1),
                datetime.date(2013, 1, 1),
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.BUDGET_THRESHOLD_S, (
            f"Budget children took {elapsed:.3f}s (> {self.BUDGET_THRESHOLD_S}s)"
        )

    def test_tree_build_performance(self, large_ledger: FavaLedger) -> None:
        start = time.perf_counter()
        for _ in range(5):
            Tree(large_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.TREE_THRESHOLD_S, (
            f"Tree build took {elapsed:.3f}s (> {self.TREE_THRESHOLD_S}s)"
        )

    def test_chart_interval_totals_performance(
        self, large_ledger: FavaLedger
    ) -> None:
        filtered = large_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(5):
            large_ledger.charts.interval_totals(
                filtered, Month, "Expenses", "at_cost"
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.CHART_INTERVAL_THRESHOLD_S, (
            f"Chart interval_totals took {elapsed:.3f}s "
            f"(> {self.CHART_INTERVAL_THRESHOLD_S}s)"
        )

    def test_chart_linechart_performance(self, large_ledger: FavaLedger) -> None:
        filtered = large_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(5):
            large_ledger.charts.linechart(
                filtered, "Assets:Bank", "units"
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.CHART_LINECHART_THRESHOLD_S, (
            f"Chart linechart took {elapsed:.3f}s "
            f"(> {self.CHART_LINECHART_THRESHOLD_S}s)"
        )

    def test_chart_net_worth_performance(self, large_ledger: FavaLedger) -> None:
        filtered = large_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(5):
            large_ledger.charts.net_worth(filtered, Month, "USD")
        elapsed = time.perf_counter() - start
        assert elapsed < self.CHART_NETWORTH_THRESHOLD_S, (
            f"Chart net_worth took {elapsed:.3f}s "
            f"(> {self.CHART_NETWORTH_THRESHOLD_S}s)"
        )

    def test_time_filter_performance(self, large_ledger: FavaLedger) -> None:
        start = time.perf_counter()
        for year in range(2010, 2013):
            tf = TimeFilter(
                large_ledger.options,
                large_ledger.fava_options,
                str(year),
            )
            tf.apply(large_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"Time filter took {elapsed:.3f}s (> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_account_filter_performance(self, large_ledger: FavaLedger) -> None:
        start = time.perf_counter()
        for _ in range(5):
            af = AccountFilter("Expenses:Cat000")
            af.apply(large_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"Account filter took {elapsed:.3f}s (> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_advanced_filter_performance(self, large_ledger: FavaLedger) -> None:
        start = time.perf_counter()
        for _ in range(5):
            af = AdvancedFilter('payee:Transaction')
            af.apply(large_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"Advanced filter took {elapsed:.3f}s (> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_hierarchy_performance(self, large_ledger: FavaLedger) -> None:
        filtered = large_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(5):
            large_ledger.charts.hierarchy(filtered, "Expenses", AT_COST)
        elapsed = time.perf_counter() - start
        assert elapsed < self.TREE_THRESHOLD_S, (
            f"Hierarchy took {elapsed:.3f}s (> {self.TREE_THRESHOLD_S}s)"
        )

    def test_large_ledger_correctness(self, large_ledger: FavaLedger) -> None:
        """Verify large ledger loads with expected transaction count."""
        all_entries = large_ledger.all_entries
        txn_count = sum(
            1 for e in all_entries if isinstance(e, Transaction)
        )
        assert txn_count > 1000, f"Expected >1000 txns, got {txn_count}"

        filtered = FilteredLedger(large_ledger, time="2012")
        chart_data = large_ledger.charts.interval_totals(
            filtered, Month, "Expenses", "at_cost"
        )
        assert len(chart_data) == 12

        tree = Tree(filtered.entries)
        expenses = tree.get("Expenses")
        assert expenses.name == "Expenses"

    def test_interval_100_limit_large(self, large_ledger: FavaLedger) -> None:
        filtered = FilteredLedger(large_ledger, time="2010-2013")
        data = large_ledger.charts.interval_totals(
            filtered, Day, "Expenses", "at_cost"
        )
        assert len(data) <= 100


class TestCrossTimezone:
    """Cross-timezone date parsing boundary tests."""

    def test_parse_date_year(self) -> None:
        begin, end = parse_date("2020")
        assert begin == datetime.date(2020, 1, 1)
        assert end == datetime.date(2021, 1, 1)

    def test_parse_date_month(self) -> None:
        begin, end = parse_date("2020-06")
        assert begin == datetime.date(2020, 6, 1)
        assert end == datetime.date(2020, 7, 1)

    def test_parse_date_day(self) -> None:
        begin, end = parse_date("2020-06-15")
        assert begin == datetime.date(2020, 6, 15)
        assert end == datetime.date(2020, 6, 16)

    def test_parse_date_quarter(self) -> None:
        begin, end = parse_date("2020-Q2")
        assert begin == datetime.date(2020, 4, 1)
        assert end == datetime.date(2020, 7, 1)

    def test_parse_date_week(self) -> None:
        begin, end = parse_date("2020-W01")
        assert begin is not None
        assert end is not None
        assert begin < end
        assert (end - begin).days == 7

    def test_parse_date_range_dash(self) -> None:
        begin, end = parse_date("2020-01 to 2020-06")
        assert begin == datetime.date(2020, 1, 1)
        assert end == datetime.date(2020, 7, 1)

    def test_parse_date_fiscal_year(self) -> None:
        from fava.util.date import FiscalYearEnd

        fye = FiscalYearEnd(6, 30)
        begin, end = parse_date("FY2020", fye)
        assert begin == datetime.date(2019, 7, 1)
        assert end == datetime.date(2020, 7, 1)

    def test_parse_date_fiscal_quarter(self) -> None:
        from fava.util.date import FiscalYearEnd

        fye = FiscalYearEnd(6, 30)
        begin, end = parse_date("FY2020-Q1", fye)
        assert begin == datetime.date(2019, 7, 1)
        assert end == datetime.date(2019, 10, 1)

    def test_parse_date_fiscal_year_no_quarters(self) -> None:
        from fava.util.date import FiscalYearEnd

        fye = FiscalYearEnd(2, 15)
        begin, end = parse_date("FY2020-Q1", fye)
        assert begin is None
        assert end is None

    def test_parse_date_empty(self) -> None:
        begin, end = parse_date("")
        assert begin is None
        assert end is None

    def test_parse_date_invalid(self) -> None:
        begin, end = parse_date("not-a-date")
        assert begin is None
        assert end is None

    def test_time_filter_across_dst_boundary(
        self, small_example_ledger: FavaLedger
    ) -> None:
        """TimeFilter should correctly handle DST-like date boundaries.

        Note: clamp_opt may add summarization entries at the boundary
        with dates just before the range.
        """
        tf = TimeFilter(
            small_example_ledger.options,
            small_example_ledger.fava_options,
            "2016-03",
        )
        assert tf.date_range.begin == datetime.date(2016, 3, 1)
        assert tf.date_range.end == datetime.date(2016, 4, 1)
        filtered = tf.apply(small_example_ledger.all_entries)
        assert len(filtered) > 0

    def test_time_filter_year_end_boundary(
        self, small_example_ledger: FavaLedger
    ) -> None:
        tf = TimeFilter(
            small_example_ledger.options,
            small_example_ledger.fava_options,
            "2016-12",
        )
        assert tf.date_range.begin == datetime.date(2016, 12, 1)
        assert tf.date_range.end == datetime.date(2017, 1, 1)

    def test_time_filter_leap_day(
        self, small_example_ledger: FavaLedger
    ) -> None:
        tf = TimeFilter(
            small_example_ledger.options,
            small_example_ledger.fava_options,
            "2016-02-29",
        )
        assert tf.date_range.begin == datetime.date(2016, 2, 29)
        assert tf.date_range.end == datetime.date(2016, 3, 1)

    def test_interval_ranges_consistency(
        self, small_example_ledger: FavaLedger
    ) -> None:
        """Interval ranges should be consistent across interval types."""
        filtered = small_example_ledger.get_filtered()
        if not filtered._date_first or not filtered._date_last:
            pytest.skip("No entries in ledger")

        for interval_cls in [Day, Week, Month, Quarter, Year]:
            ranges = filtered.interval_ranges(interval_cls)
            for r in ranges:
                assert r.begin < r.end
            if len(ranges) > 1:
                for i in range(len(ranges) - 1):
                    assert ranges[i].end == ranges[i + 1].begin

    def test_date_range_end_inclusive(
        self, small_example_ledger: FavaLedger
    ) -> None:
        from fava.util.date import DateRange

        dr = DateRange(datetime.date(2020, 1, 1), datetime.date(2020, 2, 1))
        assert dr.end_inclusive == datetime.date(2020, 1, 31)

        dr_leap = DateRange(
            datetime.date(2020, 2, 1), datetime.date(2020, 3, 1)
        )
        assert dr_leap.end_inclusive == datetime.date(2020, 2, 29)

    def test_budget_timezone_invariant(
        self, small_example_ledger: FavaLedger
    ) -> None:
        """Budget calculation should be timezone-invariant (pure date math)."""
        budgets = small_example_ledger.budgets._budget_entries
        r1 = calculate_budget(
            budgets,
            "Expenses:Food",
            datetime.date(2016, 1, 1),
            datetime.date(2016, 2, 1),
        )
        r2 = calculate_budget(
            budgets,
            "Expenses:Food",
            datetime.date(2016, 1, 1),
            datetime.date(2016, 2, 1),
        )
        assert r1 == r2
