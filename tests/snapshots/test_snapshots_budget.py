"""Tests for budget comparison logic."""

from __future__ import annotations

import pytest

from fava.core.snapshots import SnapshotFilters
from fava.core.snapshots import SnapshotStore


class TestBudgetComparison:
    """Tests for budget difference computation."""

    def test_budget_diff_simple(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
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

    def test_budget_diff_multiple_periods(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        filters = SnapshotFilters("", "", "", "", "")
        budgets_a = {
            "Expenses:Food": [
                {"budget": {"USD": 500}, "budget_children": {}},
                {"budget": {"USD": 550}, "budget_children": {}},
            ],
        }
        budgets_b = {
            "Expenses:Food": [
                {"budget": {"USD": 600}, "budget_children": {}},
                {"budget": {"USD": 550}, "budget_children": {}},
            ],
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

        diffs = result["budget_diff"]["Expenses:Food"]
        assert len(diffs) == 1
        assert diffs[0]["budget_diff"]["USD"] == pytest.approx(100)

    def test_budget_diff_new_account(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        filters = SnapshotFilters("", "", "", "", "")
        budgets_a = {
            "Expenses:Food": [{"budget": {"USD": 500}, "budget_children": {}}],
        }
        budgets_b = {
            "Expenses:Food": [{"budget": {"USD": 500}, "budget_children": {}}],
            "Expenses:Transport": [
                {"budget": {"EUR": 200}, "budget_children": {}},
            ],
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
        assert "Expenses:Transport" in result["budget_diff"]
