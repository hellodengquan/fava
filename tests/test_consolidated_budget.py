"""Unit tests for the consolidated budget merging logic and API endpoint.

Covers:
- Empty / single / multiple ledger combinations
- Accounts present in only a subset of ledgers
- Children-only-present-on-one-ledger scenarios
- Different currency mixes per ledger
- Fast-path conversion when only one ledger has data
- The _sum_mapping utility
- The per-request cache hit behaviour
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from test_json_api import assert_api_success

from fava.json_api import _consolidated_cache_key
from fava.json_api import _convert_breakdown_to_consolidated
from fava.json_api import _merge_accounts
from fava.json_api import _sum_mapping
from fava.json_api import BudgetBreakdownAccount
from fava.json_api import BudgetBreakdownInterval
from fava.json_api import ConsolidatedBudgetAccount

if TYPE_CHECKING:  # pragma: no cover
    from flask.testing import FlaskClient


def _iv(
    label: str,
    budget: dict[str, int] | None = None,
    actual: dict[str, int] | None = None,
) -> BudgetBreakdownInterval:
    """Construct a BudgetBreakdownInterval with sensible defaults.

    budget_children and actual_children are not used by the merge code, so
    they default to empty dicts (matches the validator).
    """
    return BudgetBreakdownInterval(
        label=label,
        budget={k: Decimal(v) for k, v in (budget or {}).items()},
        budget_children={},
        actual={k: Decimal(v) for k, v in (actual or {}).items()},
        actual_children={},
    )


def _node(
    account: str,
    intervals: list[BudgetBreakdownInterval],
    children: list[BudgetBreakdownAccount] | None = None,
) -> BudgetBreakdownAccount:
    return BudgetBreakdownAccount(
        account=account,
        intervals=intervals,
        children=children or [],
    )


# ---------------------------------------------------------------------------
# _sum_mapping utility
# ---------------------------------------------------------------------------


class TestSumMapping:
    def test_empty_accumulator(self) -> None:
        acc: dict[str, Decimal] = {}
        _sum_mapping(acc, {"USD": Decimal(10), "EUR": Decimal(5)})
        assert acc == {"USD": Decimal(10), "EUR": Decimal(5)}

    def test_accumulates_existing_keys(self) -> None:
        acc: dict[str, Decimal] = {"USD": Decimal(3)}
        _sum_mapping(acc, {"USD": Decimal(7), "EUR": Decimal(2)})
        assert acc == {"USD": Decimal(10), "EUR": Decimal(2)}

    def test_empty_mapping_no_change(self) -> None:
        acc: dict[str, Decimal] = {"USD": Decimal(1)}
        _sum_mapping(acc, {})
        assert acc == {"USD": Decimal(1)}


# ---------------------------------------------------------------------------
# Fast-path conversion tests
# ---------------------------------------------------------------------------


class TestConvertBreakdownToConsolidated:
    def test_simple_leaf_conversion(self) -> None:
        src = _node(
            "Expenses:Food",
            [
                _iv("2024-Q1", {"USD": 100}, {"USD": 110}),
                _iv("2024-Q2", {"USD": 100}, {"USD": 90}),
            ],
        )
        result = _convert_breakdown_to_consolidated(src)
        assert isinstance(result, ConsolidatedBudgetAccount)
        assert result.account == "Expenses:Food"
        assert len(result.intervals) == 2
        assert result.intervals[0].label == "2024-Q1"
        assert result.intervals[0].budget["USD"] == Decimal(100)
        assert result.intervals[0].actual["USD"] == Decimal(110)
        assert result.intervals[1].actual["USD"] == Decimal(90)
        assert result.children == []

    def test_nested_children_converted(self) -> None:
        child = _node(
            "Expenses:Food:Groceries",
            [_iv("2024-Q1", {"USD": 60})],
        )
        parent = _node(
            "Expenses:Food",
            [_iv("2024-Q1", {"USD": 100})],
            [child],
        )
        result = _convert_breakdown_to_consolidated(parent)
        assert len(result.children) == 1
        assert result.children[0].account == "Expenses:Food:Groceries"
        assert result.children[0].intervals[0].budget["USD"] == Decimal(60)

    def test_preserves_all_currencies(self) -> None:
        src = _node(
            "Expenses:Travel",
            [
                _iv(
                    "2024",
                    {"USD": 1000, "EUR": 500},
                    {"USD": 1100, "EUR": 600},
                )
            ],
        )
        result = _convert_breakdown_to_consolidated(src)
        iv = result.intervals[0]
        assert iv.budget["USD"] == Decimal(1000)
        assert iv.budget["EUR"] == Decimal(500)
        assert iv.actual["USD"] == Decimal(1100)
        assert iv.actual["EUR"] == Decimal(600)


# ---------------------------------------------------------------------------
# _merge_accounts
# ---------------------------------------------------------------------------


class TestMergeAccounts:
    def test_empty_input(self) -> None:
        result = _merge_accounts([])
        assert result.account == ""
        assert result.intervals == []
        assert result.children == []

    def test_single_ledger_uses_fast_path(self) -> None:
        """A single element list should use _convert_breakdown_to_consolidated
        and thus have no _merge_accounts recursive merge overhead. We verify
        behaviour by checking output type and data integrity.
        """
        src = _node(
            "Expenses:Food",
            [_iv("2024-Q1", {"USD": 100}, {"USD": 105})],
        )
        result = _merge_accounts([src])
        assert result.account == "Expenses:Food"
        assert len(result.intervals) == 1
        assert result.intervals[0].budget["USD"] == Decimal(100)
        assert result.intervals[0].actual["USD"] == Decimal(105)

    def test_two_ledgers_same_account_same_currency(self) -> None:
        """Two ledgers reporting the same account and currency should sum."""
        ledger_a = _node(
            "Expenses:Food",
            [_iv("2024-Q1", {"USD": 100}, {"USD": 110})],
        )
        ledger_b = _node(
            "Expenses:Food",
            [_iv("2024-Q1", {"USD": 200}, {"USD": 220})],
        )
        result = _merge_accounts([ledger_a, ledger_b])
        assert result.account == "Expenses:Food"
        assert len(result.intervals) == 1
        iv = result.intervals[0]
        assert iv.label == "2024-Q1"
        assert iv.budget["USD"] == Decimal(300)
        assert iv.actual["USD"] == Decimal(330)
        assert result.children == []

    def test_two_ledgers_different_currencies(self) -> None:
        """Ledgers reporting different currencies should union keys."""
        ledger_a = _node(
            "Expenses:Food",
            [_iv("2024-Q1", {"USD": 100})],
        )
        ledger_b = _node(
            "Expenses:Food",
            [_iv("2024-Q1", {"EUR": 200})],
        )
        result = _merge_accounts([ledger_a, ledger_b])
        iv = result.intervals[0]
        assert iv.budget["USD"] == Decimal(100)
        assert iv.budget["EUR"] == Decimal(200)

    def test_account_present_in_only_one_ledger(self) -> None:
        """A child that appears only in one ledger must still appear."""
        parent_a = _node(
            "Expenses",
            [_iv("2024-Q1", {"USD": 100})],
            [
                _node("Expenses:Food", [_iv("2024-Q1", {"USD": 50})]),
            ],
        )
        parent_b = _node(
            "Expenses",
            [_iv("2024-Q1", {"USD": 200})],
            [
                _node("Expenses:Travel", [_iv("2024-Q1", {"USD": 150})]),
            ],
        )
        result = _merge_accounts([parent_a, parent_b])
        child_names = {c.account for c in result.children}
        assert child_names == {"Expenses:Food", "Expenses:Travel"}
        food = next(
            c for c in result.children if c.account == "Expenses:Food"
        )
        assert food.intervals[0].budget["USD"] == Decimal(50)
        travel = next(
            c for c in result.children if c.account == "Expenses:Travel"
        )
        assert travel.intervals[0].budget["USD"] == Decimal(150)

    def test_three_ledgers_deep_merge(self) -> None:
        """Three ledgers with overlapping and non-overlapping children."""
        def make(
            child_name: str, budget: int
        ) -> BudgetBreakdownAccount:
            return _node(
                "Expenses",
                [_iv("Jan", {"USD": budget})],
                [
                    _node(
                        f"Expenses:{child_name}",
                        [_iv("Jan", {"USD": budget})],
                    )
                ],
            )

        result = _merge_accounts(
            [make("Food", 10), make("Food", 20), make("Travel", 30)]
        )
        iv = result.intervals[0]
        assert iv.budget["USD"] == Decimal(60)
        child_names = {c.account for c in result.children}
        assert child_names == {"Expenses:Food", "Expenses:Travel"}
        food = next(
            c for c in result.children if c.account == "Expenses:Food"
        )
        assert food.intervals[0].budget["USD"] == Decimal(30)
        travel = next(
            c for c in result.children if c.account == "Expenses:Travel"
        )
        assert travel.intervals[0].budget["USD"] == Decimal(30)

    def test_different_interval_counts(self) -> None:
        """When ledgers have different numbers of intervals, use the longest
        count and treat missing intervals as zeros.
        """
        short = _node(
            "Expenses:Food",
            [_iv("Jan", {"USD": 10})],
        )
        long = _node(
            "Expenses:Food",
            [_iv("Jan", {"USD": 20}), _iv("Feb", {"USD": 25})],
        )
        result = _merge_accounts([short, long])
        assert len(result.intervals) == 2
        assert result.intervals[0].budget["USD"] == Decimal(30)
        assert result.intervals[1].label == "Feb"
        assert result.intervals[1].budget["USD"] == Decimal(25)

    def test_mixed_actual_and_budget(self) -> None:
        """Both keys present.

        Actual present only in A, budget present only in B.
        """
        a = _node(
            "Expenses:Food",
            [_iv("Jan", {}, {"USD": 50})],
        )
        b = _node(
            "Expenses:Food",
            [_iv("Jan", {"USD": 100}, {})],
        )
        result = _merge_accounts([a, b])
        iv = result.intervals[0]
        assert iv.budget["USD"] == Decimal(100)
        assert iv.actual["USD"] == Decimal(50)


# ---------------------------------------------------------------------------
# _consolidated_cache_key
# ---------------------------------------------------------------------------


class TestConsolidatedCacheKey:
    def test_key_stability(self) -> None:
        k1 = _consolidated_cache_key("ledger-a", "Expenses", "month")
        k2 = _consolidated_cache_key("ledger-a", "Expenses", "month")
        assert k1 == k2

    def test_key_distinguishes_components(self) -> None:
        keys = {
            _consolidated_cache_key("a", "Exp", "month"),
            _consolidated_cache_key("b", "Exp", "month"),
            _consolidated_cache_key("a", "Inc", "month"),
            _consolidated_cache_key("a", "Exp", "quarter"),
        }
        assert len(keys) == 4


# ---------------------------------------------------------------------------
# get_consolidated_budget API endpoint (integration tests)
# ---------------------------------------------------------------------------


class TestConsolidatedBudgetApi:
    def test_endpoint_exists_and_returns_structure(
        self, test_client: FlaskClient
    ) -> None:
        """Hitting the endpoint for the long-example ledger should return
        a 200 with the expected top-level structure.
        """
        res = test_client.get(
            "/long-example/api/consolidated_budget?interval=year"
        )
        assert res.status_code == 200
        data = assert_api_success(res)
        # Top-level keys required by the validator
        for key in ("ledgers", "interval", "dates", "root"):
            assert key in data, f"Missing required key: {key}"

        # "ledgers" should list every ledger in the test app
        titles = [item["title"] for item in data["ledgers"]]
        # At least the long-example ledger should be there
        assert any(titles)

        # root must be an account node
        assert "account" in data["root"]
        assert "intervals" in data["root"]
        assert "children" in data["root"]

    def test_endpoint_with_account_filter(
        self, test_client: FlaskClient
    ) -> None:
        """Requesting with a=Expenses should not 500."""
        res = test_client.get(
            "/long-example/api/consolidated_budget?interval=year&a=Expenses"
        )
        assert res.status_code == 200
        data = assert_api_success(res)
        assert "root" in data

    def test_endpoint_interval_label(
        self, test_client: FlaskClient
    ) -> None:
        """The 'interval' field of the response should reflect the URL param.

        Note: the labels match Interval.label.lower(), e.g. "quarterly",
        not the raw URL param "quarter".
        """
        res = test_client.get(
            "/long-example/api/consolidated_budget?interval=quarter"
        )
        assert res.status_code == 200
        data = assert_api_success(res)
        assert data["interval"] == "quarterly"

        res_year = test_client.get(
            "/long-example/api/consolidated_budget?interval=year"
        )
        assert res_year.status_code == 200
        data_year = assert_api_success(res_year)
        assert data_year["interval"] == "yearly"

        res_month = test_client.get(
            "/long-example/api/consolidated_budget"
        )
        assert res_month.status_code == 200
        data_month = assert_api_success(res_month)
        # default (no interval) is month
        assert data_month["interval"] == "monthly"
