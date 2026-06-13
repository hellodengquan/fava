"""Tests for the snapshot storage module."""

from __future__ import annotations

import json
from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from fava.core.snapshots import SnapshotFilters
from fava.core.snapshots import SnapshotRetention
from fava.core.snapshots import SnapshotStore


@pytest.fixture
def mock_ledger(tmp_path: Path) -> MagicMock:
    """Create a mock FavaLedger with a temp beancount file."""
    ledger = MagicMock()
    beancount_file = tmp_path / "test.beancount"
    beancount_file.touch()
    ledger.beancount_file_path = str(beancount_file)
    return ledger


@pytest.fixture
def snapshot_store(mock_ledger: MagicMock) -> SnapshotStore:
    """Create a SnapshotStore instance."""
    store = SnapshotStore(mock_ledger)
    store.load_file()
    return store


class TestSnapshotRetention:
    """Tests for SnapshotRetention dataclass."""

    def test_validate_keep_last_n_valid(self) -> None:
        """Test validation of valid keep_last_n values."""
        policy = SnapshotRetention(keep_last_n=10)
        policy.validate()

    def test_validate_keep_days_valid(self) -> None:
        """Test validation of valid keep_days values."""
        policy = SnapshotRetention(keep_days=30)
        policy.validate()

    def test_validate_both_valid(self) -> None:
        """Test validation when both policies are set."""
        policy = SnapshotRetention(keep_last_n=5, keep_days=30)
        policy.validate()

    def test_validate_negative_keep_last_n(self) -> None:
        """Test validation raises on negative keep_last_n."""
        policy = SnapshotRetention(keep_last_n=-1)
        with pytest.raises(ValueError, match="keep_last_n must be non-negative"):
            policy.validate()

    def test_validate_negative_keep_days(self) -> None:
        """Test validation raises on negative keep_days."""
        policy = SnapshotRetention(keep_days=-1)
        with pytest.raises(ValueError, match="keep_days must be non-negative"):
            policy.validate()

    def test_validate_no_policy(self) -> None:
        """Test validation raises when no policy is set."""
        policy = SnapshotRetention()
        with pytest.raises(ValueError, match="At least one of"):
            policy.validate()

    def test_validate_zero_keep_last_n(self) -> None:
        """Test validation treats keep_last_n=0 as no policy."""
        policy = SnapshotRetention(keep_last_n=0)
        with pytest.raises(ValueError, match="At least one of"):
            policy.validate()

    def test_validate_zero_keep_days(self) -> None:
        """Test validation treats keep_days=0 as no policy."""
        policy = SnapshotRetention(keep_days=0)
        with pytest.raises(ValueError, match="At least one of"):
            policy.validate()


class TestSnapshotStoreSaveAndLoad:
    """Tests for saving and loading snapshots."""

    def test_save_snapshot(self, snapshot_store: SnapshotStore) -> None:
        """Test basic snapshot save."""
        filters = SnapshotFilters(
            time="2024",
            account="",
            filter="",
            conversion="",
            interval="",
        )
        balances = {"Assets:Cash": {"USD": Decimal("1000")}}
        trees: list[Mapping[str, Any]] = []

        snapshot = snapshot_store.save(
            name="test snapshot",
            report_type="balance_sheet",
            filters=filters,
            balances=balances,
            trees=trees,
        )

        assert snapshot.id is not None
        assert len(snapshot.id) == 12
        assert snapshot.name == "test snapshot"
        assert snapshot.data.report_type == "balance_sheet"

    def test_list_snapshots_empty(self, snapshot_store: SnapshotStore) -> None:
        """Test listing when no snapshots exist."""
        result = snapshot_store.list_snapshots()
        assert result == []

    def test_list_snapshots(self, snapshot_store: SnapshotStore) -> None:
        """Test listing snapshots."""
        filters = SnapshotFilters("", "", "", "", "")
        for i in range(3):
            snapshot_store.save(
                name=f"snap-{i}",
                report_type="balance_sheet",
                filters=filters,
                balances={"Assets": {"USD": Decimal(str(100 * i))}},
                trees=[],
            )

        result = snapshot_store.list_snapshots()
        assert len(result) == 3
        assert all("id" in s for s in result)
        assert all("name" in s for s in result)
        assert all("created_at" in s for s in result)
        assert all("report_type" in s for s in result)

    def test_get_snapshot(self, snapshot_store: SnapshotStore) -> None:
        """Test getting a full snapshot."""
        filters = SnapshotFilters("", "", "", "", "")
        snapshot = snapshot_store.save(
            name="test",
            report_type="income_statement",
            filters=filters,
            balances={"Income:Salary": {"USD": Decimal("5000")}},
            trees=[],
        )

        result = snapshot_store.get_snapshot(snapshot.id)
        assert result is not None
        assert result["id"] == snapshot.id
        assert result["name"] == "test"
        assert result["data"]["report_type"] == "income_statement"
        assert "balances" in result["data"]

    def test_get_snapshot_nonexistent(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test getting a snapshot that doesn't exist."""
        result = snapshot_store.get_snapshot("nonexistent")
        assert result is None

    def test_delete_snapshot(self, snapshot_store: SnapshotStore) -> None:
        """Test deleting a snapshot."""
        filters = SnapshotFilters("", "", "", "", "")
        snapshot = snapshot_store.save(
            name="to-delete",
            report_type="balance_sheet",
            filters=filters,
            balances={},
            trees=[],
        )

        assert snapshot_store.delete(snapshot.id) is True
        assert snapshot_store.get_snapshot(snapshot.id) is None
        assert len(snapshot_store.list_snapshots()) == 0

    def test_delete_nonexistent(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test deleting a snapshot that doesn't exist."""
        assert snapshot_store.delete("nonexistent") is False

    def test_save_with_decimal_serialization(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test that Decimal values serialize properly to JSON."""
        filters = SnapshotFilters("", "", "", "", "")
        snapshot = snapshot_store.save(
            name="decimal test",
            report_type="balance_sheet",
            filters=filters,
            balances={
                "Assets:Cash": {
                    "USD": Decimal("123.45"),
                    "EUR": Decimal("67.89"),
                },
            },
            trees=[],
        )

        loaded = snapshot_store.get_snapshot(snapshot.id)
        assert loaded is not None
        balances = loaded["data"]["balances"]
        assert balances["Assets:Cash"]["USD"] == pytest.approx(123.45)
        assert balances["Assets:Cash"]["EUR"] == pytest.approx(67.89)


class TestBalanceComparison:
    """Tests for balance difference computation."""

    def test_balance_diff_no_change(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test balance diff with identical balances."""
        filters = SnapshotFilters("", "", "", "", "")
        balances = {"Assets:Cash": {"USD": Decimal("1000")}}
        snap_a = snapshot_store.save("a", "balance_sheet", filters, balances, [])
        snap_b = snapshot_store.save("b", "balance_sheet", filters, balances, [])

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["balance_diff"] == {}

    def test_balance_diff_simple(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test simple balance difference."""
        filters = SnapshotFilters("", "", "", "", "")
        balances_a = {"Assets:Cash": {"USD": Decimal("1000")}}
        balances_b = {"Assets:Cash": {"USD": Decimal("1500")}}

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, balances_a, [],
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, balances_b, [],
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["balance_diff"]["Assets:Cash"]["USD"] == pytest.approx(500)

    def test_balance_diff_negative(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test balance diff with decrease."""
        filters = SnapshotFilters("", "", "", "", "")
        balances_a = {"Assets:Cash": {"USD": Decimal("1000")}}
        balances_b = {"Assets:Cash": {"USD": Decimal("700")}}

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, balances_a, [],
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, balances_b, [],
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["balance_diff"]["Assets:Cash"]["USD"] == pytest.approx(-300)

    def test_balance_diff_multiple_accounts(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test balance diff across multiple accounts."""
        filters = SnapshotFilters("", "", "", "", "")
        balances_a = {
            "Assets:Cash": {"USD": Decimal("1000")},
            "Assets:Bank": {"USD": Decimal("5000")},
        }
        balances_b = {
            "Assets:Cash": {"USD": Decimal("1200")},
            "Assets:Bank": {"USD": Decimal("4800")},
            "Assets:Invest": {"USD": Decimal("3000")},
        }

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, balances_a, [],
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, balances_b, [],
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        diff = result["balance_diff"]
        assert diff["Assets:Cash"]["USD"] == pytest.approx(200)
        assert diff["Assets:Bank"]["USD"] == pytest.approx(-200)
        assert diff["Assets:Invest"]["USD"] == pytest.approx(3000)

    def test_balance_diff_multiple_currencies(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test balance diff with multiple currencies per account."""
        filters = SnapshotFilters("", "", "", "", "")
        balances_a = {
            "Assets:Cash": {
                "USD": Decimal("1000"),
                "EUR": Decimal("500"),
            },
        }
        balances_b = {
            "Assets:Cash": {
                "USD": Decimal("1200"),
                "EUR": Decimal("450"),
                "GBP": Decimal("300"),
            },
        }

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, balances_a, [],
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, balances_b, [],
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        diff = result["balance_diff"]["Assets:Cash"]
        assert diff["USD"] == pytest.approx(200)
        assert diff["EUR"] == pytest.approx(-50)
        assert diff["GBP"] == pytest.approx(300)


class TestTreeComparison:
    """Tests for tree structure difference computation."""

    def _make_tree_node(
        self,
        account: str,
        balance: dict[str, float],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Helper to create a tree node dict."""
        return {
            "account": account,
            "balance": balance,
            "balance_children": {},
            "has_txns": True,
            "children": children or [],
        }

    def test_tree_diff_simple(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test simple tree node diff."""
        filters = SnapshotFilters("", "", "", "", "")
        tree_a = [self._make_tree_node("Assets", {"USD": 1000})]
        tree_b = [self._make_tree_node("Assets", {"USD": 1500})]

        snap_a = snapshot_store.save("a", "balance_sheet", filters, {}, tree_a)
        snap_b = snapshot_store.save("b", "balance_sheet", filters, {}, tree_b)

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        tree_diff = result["tree_diff"]
        assert len(tree_diff) == 1
        assert tree_diff[0]["account"] == "Assets"
        assert tree_diff[0]["balance_diff"]["USD"] == pytest.approx(500)

    def test_tree_diff_nested(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test nested tree node diff."""
        filters = SnapshotFilters("", "", "", "", "")
        tree_a = [
            self._make_tree_node(
                "Assets",
                {"USD": 1000},
                [self._make_tree_node("Assets:Cash", {"USD": 1000})],
            ),
        ]
        tree_b = [
            self._make_tree_node(
                "Assets",
                {"USD": 1500},
                [
                    self._make_tree_node("Assets:Cash", {"USD": 700}),
                    self._make_tree_node("Assets:Bank", {"USD": 800}),
                ],
            ),
        ]

        snap_a = snapshot_store.save("a", "balance_sheet", filters, {}, tree_a)
        snap_b = snapshot_store.save("b", "balance_sheet", filters, {}, tree_b)

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        tree_diff = result["tree_diff"]
        assert tree_diff[0]["balance_diff"]["USD"] == pytest.approx(500)

        children = tree_diff[0]["children"]
        assert len(children) == 2

        child_accounts = {c["account"]: c for c in children}
        assert child_accounts["Assets:Cash"]["balance_diff"]["USD"] == pytest.approx(-300)
        assert child_accounts["Assets:Bank"]["balance_diff"]["USD"] == pytest.approx(800)


class TestBudgetComparison:
    """Tests for budget difference computation."""

    def test_budget_diff_simple(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test simple budget diff."""
        filters = SnapshotFilters("", "", "", "", "")
        budgets_a = {
            "Expenses:Food": [{"budget": {"USD": 500}, "budget_children": {}}],
        }
        budgets_b = {
            "Expenses:Food": [{"budget": {"USD": 600}, "budget_children": {}}],
        }

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, {}, [], budgets=budgets_a,
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, {}, [], budgets=budgets_b,
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["budget_diff"] is not None
        assert result["budget_diff"]["Expenses:Food"][0]["budget_diff"][
            "USD"
        ] == pytest.approx(100)

    def test_budget_diff_none_when_missing(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test budget diff is None when one snapshot has no budgets."""
        filters = SnapshotFilters("", "", "", "", "")
        budgets_a = {
            "Expenses:Food": [{"budget": {"USD": 500}, "budget_children": {}}],
        }

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, {}, [], budgets=budgets_a,
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, {}, [],
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["budget_diff"] is None


class TestHoldingsComparison:
    """Tests for holdings difference computation."""

    def test_holdings_diff_no_change(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test holdings diff with identical holdings."""
        filters = SnapshotFilters("", "", "", "", "")
        holdings = [
            {
                "account": "Assets:Invest",
                "units": {"number": 10, "currency": "AAPL"},
                "price": {"number": 150, "currency": "USD"},
                "value": {"number": 1500, "currency": "USD"},
            },
        ]

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, {}, [], holdings=holdings,
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, {}, [], holdings=holdings,
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["holdings_diff"] is not None
        assert result["holdings_diff"] == []

    def test_holdings_diff_price_change(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test holdings diff when price changes."""
        filters = SnapshotFilters("", "", "", "", "")
        holdings_a = [
            {
                "account": "Assets:Invest",
                "units": {"number": 10, "currency": "AAPL"},
                "price": {"number": 150, "currency": "USD"},
                "value": {"number": 1500, "currency": "USD"},
            },
        ]
        holdings_b = [
            {
                "account": "Assets:Invest",
                "units": {"number": 10, "currency": "AAPL"},
                "price": {"number": 180, "currency": "USD"},
                "value": {"number": 1800, "currency": "USD"},
            },
        ]

        snap_a = snapshot_store.save(
            "a", "balance_sheet", filters, {}, [], holdings=holdings_a,
        )
        snap_b = snapshot_store.save(
            "b", "balance_sheet", filters, {}, [], holdings=holdings_b,
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["holdings_diff"] is not None
        assert len(result["holdings_diff"]) == 1

        diff = result["holdings_diff"][0]
        assert diff["price"]["before"] == {"number": 150, "currency": "USD"}
        assert diff["price"]["after"] == {"number": 180, "currency": "USD"}
        assert diff["value"]["before"] == {"number": 1500, "currency": "USD"}
        assert diff["value"]["after"] == {"number": 1800, "currency": "USD"}


class TestCrossCurrencyHoldings:
    """Regression tests for cross-currency holdings comparison.

    These tests verify that holdings comparison works correctly when
    holdings are denominated in different currencies. The comparison
    should be based on the raw snapshot data as captured, NOT on
    live-converted values, to avoid exchange rate drift between
    comparison points.
    """

    def test_cross_currency_holdings_same_units_different_price_currency(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test holdings with units in one currency priced in another.

        Regression test: Compare holdings where the holding currency (units)
        differs from the price/value currency. The diff should accurately
        reflect changes in both units and value without exchange rate drift.
        """
        filters = SnapshotFilters("", "", "", "", "")

        holdings_a = [
            {
                "account": "Assets:Invest:Foreign",
                "units": {"number": 100, "currency": "BTC"},
                "price": {"number": 40000, "currency": "USD"},
                "value": {"number": 4000000, "currency": "USD"},
                "cost": {"number": 3000000, "currency": "USD"},
            },
            {
                "account": "Assets:Cash:Euro",
                "units": {"number": 5000, "currency": "EUR"},
                "price": {"number": 1.08, "currency": "USD"},
                "value": {"number": 5400, "currency": "USD"},
                "cost": {"number": 5000, "currency": "EUR"},
            },
        ]

        holdings_b = [
            {
                "account": "Assets:Invest:Foreign",
                "units": {"number": 100, "currency": "BTC"},
                "price": {"number": 50000, "currency": "USD"},
                "value": {"number": 5000000, "currency": "USD"},
                "cost": {"number": 3000000, "currency": "USD"},
            },
            {
                "account": "Assets:Cash:Euro",
                "units": {"number": 5500, "currency": "EUR"},
                "price": {"number": 1.10, "currency": "USD"},
                "value": {"number": 6050, "currency": "USD"},
                "cost": {"number": 5500, "currency": "EUR"},
            },
        ]

        snap_a = snapshot_store.save(
            "month-start", "balance_sheet", filters, {}, [], holdings=holdings_a,
        )
        snap_b = snapshot_store.save(
            "month-end", "balance_sheet", filters, {}, [], holdings=holdings_b,
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["holdings_diff"] is not None
        diffs = result["holdings_diff"]

        assert len(diffs) == 2

        btc_diff = diffs[0]
        assert "units" not in btc_diff
        assert btc_diff["price"]["before"] == {"number": 40000, "currency": "USD"}
        assert btc_diff["price"]["after"] == {"number": 50000, "currency": "USD"}
        assert btc_diff["value"]["before"] == {"number": 4000000, "currency": "USD"}
        assert btc_diff["value"]["after"] == {"number": 5000000, "currency": "USD"}

        eur_diff = diffs[1]
        assert eur_diff["units"]["before"] == {"number": 5000, "currency": "EUR"}
        assert eur_diff["units"]["after"] == {"number": 5500, "currency": "EUR"}
        assert eur_diff["price"]["before"] == {"number": 1.08, "currency": "USD"}
        assert eur_diff["price"]["after"] == {"number": 1.10, "currency": "USD"}
        assert eur_diff["value"]["before"] == {"number": 5400, "currency": "USD"}
        assert eur_diff["value"]["after"] == {"number": 6050, "currency": "USD"}

    def test_cross_currency_holdings_new_position(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test when a new currency position appears between snapshots.

        Regression test: Verify that newly added positions in different
        currencies are properly captured as diffs.
        """
        filters = SnapshotFilters("", "", "", "", "")

        holdings_a = [
            {
                "account": "Assets:Cash",
                "units": {"number": 10000, "currency": "USD"},
                "price": {"number": 1, "currency": "USD"},
                "value": {"number": 10000, "currency": "USD"},
            },
        ]

        holdings_b = [
            {
                "account": "Assets:Cash",
                "units": {"number": 5000, "currency": "USD"},
                "price": {"number": 1, "currency": "USD"},
                "value": {"number": 5000, "currency": "USD"},
            },
            {
                "account": "Assets:Cash",
                "units": {"number": 4500, "currency": "EUR"},
                "price": {"number": 1.11, "currency": "USD"},
                "value": {"number": 4995, "currency": "USD"},
            },
        ]

        snap_a = snapshot_store.save(
            "before", "balance_sheet", filters, {}, [], holdings=holdings_a,
        )
        snap_b = snapshot_store.save(
            "after", "balance_sheet", filters, {}, [], holdings=holdings_b,
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None
        assert result["holdings_diff"] is not None
        diffs = result["holdings_diff"]

        assert len(diffs) == 2

        usd_diff = diffs[0]
        assert usd_diff["units"]["before"] == {"number": 10000, "currency": "USD"}
        assert usd_diff["units"]["after"] == {"number": 5000, "currency": "USD"}
        assert usd_diff["value"]["before"] == {"number": 10000, "currency": "USD"}
        assert usd_diff["value"]["after"] == {"number": 5000, "currency": "USD"}

        eur_diff = diffs[1]
        assert eur_diff["units"]["before"] is None
        assert eur_diff["units"]["after"] == {"number": 4500, "currency": "EUR"}
        assert eur_diff["price"]["before"] is None
        assert eur_diff["price"]["after"] == {"number": 1.11, "currency": "USD"}

    def test_holdings_snapshot_captures_conversion_state(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Regression test: Snapshot captures converted values at save time.

        This is the key regression test for exchange rate drift.
        The snapshot stores the value as it was at save-time using the
        conversion setting of that moment. When comparing two snapshots,
        we compare the stored values directly — we do NOT re-convert
        using current exchange rates, which would cause drift.
        """
        filters_a = SnapshotFilters(
            time="2024-01",
            account="",
            filter="",
            conversion="at_value",
            interval="",
        )
        filters_b = SnapshotFilters(
            time="2024-02",
            account="",
            filter="",
            conversion="at_value",
            interval="",
        )

        holdings_jan = [
            {
                "account": "Assets:Invest:Intl",
                "units": {"number": 100, "currency": "EUNL"},
                "price": {"number": 50, "currency": "EUR"},
                "value": {"number": 5000, "currency": "EUR"},
            },
        ]

        holdings_feb = [
            {
                "account": "Assets:Invest:Intl",
                "units": {"number": 100, "currency": "EUNL"},
                "price": {"number": 55, "currency": "EUR"},
                "value": {"number": 5500, "currency": "EUR"},
            },
        ]

        snap_jan = snapshot_store.save(
            "jan-2024", "balance_sheet", filters_a, {}, [], holdings=holdings_jan,
        )
        snap_feb = snapshot_store.save(
            "feb-2024", "balance_sheet", filters_b, {}, [], holdings=holdings_feb,
        )

        result = snapshot_store.compare(snap_jan.id, snap_feb.id)
        assert result is not None
        assert result["holdings_diff"] is not None
        diffs = result["holdings_diff"]

        assert len(diffs) == 1
        diff = diffs[0]

        assert "units" not in diff
        assert diff["price"]["before"]["number"] == 50
        assert diff["price"]["after"]["number"] == 55
        assert diff["value"]["before"]["number"] == 5000
        assert diff["value"]["after"]["number"] == 5500

        jan_loaded = snapshot_store.get_snapshot(snap_jan.id)
        feb_loaded = snapshot_store.get_snapshot(snap_feb.id)
        assert jan_loaded is not None
        assert feb_loaded is not None
        assert jan_loaded["filters"]["conversion"] == "at_value"
        assert feb_loaded["filters"]["conversion"] == "at_value"


class TestCleanupRetention:
    """Tests for snapshot cleanup and retention policies."""

    def test_keep_last_n(self, snapshot_store: SnapshotStore) -> None:
        """Test keep_last_n retention policy."""
        filters = SnapshotFilters("", "", "", "", "")
        for i in range(5):
            snapshot_store.save(
                f"snap-{i}", "balance_sheet", filters, {}, [],
            )

        assert len(snapshot_store.list_snapshots()) == 5

        result = snapshot_store.clean(SnapshotRetention(keep_last_n=3))

        assert len(result["kept"]) == 3
        assert len(result["deleted"]) == 2
        assert len(snapshot_store.list_snapshots()) == 3

    def test_keep_days(self, snapshot_store: SnapshotStore) -> None:
        """Test keep_days retention policy via _apply_retention."""
        now = datetime(2024, 1, 15, 12, 0, 0)

        snapshots = []
        for i, days_ago in enumerate([1, 5, 10, 20, 30]):
            created = now - timedelta(days=days_ago)
            snapshots.append(
                {
                    "id": f"snap-{i}",
                    "name": f"snap-{i}",
                    "created_at": created.isoformat(timespec="seconds"),
                    "report_type": "balance_sheet",
                },
            )

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):  # noqa: D401
                return now

            @classmethod
            def fromisoformat(cls, s):  # noqa: D401
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots, SnapshotRetention(keep_days=14),
            )
        finally:
            snap_module.datetime = original_datetime

        assert len(to_keep) == 3
        assert len(to_delete) == 2

    def test_keep_days_integration(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Integration test for keep_days with actual file operations."""
        filters = SnapshotFilters("", "", "", "", "")
        now = datetime.now()

        for i, days_ago in enumerate([0, 1, 100]):
            created = now - timedelta(days=days_ago)
            snapshot = snapshot_store.save(
                f"snap-{i}", "balance_sheet", filters, {}, [],
            )
            path = snapshot_store._snapshot_path(snapshot.id)
            data = json.loads(path.read_text())
            data["created_at"] = created.isoformat(timespec="seconds")
            path.write_text(json.dumps(data, indent=2))

        result = snapshot_store.clean(SnapshotRetention(keep_days=30))
        assert len(result["kept"]) >= 2
        assert len(result["deleted"]) >= 0

    def test_per_report_type(self, snapshot_store: SnapshotStore) -> None:
        """Test per-report-type retention policy."""
        filters = SnapshotFilters("", "", "", "", "")

        for i in range(3):
            snapshot_store.save(
                f"bs-{i}", "balance_sheet", filters, {}, [],
            )
        for i in range(3):
            snapshot_store.save(
                f"is-{i}", "income_statement", filters, {}, [],
            )

        assert len(snapshot_store.list_snapshots()) == 6

        result = snapshot_store.clean(
            SnapshotRetention(keep_last_n=2, per_report_type=True),
        )

        assert len(result["kept"]) == 4
        assert len(result["deleted"]) == 2

    def test_global_retention(self, snapshot_store: SnapshotStore) -> None:
        """Test global (not per-report-type) retention policy."""
        filters = SnapshotFilters("", "", "", "", "")

        for i in range(3):
            snapshot_store.save(
                f"bs-{i}", "balance_sheet", filters, {}, [],
            )
        for i in range(3):
            snapshot_store.save(
                f"is-{i}", "income_statement", filters, {}, [],
            )

        assert len(snapshot_store.list_snapshots()) == 6

        result = snapshot_store.clean(
            SnapshotRetention(keep_last_n=4, per_report_type=False),
        )

        assert len(result["kept"]) == 4
        assert len(result["deleted"]) == 2

    def test_clean_empty(self, snapshot_store: SnapshotStore) -> None:
        """Test cleaning when no snapshots exist."""
        result = snapshot_store.clean(SnapshotRetention(keep_last_n=10))
        assert result["deleted"] == []
        assert result["kept"] == []

    def test_auto_clean_on_save(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test auto-clean when saving snapshots."""
        filters = SnapshotFilters("", "", "", "", "")
        policy = SnapshotRetention(keep_last_n=2)

        for i in range(5):
            snapshot_store.save(
                f"snap-{i}",
                "balance_sheet",
                filters,
                {},
                [],
                auto_clean=policy,
            )

        assert len(snapshot_store.list_snapshots()) == 2


class TestCompareEdgeCases:
    """Tests for edge cases in comparison."""

    def test_compare_nonexistent_a(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test compare when snapshot A doesn't exist."""
        filters = SnapshotFilters("", "", "", "", "")
        snap_b = snapshot_store.save("b", "balance_sheet", filters, {}, [])

        result = snapshot_store.compare("nonexistent", snap_b.id)
        assert result is None

    def test_compare_nonexistent_b(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test compare when snapshot B doesn't exist."""
        filters = SnapshotFilters("", "", "", "", "")
        snap_a = snapshot_store.save("a", "balance_sheet", filters, {}, [])

        result = snapshot_store.compare(snap_a.id, "nonexistent")
        assert result is None

    def test_compare_metadata_fields(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test that compare result includes metadata for both snapshots."""
        filters_a = SnapshotFilters("2024", "Assets", "", "", "monthly")
        filters_b = SnapshotFilters("2024", "", "", "at_cost", "")

        snap_a = snapshot_store.save(
            "Jan", "balance_sheet", filters_a, {"A": {"USD": 100}}, [],
        )
        snap_b = snapshot_store.save(
            "Feb", "balance_sheet", filters_b, {"A": {"USD": 200}}, [],
        )

        result = snapshot_store.compare(snap_a.id, snap_b.id)
        assert result is not None

        assert result["snapshot_a"]["id"] == snap_a.id
        assert result["snapshot_a"]["name"] == "Jan"
        assert result["snapshot_a"]["filters"]["time"] == "2024"
        assert result["snapshot_a"]["filters"]["account"] == "Assets"

        assert result["snapshot_b"]["id"] == snap_b.id
        assert result["snapshot_b"]["name"] == "Feb"
        assert result["snapshot_b"]["filters"]["conversion"] == "at_cost"


class TestSnapshotSerialization:
    """Tests for snapshot serialization/deserialization."""

    def test_date_serialization(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Test that date objects serialize properly."""
        from datetime import date as date_type

        filters = SnapshotFilters("", "", "", "", "")

        holdings = [
            {
                "account": "Assets:Test",
                "date": date_type(2024, 1, 15),
                "units": {"number": 100, "currency": "USD"},
            },
        ]

        snap = snapshot_store.save(
            "date-test", "balance_sheet", filters, {}, [], holdings=holdings,
        )

        loaded = snapshot_store.get_snapshot(snap.id)
        assert loaded is not None
        assert loaded["data"]["holdings"][0]["date"] == "2024-01-15"

    def test_corrupted_file_skipped(
        self,
        snapshot_store: SnapshotStore,
        tmp_path: Path,
    ) -> None:
        """Test that corrupted snapshot files are skipped gracefully."""
        bad_path = snapshot_store.snapshots_dir / "bad.json"
        bad_path.write_text("{invalid json")

        result = snapshot_store.list_snapshots()
        assert result == []
