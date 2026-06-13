"""Tests for snapshot store operations (save, load, list, delete, serialize)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fava.core.snapshots import SnapshotFilters
from fava.core.snapshots import SnapshotStore


class TestSaveAndLoad:
    """Tests for saving and loading snapshots."""

    def test_save_snapshot(self, snapshot_store: SnapshotStore) -> None:
        filters = SnapshotFilters(
            time="2024",
            account="",
            filter="",
            conversion="",
            interval="",
        )
        balances = {"Assets:Cash": {"USD": Decimal("1000")}}

        snapshot = snapshot_store.save(
            name="test snapshot",
            report_type="balance_sheet",
            filters=filters,
            balances=balances,
            trees=[],
        )

        assert snapshot.id is not None
        assert len(snapshot.id) == 12
        assert snapshot.name == "test snapshot"
        assert snapshot.data.report_type == "balance_sheet"

    def test_list_snapshots_empty(self, snapshot_store: SnapshotStore) -> None:
        result = snapshot_store.list_snapshots()
        assert result == []

    def test_list_snapshots(self, snapshot_store: SnapshotStore) -> None:
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
        result = snapshot_store.get_snapshot("nonexistent")
        assert result is None

    def test_delete_snapshot(self, snapshot_store: SnapshotStore) -> None:
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
        assert snapshot_store.delete("nonexistent") is False

    def test_save_with_decimal_serialization(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
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

    def test_date_serialization(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        filters = SnapshotFilters("", "", "", "", "")

        holdings = [
            {
                "account": "Assets:Test",
                "date": date(2024, 1, 15),
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
    ) -> None:
        bad_path = snapshot_store.snapshots_dir / "bad.json"
        bad_path.write_text("{invalid json")

        result = snapshot_store.list_snapshots()
        assert result == []

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
