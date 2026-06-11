"""Parsing and computing budgets."""

from __future__ import annotations

from collections import Counter
from collections import defaultdict
from decimal import Decimal
from enum import Enum
from typing import NamedTuple
from typing import TYPE_CHECKING

from fava.core.module_base import FavaModule
from fava.helpers import BeancountError
from fava.util.date import days_in_daterange
from fava.util.date import INTERVALS

if TYPE_CHECKING:  # pragma: no cover
    import datetime
    from collections.abc import Mapping
    from collections.abc import Sequence

    from fava.beans.abc import Custom
    from fava.core import FavaLedger
    from fava.util.date import Interval


class Budget(NamedTuple):
    """A budget entry."""

    account: str
    date_start: datetime.date
    period: Interval
    number: Decimal
    currency: str
    category: str | None = None


BudgetDict = dict[str, list[Budget]]
"""A map of account names to lists of budget entries."""

BudgetCategoryDict = dict[str, list[Budget]]
"""A map of category names to lists of budget entries."""


NEAR_OVERSPENT_THRESHOLD = Decimal("0.8")
"""A budget is considered near overspent at 80% usage."""

OVERSPENT_THRESHOLD = Decimal("1.0")
"""A budget is considered overspent at 100% usage."""


class BudgetStatus(str, Enum):
    """Status of a budget relative to actual spending."""

    OK = "ok"
    NEAR = "near"
    OVER = "over"


def calculate_budget_status(
    budgeted: Decimal,
    actual: Decimal,
) -> BudgetStatus:
    """Calculate the budget status based on actual vs budgeted amount.

    Args:
        budgeted: The budgeted amount (should be positive).
        actual: The actual spending amount.

    Returns:
        BudgetStatus indicating whether spending is OK, near overspent, or overspent.
    """
    if budgeted <= 0:
        return BudgetStatus.OK
    ratio = actual / budgeted
    if ratio >= OVERSPENT_THRESHOLD:
        return BudgetStatus.OVER
    if ratio >= NEAR_OVERSPENT_THRESHOLD:
        return BudgetStatus.NEAR
    return BudgetStatus.OK


class BudgetError(BeancountError):
    """Error with a budget."""


class BudgetModule(FavaModule):
    """Parses budget entries."""

    def __init__(self, ledger: FavaLedger) -> None:
        super().__init__(ledger)
        self._budget_entries: BudgetDict = {}
        self._budget_by_category: BudgetCategoryDict = {}
        self.errors: Sequence[BudgetError] = []
        self._all_categories: list[str] = []

    def load_file(self) -> None:  # noqa: D102
        (
            self._budget_entries,
            self._budget_by_category,
            self._all_categories,
            self.errors,
        ) = parse_budgets(
            self.ledger.all_entries_by_type.Custom,
        )

    @property
    def all_categories(self) -> list[str]:
        """Get all unique budget categories."""
        return self._all_categories

    def calculate(
        self,
        account: str,
        begin_date: datetime.date,
        end_date: datetime.date,
        category: str | None = None,
    ) -> Mapping[str, Decimal]:
        """Calculate the budget for an account in an interval.

        Args:
            account: The account name.
            begin_date: Start date (inclusive).
            end_date: End date (exclusive).
            category: Optional category filter.
        """
        return calculate_budget(
            self._budget_entries,
            account,
            begin_date,
            end_date,
            category,
        )

    def calculate_children(
        self,
        account: str,
        begin_date: datetime.date,
        end_date: datetime.date,
        category: str | None = None,
    ) -> Mapping[str, Decimal]:
        """Calculate the budget for an account including its children.

        Args:
            account: The account name.
            begin_date: Start date (inclusive).
            end_date: End date (exclusive).
            category: Optional category filter.
        """
        return calculate_budget_children(
            self._budget_entries,
            account,
            begin_date,
            end_date,
            category,
        )

    def calculate_by_category(
        self,
        category: str,
        begin_date: datetime.date,
        end_date: datetime.date,
    ) -> Mapping[str, Decimal]:
        """Calculate the budget for a category across all accounts.

        Args:
            category: The category name.
            begin_date: Start date (inclusive).
            end_date: End date (exclusive).
        """
        if category not in self._budget_by_category:
            return {}

        currency_dict: dict[str, Decimal] = defaultdict(Decimal)
        for budget in self._budget_by_category[category]:
            result = calculate_budget(
                self._budget_entries,
                budget.account,
                begin_date,
                end_date,
                category,
            )
            for currency, amount in result.items():
                currency_dict[currency] += amount
        return dict(currency_dict)


def parse_budgets(
    custom_entries: Sequence[Custom],
) -> tuple[BudgetDict, BudgetCategoryDict, list[str], Sequence[BudgetError]]:
    """Parse budget directives from custom entries.

    Args:
        custom_entries: the Custom entries to parse budgets from.

    Returns:
        A tuple of (accounts dict, categories dict, categories list, errors).

    Example:
        2015-04-09 custom "budget" Expenses:Books "monthly" 20.00 EUR
        2015-04-09 custom "budget" Expenses:Food "monthly" 300.00 EUR "living"
        2015-04-09 custom "budget" Expenses:Transport "monthly" 150.00 EUR "living"
    """
    budgets: BudgetDict = defaultdict(list)
    budgets_by_category: BudgetCategoryDict = defaultdict(list)
    categories_set: set[str] = set()
    errors = []

    for entry in (entry for entry in custom_entries if entry.type == "budget"):
        try:
            interval = INTERVALS.get(str(entry.values[1].value).lower())
            if not interval:
                errors.append(
                    BudgetError(
                        entry.meta,
                        "Invalid interval for budget entry",
                        entry,
                    ),
                )
                continue
            account = entry.values[0].value
            period = interval
            number = entry.values[2].value.number
            currency = entry.values[2].value.currency
            category = (
                str(entry.values[3].value)
                if len(entry.values) > 3 and entry.values[3].value is not None
                else None
            )
            if category:
                categories_set.add(category)
            budget = Budget(
                account=account,
                date_start=entry.date,
                period=period,
                number=number,
                currency=currency,
                category=category,
            )
            budgets[budget.account].append(budget)
            if category:
                budgets_by_category[category].append(budget)
        except (IndexError, TypeError):
            errors.append(
                BudgetError(entry.meta, "Failed to parse budget entry", entry),
            )

    return budgets, dict(budgets_by_category), sorted(categories_set), errors


def _matching_budgets(
    budgets: Sequence[Budget],
    date_active: datetime.date,
    category: str | None = None,
) -> Mapping[str, Budget]:
    """Find matching budgets.

    Returns:
        The budget that is active on the specified date for the
        specified account.
    """
    last_seen_budgets = {}
    for budget in budgets:
        if budget.date_start <= date_active:
            if category is not None and budget.category != category:
                continue
            last_seen_budgets[budget.currency] = budget
        else:
            break
    return last_seen_budgets


def calculate_budget(
    budgets: BudgetDict,
    account: str,
    date_from: datetime.date,
    date_to: datetime.date,
    category: str | None = None,
) -> Mapping[str, Decimal]:
    """Calculate budget for an account.

    Args:
        budgets: A list of :class:`Budget` entries.
        account: An account name.
        date_from: Starting date.
        date_to: End date (exclusive).
        category: Optional category filter.

    Returns:
        A dictionary of currency to Decimal with the budget for the
        specified account and period.
    """
    budget_list = budgets.get(account, None)
    if budget_list is None:
        return {}

    currency_dict: dict[str, Decimal] = defaultdict(Decimal)

    for day in days_in_daterange(date_from, date_to):
        matches = _matching_budgets(budget_list, day, category)
        for budget in matches.values():
            days_in_period = budget.period.number_of_days(day)
            currency_dict[budget.currency] += budget.number / days_in_period
    return dict(currency_dict)


def calculate_budget_children(
    budgets: BudgetDict,
    account: str,
    date_from: datetime.date,
    date_to: datetime.date,
    category: str | None = None,
) -> Mapping[str, Decimal]:
    """Calculate budget for an account including budgets of its children.

    Args:
        budgets: A list of :class:`Budget` entries.
        account: An account name.
        date_from: Starting date.
        date_to: End date (exclusive).
        category: Optional category filter.

    Returns:
        A dictionary of currency to Decimal with the budget for the
        specified account and period.
    """
    currency_dict: dict[str, Decimal] = Counter()  # type: ignore[assignment]  # ty:ignore[invalid-assignment]

    for child in budgets:
        if child.startswith(account):
            currency_dict.update(
                calculate_budget(budgets, child, date_from, date_to, category),
            )
    return dict(currency_dict)
