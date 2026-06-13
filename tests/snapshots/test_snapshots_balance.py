"""Tests for balance comparison logic."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from fava.core.snapshots import SnapshotFilters
from fava.core.snapshots import SnapshotStore


class TestBalanceComparison:
    """Tests for balance difference computation."""

    def test_balance_diff_no_change(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
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


class TestCompareEdgeCases:
    """Edge-case tests for snapshot comparison relevant to balance reports."""

    def test_compare_nonexistent_a(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        filters = SnapshotFilters("", "", "", "", "")
        snap_b = snapshot_store.save("b", "balance_sheet", filters, {}, [])

        result = snapshot_store.compare("nonexistent", snap_b.id)
        assert result is None

    def test_compare_nonexistent_b(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        filters = SnapshotFilters("", "", "", "", "")
        snap_a = snapshot_store.save("a", "balance_sheet", filters, {}, [])

        result = snapshot_store.compare(snap_a.id, "nonexistent")
        assert result is None

    def test_compare_metadata_fields(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
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
