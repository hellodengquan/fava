"""Fava's budget syntax."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from fava.core.budgets import BudgetStatus
from fava.core.budgets import calculate_budget
from fava.core.budgets import calculate_budget_children
from fava.core.budgets import calculate_budget_status
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
    budgets, _by_cat, _cats, errors = parse_budgets(load_doc_custom_entries)

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


def test_budgets_with_category(load_doc_custom_entries: list[Custom]) -> None:
    """
    2016-01-01 custom "budget" Expenses:Food     "monthly" 300.00 EUR "living"
    2016-01-01 custom "budget" Expenses:Transport "monthly" 150.00 EUR "living"
    2016-01-01 custom "budget" Expenses:Holiday   "yearly"  2000 EUR "travel"
    """
    budgets, by_cat, cats, errors = parse_budgets(load_doc_custom_entries)
    assert len(errors) == 0
    assert "living" in cats
    assert "travel" in cats
    assert "living" in by_cat
    assert "travel" in by_cat

    living_budgets = by_cat["living"]
    assert len(living_budgets) == 2
    accounts_with_living = {b.account for b in living_budgets}
    assert accounts_with_living == {"Expenses:Food", "Expenses:Transport"}

    cat0 = living_budgets[0]
    assert cat0.category == "living"

    food_no_cat = calculate_budget(
        budgets,
        "Expenses:Food",
        date(2016, 1, 1),
        date(2016, 2, 1),
    )
    assert round(food_no_cat["EUR"] - Decimal("300.00"), 10) == 0

    food_with_wrong_cat = calculate_budget(
        budgets,
        "Expenses:Food",
        date(2016, 1, 1),
        date(2016, 2, 1),
        category="travel",
    )
    assert "EUR" not in food_with_wrong_cat

    food_with_right_cat = calculate_budget(
        budgets,
        "Expenses:Food",
        date(2016, 1, 1),
        date(2016, 2, 1),
        category="living",
    )
    assert round(food_with_right_cat["EUR"] - Decimal("300.00"), 10) == 0


def test_calculate_budget_status() -> None:
    assert calculate_budget_status(Decimal(100), Decimal(0)) == BudgetStatus.OK
    assert calculate_budget_status(Decimal(100), Decimal(50)) == BudgetStatus.OK
    assert calculate_budget_status(Decimal(100), Decimal(79)) == BudgetStatus.OK
    assert calculate_budget_status(Decimal(100), Decimal(80)) == BudgetStatus.NEAR
    assert calculate_budget_status(Decimal(100), Decimal(95)) == BudgetStatus.NEAR
    assert calculate_budget_status(Decimal(100), Decimal(100)) == BudgetStatus.OVER
    assert calculate_budget_status(Decimal(100), Decimal(120)) == BudgetStatus.OVER
    assert calculate_budget_status(Decimal(0), Decimal(100)) == BudgetStatus.OK
    assert calculate_budget_status(Decimal(-1), Decimal(100)) == BudgetStatus.OK
