"""Combined tests for budgets, filters, charts and tree interactions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from fava.core import FilteredLedger
from fava.core.budgets import calculate_budget
from fava.core.budgets import calculate_budget_children
from fava.core.budgets import parse_budgets
from fava.core.conversion import AT_COST
from fava.core.filters import AccountFilter
from fava.core.filters import AdvancedFilter
from fava.core.filters import TimeFilter
from fava.core.tree import Tree
from fava.util.date import Day
from fava.util.date import Month
from fava.util.date import Week
from fava.util.date import Year

if TYPE_CHECKING:  # pragma: no cover
    from fava.beans.abc import Custom
    from fava.core import FavaLedger
    from fava.core.budgets import BudgetDict

    from .conftest import GetFavaLedger
    from .conftest import SnapshotFunc


def test_budget_with_time_filter_combination(
    small_example_ledger: FavaLedger,
) -> None:
    """Test budget calculation combined with time filter."""
    budgets_doc = small_example_ledger.budgets._budget_entries

    time_filter = TimeFilter(
        small_example_ledger.options,
        small_example_ledger.fava_options,
        "2016-06",
    )

    budget = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        time_filter.date_range.begin,
        time_filter.date_range.end,
    )
    assert isinstance(budget, dict)


def test_budget_with_account_filter_combination(
    small_example_ledger: FavaLedger,
) -> None:
    """Test budget calculation combined with account filter."""
    budgets_doc = small_example_ledger.budgets._budget_entries

    account_filter = AccountFilter("Expenses:Food")
    filtered_entries = account_filter.apply(small_example_ledger.all_entries)

    assert len(filtered_entries) <= len(small_example_ledger.all_entries)

    budget = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2016, 1, 1),
        date(2016, 12, 31),
    )
    assert isinstance(budget, dict)


def test_tree_with_budget_combination(
    small_example_ledger: FavaLedger,
) -> None:
    """Test account tree combined with budget calculation."""
    filtered = FilteredLedger(small_example_ledger, time="2016")
    tree = Tree(filtered.entries)

    budgets_doc = small_example_ledger.budgets._budget_entries

    budget = calculate_budget_children(
        budgets_doc,
        "Expenses",
        date(2016, 1, 1),
        date(2017, 1, 1),
    )

    expenses_node = tree.get("Expenses")
    assert expenses_node.name == "Expenses"
    assert isinstance(budget, dict)


def test_charts_with_time_filter_boundary(
    small_example_ledger: FavaLedger,
) -> None:
    """Test chart data with time filter at year boundaries."""
    for year in ["2015", "2016", "2017"]:
        filtered = FilteredLedger(small_example_ledger, time=year)
        data = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            "at_cost",
        )
        assert len(data) <= 12

        for item in data:
            assert item.date.year == int(year)


def test_charts_with_multiple_filters(
    small_example_ledger: FavaLedger,
) -> None:
    """Test chart data with multiple filters combined."""
    filtered = FilteredLedger(
        small_example_ledger,
        time="2016",
        account="Expenses:Food",
    )

    data = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        "Expenses:Food",
        "at_cost",
    )

    assert len(data) > 0
    for item in data:
        assert item.date.year == 2016


def test_tree_with_time_filter_boundary(
    small_example_ledger: FavaLedger,
) -> None:
    """Test account tree with time filter at month boundaries."""
    time_filter = TimeFilter(
        small_example_ledger.options,
        small_example_ledger.fava_options,
        "2016-02",
    )
    filtered_entries = time_filter.apply(small_example_ledger.all_entries)

    tree = Tree(filtered_entries)
    root = tree.get("")

    assert root.name == ""
    assert len(root.children) > 0


def test_budget_cross_year_boundary(
    load_doc_custom_entries: list[Custom],
) -> None:
    """
    2016-01-01 custom "budget" Expenses:Books "yearly" 365.00 EUR"""
    budgets, _ = parse_budgets(load_doc_custom_entries)

    result = calculate_budget(
        budgets,
        "Expenses:Books",
        date(2016, 12, 31),
        date(2017, 1, 2),
    )

    assert "EUR" in result
    expected_2016 = Decimal(365) / 366
    expected_2017 = Decimal(365) / 365
    assert abs(result["EUR"] - (expected_2016 + expected_2017)) < Decimal("0.01")


def test_budget_cross_month_boundary(
    load_doc_custom_entries: list[Custom],
) -> None:
    """
    2016-01-01 custom "budget" Expenses:Books "monthly" 310.00 EUR"""
    budgets, _ = parse_budgets(load_doc_custom_entries)

    result = calculate_budget(
        budgets,
        "Expenses:Books",
        date(2016, 1, 31),
        date(2016, 2, 2),
    )

    assert "EUR" in result
    jan_day = Decimal(310) / 31
    feb_day = Decimal(310) / 29
    assert result["EUR"] == jan_day + feb_day


def test_budget_cross_quarter_boundary(
    load_doc_custom_entries: list[Custom],
) -> None:
    """
    2016-01-01 custom "budget" Expenses:Books "quarterly" 91.00 EUR"""
    budgets, _ = parse_budgets(load_doc_custom_entries)

    result = calculate_budget(
        budgets,
        "Expenses:Books",
        date(2016, 3, 31),
        date(2016, 4, 2),
    )

    assert "EUR" in result
    q1_day = Decimal(91) / 91
    q2_day = Decimal(91) / 91
    assert result["EUR"] == q1_day + q2_day


def test_filtered_ledger_interval_boundaries(
    small_example_ledger: FavaLedger,
) -> None:
    """Test FilteredLedger interval ranges at various boundaries."""
    filtered = small_example_ledger.get_filtered()
    assert filtered._date_first is not None
    assert filtered._date_last is not None

    for interval in [Year, Month, Week, Day]:
        ranges = filtered.interval_ranges(interval)
        assert len(ranges) > 0

        for date_range in ranges:
            assert date_range.begin < date_range.end

        first_range = ranges[0]
        last_range = ranges[-1]
        assert first_range.begin <= filtered._date_first
        assert last_range.end >= filtered._date_last


def test_time_filter_boundary_dates(
    small_example_ledger: FavaLedger,
) -> None:
    """Test time filter parsing for boundary dates."""
    test_cases = [
        ("2016-01-01", date(2016, 1, 1), date(2016, 1, 2)),
        ("2016-02-29", date(2016, 2, 29), date(2016, 3, 1)),
        ("2016-12-31", date(2016, 12, 31), date(2017, 1, 1)),
        ("2016-01", date(2016, 1, 1), date(2016, 2, 1)),
        ("2016-12", date(2016, 12, 1), date(2017, 1, 1)),
        ("2016", date(2016, 1, 1), date(2017, 1, 1)),
    ]

    for filter_str, expected_begin, expected_end in test_cases:
        time_filter = TimeFilter(
            small_example_ledger.options,
            small_example_ledger.fava_options,
            filter_str,
        )
        assert time_filter.date_range.begin == expected_begin
        assert time_filter.date_range.end == expected_end


def test_advanced_filter_combination(
    small_example_ledger: FavaLedger,
) -> None:
    """Test advanced filter with multiple conditions."""
    filter_str = 'payee:BayBook #test'
    adv_filter = AdvancedFilter(filter_str)

    filtered = adv_filter.apply(small_example_ledger.all_entries)

    for entry in filtered:
        payee = getattr(entry, "payee", "")
        tags = getattr(entry, "tags", frozenset())
        assert "BayBook" in payee or "test" in tags


def test_account_filter_regex_boundary(
    small_example_ledger: FavaLedger,
) -> None:
    """Test account filter with regex patterns at boundaries."""
    test_cases = [
        ("^Assets:US", "Assets:US"),
        ("Checking$", "Checking"),
        (".*:BofA:.*", "BofA"),
    ]

    for pattern, expected_substring in test_cases:
        account_filter = AccountFilter(pattern)
        filtered = account_filter.apply(small_example_ledger.all_entries)

        for entry in filtered:
            accounts = [p.account for p in getattr(entry, "postings", [])]
            assert any(expected_substring in acc for acc in accounts)


def test_charts_interval_boundary_overflow(
    get_ledger: GetFavaLedger,
) -> None:
    """Test chart interval totals with more than 100 intervals."""
    ledger = get_ledger("long-example")
    from fava.core import FilteredLedger
    from fava.util.date import Day

    filtered = FilteredLedger(ledger, time="2010-2020")
    data = ledger.charts.interval_totals(
        filtered,
        Day,
        "Expenses",
        "at_cost",
    )

    assert len(data) <= 100

    all_dates = [item.date for item in data]
    assert len(set(all_dates)) == len(all_dates)


def test_tree_with_advanced_filter(
    small_example_ledger: FavaLedger,
) -> None:
    """Test tree construction with advanced filter applied."""
    adv_filter = AdvancedFilter('#test')
    filtered_entries = adv_filter.apply(small_example_ledger.all_entries)

    tree = Tree(filtered_entries)

    assert len(tree) >= 1

    test_node = tree.get("Expenses")
    assert test_node.name == "Expenses"


def test_budget_tree_chart_combined(
    small_example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    """Test budget, tree, and chart functionality combined."""
    filtered = FilteredLedger(
        small_example_ledger,
        time="2016",
        account="Expenses",
    )

    chart_data = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        "Expenses",
        "at_cost",
    )

    tree = Tree(filtered.entries)
    hierarchy_data = small_example_ledger.charts.hierarchy(
        filtered, "Expenses", AT_COST
    )

    assert len(chart_data) > 0
    assert hierarchy_data.account == "Expenses"

    for item in chart_data:
        assert item.date.year == 2016
        assert isinstance(item.balance, dict)
        assert isinstance(item.budgets, dict)

    snapshot(chart_data, json=True)


def test_empty_result_handling(
    small_example_ledger: FavaLedger,
) -> None:
    """Test handling of empty results across all modules."""
    filtered = FilteredLedger(small_example_ledger, time="1900")

    tree = Tree(filtered.entries)
    assert len(tree) == 1

    chart_data = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        "Expenses",
        "at_cost",
    )
    for item in chart_data:
        assert item.balance == {}
        assert item.budgets == {}
        assert item.account_balances == {}

    linechart_data = small_example_ledger.charts.linechart(
        filtered,
        "Assets:US:BofA:Checking",
        "units",
    )
    assert linechart_data == []

    net_worth_data = small_example_ledger.charts.net_worth(
        filtered,
        Month,
        "USD",
    )
    for item in net_worth_data:
        for value in item.balance.values():
            assert value == Decimal(0)


def test_fiscal_year_boundary(
    small_example_ledger: FavaLedger,
) -> None:
    """Test fiscal year boundary handling."""
    from fava.util.date import parse_date

    begin, end = parse_date("FY2016", small_example_ledger.fava_options.fiscal_year_end)
    assert begin is not None
    assert end is not None
    assert begin < end


def test_date_range_overlap_protection(
    load_doc_custom_entries: list[Custom],
) -> None:
    """Test budget calculation with overlapping date ranges."""
    budgets, _ = parse_budgets(load_doc_custom_entries)

    result1 = calculate_budget(
        budgets,
        "Expenses:Books",
        date(2016, 1, 1),
        date(2016, 1, 15),
    )

    result2 = calculate_budget(
        budgets,
        "Expenses:Books",
        date(2016, 1, 10),
        date(2016, 1, 25),
    )

    result3 = calculate_budget(
        budgets,
        "Expenses:Books",
        date(2016, 1, 1),
        date(2016, 1, 25),
    )

    for currency in result1:
        if currency in result2 and currency in result3:
            assert result3[currency] <= result1[currency] + result2[currency]


def test_multiple_currency_tree_budget(
    small_example_ledger: FavaLedger,
) -> None:
    """Test tree and budget with multiple currencies."""
    filtered = small_example_ledger.get_filtered()

    hierarchy = small_example_ledger.charts.hierarchy(
        filtered, "Assets", AT_COST
    )

    currencies = set()
    for child in hierarchy.children:
        currencies.update(child.balance_children.keys())
        currencies.update(child.balance.keys())

    assert len(currencies) >= 1


def test_filter_chain_protection(
    small_example_ledger: FavaLedger,
) -> None:
    """Test applying multiple filters in sequence."""
    time_filter = TimeFilter(
        small_example_ledger.options,
        small_example_ledger.fava_options,
        "2016",
    )
    account_filter = AccountFilter("Expenses:Food")
    adv_filter = AdvancedFilter('payee:BayBook')

    entries = small_example_ledger.all_entries
    entries = time_filter.apply(entries)
    entries = account_filter.apply(entries)
    entries = adv_filter.apply(entries)

    assert len(entries) <= len(small_example_ledger.all_entries)


@pytest.mark.parametrize(
    ("time_filter", "account_filter", "expect_data"),
    [
        ("1900", "Expenses", False),
        ("2016", "NonExistent:Account", False),
        ("2016", "Expenses", True),
    ],
)
def test_filter_combination_edge_cases(
    small_example_ledger: FavaLedger,
    time_filter: str,
    account_filter: str,
    expect_data: bool,
) -> None:
    """Test filter combinations with edge cases."""
    filtered = FilteredLedger(
        small_example_ledger,
        time=time_filter,
        account=account_filter,
    )

    data = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        account_filter,
        "at_cost",
    )

    assert len(data) > 0
    for item in data:
        if expect_data:
            assert len(item.balance) >= 0
        else:
            assert item.balance == {}
            assert item.budgets == {}
            assert item.account_balances == {}


def test_budget_update_boundary(
    load_doc_custom_entries: list[Custom],
) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "daily" 50.00 USD
    2020-06-01 custom "budget" Expenses:Food "daily" 100.00 USD"""
    budgets, _ = parse_budgets(load_doc_custom_entries)

    result_before = calculate_budget(
        budgets,
        "Expenses:Food",
        date(2020, 5, 31),
        date(2020, 6, 1),
    )
    assert result_before["USD"] == Decimal("50.00")

    result_after = calculate_budget(
        budgets,
        "Expenses:Food",
        date(2020, 6, 1),
        date(2020, 6, 2),
    )
    assert result_after["USD"] == Decimal("100.00")

    result_crossing = calculate_budget(
        budgets,
        "Expenses:Food",
        date(2020, 5, 31),
        date(2020, 6, 2),
    )
    assert result_crossing["USD"] == Decimal("150.00")


def test_hierarchy_with_time_filter(
    example_ledger: FavaLedger,
) -> None:
    """Test hierarchy chart with various time filters."""
    for time_str in ["2015", "2016", "2017"]:
        filtered = FilteredLedger(example_ledger, time=time_str)
        hierarchy = example_ledger.charts.hierarchy(
            filtered, "Assets", AT_COST
        )

        assert hierarchy.account == "Assets"
        assert len(hierarchy.children) > 0


def test_net_worth_boundary_years(
    example_ledger: FavaLedger,
) -> None:
    """Test net worth calculation at year boundaries."""
    for year in range(2014, 2018):
        filtered = FilteredLedger(example_ledger, time=str(year))
        data = example_ledger.charts.net_worth(
            filtered,
            Month,
            "USD",
        )

        assert len(data) <= 12
        for item in data:
            assert item.date.year == year
