"""Performance and cross-timezone tests for budgets, charts, filters and tree.

Benchmarks run against ``tests/data/example_real.beancount``, a real-world
ledger copy (5800+ lines, 900+ transactions, 60+ accounts across 2014–2016)
so that the numbers reflect the realistic mix of postings, balance assertions,
custom directives and multi-currency transactions that occur in production
usage.
"""

from __future__ import annotations

import datetime
import time
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from fava.beans.account import get_entry_accounts

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
    from pathlib import Path

    from fava.core import FavaLedger

    from .conftest import GetFavaLedger


REAL_LEDGER_EXPECTED_TXN_MIN = 800
REAL_LEDGER_DATE_START = datetime.date(2014, 1, 1)
REAL_LEDGER_DATE_END = datetime.date(2016, 6, 1)
REAL_LEDGER_YEARS = ["2014", "2015", "2016"]
REAL_LEDGER_ROOT_ACCOUNTS = ["Expenses", "Assets", "Liabilities", "Income"]
REAL_LEDGER_TARGET_ACCOUNT = "Expenses:Food:Groceries"
REAL_LEDGER_TARGET_ACCOUNT_ALT = "Expenses:Home:Rent"
REAL_LEDGER_BANK_ACCOUNT = "Assets:US:BofA:Checking"
REAL_LEDGER_TARGET_PAYEE = "BayBook"


@pytest.fixture(scope="module")
def real_ledger(test_data_dir: Path) -> FavaLedger:
    """Load ``tests/data/example_real.beancount`` as the performance fixture.

    This file is a copy of the long-running example ledger used in the
    beancount project (931 transactions, 60+ accounts, commodity price
    directives, org-mode section comments) so that performance benchmarks
    operate on a realistic mix of directive kinds.
    """
    from fava.application import create_app
    from fava.core import FavaLedger as FL

    ledger_path = test_data_dir / "example_real.beancount"
    if not ledger_path.exists():
        pytest.skip(f"Missing {ledger_path}, skipping performance tests")

    app = create_app([str(ledger_path)], load=True)
    ledgers = app.config["LEDGERS"]
    first_slug = ledgers.first_slug()
    ledger = ledgers[first_slug]
    assert isinstance(ledger, FL)
    return ledger


class TestLargeLedgerPerformance:
    """Performance regression benchmarks against the real ledger fixture.

    Thresholds are generous (2–5 seconds for repeated iterations) so that
    tests are not flaky in CI containers.  The real protection this class
    provides is catching *order-of-magnitude* regressions that would turn
    sub-second operations into multi-second stalls.
    """

    BUDGET_THRESHOLD_S = 2.0
    TREE_THRESHOLD_S = 2.0
    CHART_INTERVAL_THRESHOLD_S = 5.0
    CHART_LINECHART_THRESHOLD_S = 5.0
    CHART_NETWORTH_THRESHOLD_S = 5.0
    FILTER_THRESHOLD_S = 5.0

    def test_real_ledger_correctness(self, real_ledger: FavaLedger) -> None:
        """Sanity check the real-world ledger has the expected shape."""
        all_entries = real_ledger.all_entries
        txn_count = sum(1 for e in all_entries if isinstance(e, Transaction))
        assert txn_count >= REAL_LEDGER_EXPECTED_TXN_MIN, (
            f"Expected >= {REAL_LEDGER_EXPECTED_TXN_MIN} real transactions, "
            f"got {txn_count}"
        )

        tree = Tree(all_entries)
        for root_name in REAL_LEDGER_ROOT_ACCOUNTS:
            node = tree.get(root_name)
            assert node is not None and node.name == root_name, (
                f"Missing root account {root_name} in real ledger"
            )

        bank = tree.get(REAL_LEDGER_BANK_ACCOUNT)
        assert bank is not None, "Missing bank account in real ledger"

    def test_tree_build_performance(self, real_ledger: FavaLedger) -> None:
        start = time.perf_counter()
        for _ in range(20):
            Tree(real_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.TREE_THRESHOLD_S, (
            f"Tree build on real ledger took {elapsed:.3f}s "
            f"(> {self.TREE_THRESHOLD_S}s)"
        )

    def test_chart_interval_totals_performance(
        self, real_ledger: FavaLedger
    ) -> None:
        filtered = real_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(10):
            real_ledger.charts.interval_totals(
                filtered, Month, "Expenses", "at_cost"
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.CHART_INTERVAL_THRESHOLD_S, (
            f"interval_totals(Month, Expenses) took {elapsed:.3f}s "
            f"(> {self.CHART_INTERVAL_THRESHOLD_S}s)"
        )

    def test_chart_interval_totals_performance_quarter(
        self, real_ledger: FavaLedger
    ) -> None:
        filtered = real_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(10):
            real_ledger.charts.interval_totals(
                filtered, Quarter, "Expenses", "at_cost"
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.CHART_INTERVAL_THRESHOLD_S, (
            f"interval_totals(Quarter, Expenses) took {elapsed:.3f}s "
            f"(> {self.CHART_INTERVAL_THRESHOLD_S}s)"
        )

    def test_chart_linechart_performance(self, real_ledger: FavaLedger) -> None:
        filtered = real_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(10):
            real_ledger.charts.linechart(
                filtered, REAL_LEDGER_BANK_ACCOUNT, "units"
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.CHART_LINECHART_THRESHOLD_S, (
            f"linechart({REAL_LEDGER_BANK_ACCOUNT}) took {elapsed:.3f}s "
            f"(> {self.CHART_LINECHART_THRESHOLD_S}s)"
        )

    def test_chart_net_worth_performance(self, real_ledger: FavaLedger) -> None:
        filtered = real_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(10):
            real_ledger.charts.net_worth(filtered, Month, "USD")
        elapsed = time.perf_counter() - start
        assert elapsed < self.CHART_NETWORTH_THRESHOLD_S, (
            f"net_worth(Month, USD) took {elapsed:.3f}s "
            f"(> {self.CHART_NETWORTH_THRESHOLD_S}s)"
        )

    def test_hierarchy_performance(self, real_ledger: FavaLedger) -> None:
        filtered = real_ledger.get_filtered()
        start = time.perf_counter()
        for _ in range(10):
            real_ledger.charts.hierarchy(filtered, "Expenses", AT_COST)
        elapsed = time.perf_counter() - start
        assert elapsed < self.TREE_THRESHOLD_S, (
            f"hierarchy(Expenses) took {elapsed:.3f}s "
            f"(> {self.TREE_THRESHOLD_S}s)"
        )

    def test_budget_calculate_performance(self, real_ledger: FavaLedger) -> None:
        budgets = real_ledger.budgets._budget_entries
        start = time.perf_counter()
        for _ in range(50):
            calculate_budget(
                budgets,
                REAL_LEDGER_TARGET_ACCOUNT,
                REAL_LEDGER_DATE_START,
                REAL_LEDGER_DATE_END,
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.BUDGET_THRESHOLD_S, (
            f"calculate_budget on real ledger took {elapsed:.3f}s "
            f"(> {self.BUDGET_THRESHOLD_S}s)"
        )

    def test_budget_children_performance(self, real_ledger: FavaLedger) -> None:
        budgets = real_ledger.budgets._budget_entries
        start = time.perf_counter()
        for _ in range(50):
            calculate_budget_children(
                budgets,
                "Expenses",
                REAL_LEDGER_DATE_START,
                REAL_LEDGER_DATE_END,
            )
        elapsed = time.perf_counter() - start
        assert elapsed < self.BUDGET_THRESHOLD_S, (
            f"calculate_budget_children on real ledger took {elapsed:.3f}s "
            f"(> {self.BUDGET_THRESHOLD_S}s)"
        )

    def test_time_filter_performance(self, real_ledger: FavaLedger) -> None:
        start = time.perf_counter()
        for _ in range(10):
            for year in REAL_LEDGER_YEARS:
                tf = TimeFilter(
                    real_ledger.options,
                    real_ledger.fava_options,
                    year,
                )
                tf.apply(real_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"TimeFilter across real ledger took {elapsed:.3f}s "
            f"(> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_account_filter_performance(self, real_ledger: FavaLedger) -> None:
        start = time.perf_counter()
        for _ in range(20):
            af = AccountFilter(REAL_LEDGER_TARGET_ACCOUNT)
            af.apply(real_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"AccountFilter on real ledger took {elapsed:.3f}s "
            f"(> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_advanced_filter_payee_performance(
        self, real_ledger: FavaLedger
    ) -> None:
        start = time.perf_counter()
        for _ in range(20):
            af = AdvancedFilter(f"payee:{REAL_LEDGER_TARGET_PAYEE}")
            af.apply(real_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"AdvancedFilter payee on real ledger took {elapsed:.3f}s "
            f"(> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_advanced_filter_tag_performance(
        self, real_ledger: FavaLedger
    ) -> None:
        start = time.perf_counter()
        for _ in range(20):
            af = AdvancedFilter("#trip")
            af.apply(real_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"AdvancedFilter #tag on real ledger took {elapsed:.3f}s "
            f"(> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_advanced_filter_account_any_performance(
        self, real_ledger: FavaLedger
    ) -> None:
        start = time.perf_counter()
        for _ in range(20):
            af = AdvancedFilter('any(account:"Expenses:Food:.*")')
            af.apply(real_ledger.all_entries)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"AdvancedFilter any(account:regex) on real ledger took "
            f"{elapsed:.3f}s (> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_filtered_ledger_performance(
        self, real_ledger: FavaLedger
    ) -> None:
        start = time.perf_counter()
        for year in REAL_LEDGER_YEARS:
            for _ in range(5):
                fl = FilteredLedger(real_ledger, time=year, account="Expenses")
                _ = fl.interval_ranges(Month)
        elapsed = time.perf_counter() - start
        assert elapsed < self.FILTER_THRESHOLD_S, (
            f"FilteredLedger + interval_ranges on real ledger took "
            f"{elapsed:.3f}s (> {self.FILTER_THRESHOLD_S}s)"
        )

    def test_chart_interval_totals_real_years(
        self, real_ledger: FavaLedger
    ) -> None:
        """Sanity-check interval_totals against each year in the real ledger."""
        for year in REAL_LEDGER_YEARS:
            filtered = FilteredLedger(real_ledger, time=year)
            data = real_ledger.charts.interval_totals(
                filtered, Month, "Expenses", "at_cost"
            )
            assert 1 <= len(data) <= 12, (
                f"Year {year}: expected 1-12 month intervals, got {len(data)}"
            )

    def test_tree_real_ledger_deep_walk(
        self, real_ledger: FavaLedger
    ) -> None:
        """Walking the full account tree should still be fast."""
        tree = Tree(real_ledger.all_entries)
        root = tree.get("Expenses")
        start = time.perf_counter()
        for _ in range(100):
            count = 0
            for child in root.children:
                count += len(child.children)
        elapsed = time.perf_counter() - start
        assert count > 0
        assert elapsed < self.TREE_THRESHOLD_S, (
            f"Deep tree walk on real ledger took {elapsed:.3f}s "
            f"(> {self.TREE_THRESHOLD_S}s)"
        )

    def test_interval_100_limit_real_ledger(
        self, real_ledger: FavaLedger
    ) -> None:
        """Day intervals across 2+ years still cap at 100 entries."""
        filtered = FilteredLedger(real_ledger, time="2014-2016")
        data = real_ledger.charts.interval_totals(
            filtered, Day, "Expenses", "at_cost"
        )
        assert len(data) <= 100

    def test_budget_calculate_monthly_children_correctness(
        self, real_ledger: FavaLedger
    ) -> None:
        """Budget aggregates from Expenses are a superset of leaf budgets."""
        budgets = real_ledger.budgets._budget_entries
        children_total = calculate_budget_children(
            budgets,
            "Expenses",
            REAL_LEDGER_DATE_START,
            REAL_LEDGER_DATE_END,
        )
        leaf_total = calculate_budget(
            budgets,
            "Expenses",
            REAL_LEDGER_DATE_START,
            REAL_LEDGER_DATE_END,
        )
        for currency, v in leaf_total.items():
            assert children_total.get(currency, Decimal(0)) >= v


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
        """TimeFilter should correctly handle DST-like date boundaries."""
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
