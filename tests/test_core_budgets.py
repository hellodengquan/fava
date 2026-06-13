"""Fava's budget syntax."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from fava.core.budgets import calculate_budget
from fava.core.budgets import calculate_budget_children
from fava.core.budgets import parse_budgets

if TYPE_CHECKING:  # pragma: no cover
    from fava.beans.abc import Custom
    from fava.core.budgets import BudgetDict


def test_budgets(load_doc_custom_entries: list[Custom]) -> None:
    """
    2016-01-01 custom "budget" Expenses:Groceries "weekly" 100.00 CNY
    2016-06-01 custom "budget" Expenses:Groceries "weekly"  10.00 EUR
    2016-06-01 custom "budget" Expenses:Groceries "asdfasdf"  10.00 EUR
    2016-01-01 custom "budget" Expenses:Groceries "weekly"
    2016-06-01 custom "budget" Expenses:Groceries 10.00 EUR
    """
    budgets, errors = parse_budgets(load_doc_custom_entries)

    assert len(errors) == 3

    empty = calculate_budget(
        budgets,
        "Expenses",
        date(2016, 6, 1),
        date(2016, 6, 8),
    )
    assert not empty

    budgets_ = calculate_budget(
        budgets,
        "Expenses:Groceries",
        date(2016, 6, 1),
        date(2016, 6, 8),
    )

    assert budgets_["CNY"] == Decimal(100)
    assert budgets_["EUR"] == Decimal(10)


def test_budgets_daily(budgets_doc: BudgetDict) -> None:
    """
    2016-05-01 custom "budget" Expenses:Books "daily" 2.5 EUR"""

    assert "EUR" not in calculate_budget(
        budgets_doc,
        "Expenses:Books",
        date(2010, 2, 1),
        date(2010, 2, 2),
    )

    for start, end, num in [
        (date(2016, 5, 1), date(2016, 5, 2), Decimal("2.5")),
        (date(2016, 5, 1), date(2016, 5, 3), Decimal("5.0")),
        (date(2016, 9, 2), date(2016, 9, 3), Decimal("2.5")),
        (date(2018, 12, 31), date(2019, 1, 1), Decimal("2.5")),
    ]:
        budget = calculate_budget(budgets_doc, "Expenses:Books", start, end)
        assert budget["EUR"] == num


def test_budgets_weekly(budgets_doc: BudgetDict) -> None:
    """
    2016-05-01 custom "budget" Expenses:Books "weekly" 21 EUR"""

    for start, end, num in [
        (date(2016, 5, 1), date(2016, 5, 2), Decimal(21) / 7),
        (date(2016, 9, 1), date(2016, 9, 2), Decimal(21) / 7),
    ]:
        budget = calculate_budget(budgets_doc, "Expenses:Books", start, end)
        assert budget["EUR"] == num


def test_budgets_monthly(budgets_doc: BudgetDict) -> None:
    """
    2014-05-01 custom "budget" Expenses:Books "monthly" 100 EUR"""

    for start, end, num in [
        (date(2016, 5, 1), date(2016, 5, 2), Decimal(100) / 31),
        (date(2016, 2, 1), date(2016, 2, 2), Decimal(100) / 29),
        (date(2018, 3, 31), date(2018, 4, 1), Decimal(100) / 31),
    ]:
        budget = calculate_budget(budgets_doc, "Expenses:Books", start, end)
        assert budget["EUR"] == num


def test_budgets_doc_quarterly(budgets_doc: BudgetDict) -> None:
    """
    2014-05-01 custom "budget" Expenses:Books "quarterly" 123456.7 EUR"""

    for start, end, num in [
        (date(2016, 5, 1), date(2016, 5, 2), Decimal("123456.7") / 91),
        (date(2016, 8, 15), date(2016, 8, 16), Decimal("123456.7") / 92),
    ]:
        budget = calculate_budget(budgets_doc, "Expenses:Books", start, end)
        assert budget["EUR"] == num


def test_budgets_doc_yearly(budgets_doc: BudgetDict) -> None:
    """
    2010-01-01 custom "budget" Expenses:Books "yearly" 99999.87 EUR"""

    budget = calculate_budget(
        budgets_doc,
        "Expenses:Books",
        date(2011, 2, 1),
        date(2011, 2, 2),
    )
    assert budget["EUR"] == Decimal("99999.87") / 365


def test_budgets_children(budgets_doc: BudgetDict) -> None:
    """
    2017-01-01 custom "budget" Expenses:Books "daily" 10.00 USD
    2017-01-01 custom "budget" Expenses:Books:Notebooks "daily" 2.00 USD"""

    budget = calculate_budget_children(
        budgets_doc,
        "Expenses",
        date(2017, 1, 1),
        date(2017, 1, 2),
    )
    assert budget["USD"] == Decimal("12.00")

    budget = calculate_budget_children(
        budgets_doc,
        "Expenses:Books",
        date(2017, 1, 1),
        date(2017, 1, 2),
    )
    assert budget["USD"] == Decimal("12.00")

    budget = calculate_budget_children(
        budgets_doc,
        "Expenses:Books:Notebooks",
        date(2017, 1, 1),
        date(2017, 1, 2),
    )
    assert budget["USD"] == Decimal("2.00")


def test_budgets_empty_dict() -> None:
    """Test budget calculation with empty budget dictionary."""
    empty_budgets: BudgetDict = {}

    result = calculate_budget(
        empty_budgets,
        "Expenses:Test",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result == {}

    result_children = calculate_budget_children(
        empty_budgets,
        "Expenses",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result_children == {}


def test_budgets_nonexistent_account(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "daily" 50.00 USD"""

    result = calculate_budget(
        budgets_doc,
        "Expenses:NonExistent",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result == {}

    result_children = calculate_budget_children(
        budgets_doc,
        "NonExistentRoot",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result_children == {}


def test_budgets_date_before_start(budgets_doc: BudgetDict) -> None:
    """
    2020-06-01 custom "budget" Expenses:Food "daily" 50.00 USD"""

    result = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result == {}

    result_partial = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 5, 30),
        date(2020, 6, 2),
    )
    assert "USD" in result_partial
    assert result_partial["USD"] == Decimal("50.00")


def test_budgets_invalid_date_range(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "daily" 50.00 USD"""

    result_same_day = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 1),
        date(2020, 1, 1),
    )
    assert result_same_day == {}

    result_reversed = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 2),
        date(2020, 1, 1),
    )
    assert result_reversed == {}


def test_budgets_multiple_currencies(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "daily" 50.00 USD
    2020-01-01 custom "budget" Expenses:Food "daily" 40.00 EUR
    2020-01-01 custom "budget" Expenses:Food "daily" 300.00 CNY"""

    result = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result["USD"] == Decimal("50.00")
    assert result["EUR"] == Decimal("40.00")
    assert result["CNY"] == Decimal("300.00")
    assert len(result) == 3


def test_budgets_updated_over_time(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "monthly" 1000.00 USD
    2020-06-01 custom "budget" Expenses:Food "monthly" 1500.00 USD
    2021-01-01 custom "budget" Expenses:Food "monthly" 2000.00 USD"""

    result_may = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 5, 15),
        date(2020, 5, 16),
    )
    assert result_may["USD"] == Decimal(1000) / 31

    result_june = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 6, 15),
        date(2020, 6, 16),
    )
    assert result_june["USD"] == Decimal(1500) / 30

    result_jan_2021 = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2021, 1, 15),
        date(2021, 1, 16),
    )
    assert result_jan_2021["USD"] == Decimal(2000) / 31

    result_cross_update = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 5, 31),
        date(2020, 6, 2),
    )
    days_may = Decimal(1000) / 31
    days_june = Decimal(1500) / 30
    assert result_cross_update["USD"] == days_may + days_june


def test_budgets_account_prefix_boundary(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "daily" 50.00 USD
    2020-01-01 custom "budget" Expenses:Food:Groceries "daily" 30.00 USD
    2020-01-01 custom "budget" Expenses:Food:Restaurant "daily" 20.00 USD
    2020-01-01 custom "budget" Expenses:Foodie "daily" 100.00 USD"""

    result_food = calculate_budget_children(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result_food["USD"] == Decimal("200.00")

    result_food_exact = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result_food_exact["USD"] == Decimal("50.00")

    result_foodie = calculate_budget_children(
        budgets_doc,
        "Expenses:Foodie",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result_foodie["USD"] == Decimal("100.00")

    result_expenses = calculate_budget_children(
        budgets_doc,
        "Expenses",
        date(2020, 1, 1),
        date(2020, 1, 2),
    )
    assert result_expenses["USD"] == Decimal("200.00")


def test_budgets_leap_year_boundary(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Books "monthly" 290.00 EUR
    2020-01-01 custom "budget" Expenses:Books "daily" 10.00 USD"""

    result_feb_2020 = calculate_budget(
        budgets_doc,
        "Expenses:Books",
        date(2020, 2, 28),
        date(2020, 2, 29),
    )
    assert result_feb_2020["EUR"] == Decimal(290) / 29
    assert result_feb_2020["USD"] == Decimal("10.00")

    result_feb_2021 = calculate_budget(
        budgets_doc,
        "Expenses:Books",
        date(2021, 2, 27),
        date(2021, 2, 28),
    )
    assert result_feb_2021["EUR"] == Decimal(290) / 28
    assert result_feb_2021["USD"] == Decimal("10.00")

    result_leap_day = calculate_budget(
        budgets_doc,
        "Expenses:Books",
        date(2020, 2, 29),
        date(2020, 3, 1),
    )
    assert result_leap_day["EUR"] == Decimal(290) / 29
    assert result_leap_day["USD"] == Decimal("10.00")


def test_budgets_month_end_boundary(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "monthly" 3100.00 USD"""

    result_jan_31 = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 31),
        date(2020, 2, 1),
    )
    assert result_jan_31["USD"] == Decimal(3100) / 31

    result_feb_28 = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 2, 28),
        date(2020, 2, 29),
    )
    assert result_feb_28["USD"] == Decimal(3100) / 29

    result_apr_30 = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 4, 30),
        date(2020, 5, 1),
    )
    assert result_apr_30["USD"] == Decimal(3100) / 30


def test_budgets_long_date_range(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Books "daily" 10.00 USD"""

    result_full_year = calculate_budget(
        budgets_doc,
        "Expenses:Books",
        date(2020, 1, 1),
        date(2021, 1, 1),
    )
    assert result_full_year["USD"] == Decimal("3660.00")

    result_leap_year = calculate_budget(
        budgets_doc,
        "Expenses:Books",
        date(2020, 2, 1),
        date(2020, 3, 1),
    )
    assert result_leap_year["USD"] == Decimal("290.00")


def test_budgets_currency_override(budgets_doc: BudgetDict) -> None:
    """
    2020-01-01 custom "budget" Expenses:Food "daily" 50.00 USD
    2020-06-01 custom "budget" Expenses:Food "daily" 60.00 USD
    2020-06-01 custom "budget" Expenses:Food "daily" 40.00 EUR"""

    result_jan = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 1, 15),
        date(2020, 1, 16),
    )
    assert result_jan["USD"] == Decimal("50.00")
    assert "EUR" not in result_jan

    result_july = calculate_budget(
        budgets_doc,
        "Expenses:Food",
        date(2020, 7, 15),
        date(2020, 7, 16),
    )
    assert result_july["USD"] == Decimal("60.00")
    assert result_july["EUR"] == Decimal("40.00")
