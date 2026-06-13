"""Tests for snapshot retention and cleanup policies."""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timedelta

import pytest

from fava.core.snapshots import SnapshotFilters
from fava.core.snapshots import SnapshotRetention
from fava.core.snapshots import SnapshotStore


class TestSnapshotRetentionValidation:
    """Tests for SnapshotRetention dataclass validation."""

    def test_validate_keep_last_n_valid(self) -> None:
        policy = SnapshotRetention(keep_last_n=10)
        policy.validate()

    def test_validate_keep_days_valid(self) -> None:
        policy = SnapshotRetention(keep_days=30)
        policy.validate()

    def test_validate_both_valid(self) -> None:
        policy = SnapshotRetention(keep_last_n=5, keep_days=30)
        policy.validate()

    def test_validate_negative_keep_last_n(self) -> None:
        policy = SnapshotRetention(keep_last_n=-1)
        with pytest.raises(ValueError, match="keep_last_n must be non-negative"):
            policy.validate()

    def test_validate_negative_keep_days(self) -> None:
        policy = SnapshotRetention(keep_days=-1)
        with pytest.raises(ValueError, match="keep_days must be non-negative"):
            policy.validate()

    def test_validate_no_policy(self) -> None:
        policy = SnapshotRetention()
        with pytest.raises(ValueError, match="At least one of"):
            policy.validate()

    def test_validate_zero_keep_last_n(self) -> None:
        policy = SnapshotRetention(keep_last_n=0)
        with pytest.raises(ValueError, match="At least one of"):
            policy.validate()

    def test_validate_zero_keep_days(self) -> None:
        policy = SnapshotRetention(keep_days=0)
        with pytest.raises(ValueError, match="At least one of"):
            policy.validate()

    def test_validate_negative_archive_per_month(self) -> None:
        policy = SnapshotRetention(keep_days=30, archive_per_month=-1)
        with pytest.raises(ValueError, match="archive_per_month must be non-negative"):
            policy.validate()


class TestKeepLastN:
    """Tests for keep_last_n retention policy."""

    def test_keep_last_n(self, snapshot_store: SnapshotStore) -> None:
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

    def test_per_report_type(self, snapshot_store: SnapshotStore) -> None:
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


class TestKeepDays:
    """Tests for keep_days (time window) retention policy."""

    def _apply_with_mocked_now(
        self,
        snapshots: list[dict],
        retention: SnapshotRetention,
        now: datetime,
    ) -> tuple[set[str], set[str]]:
        """Helper to run _apply_retention with a mocked datetime.now()."""
        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            return SnapshotStore._apply_retention(snapshots, retention)
        finally:
            snap_module.datetime = original_datetime

    def test_keep_days_via_apply_retention(self) -> None:
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

        to_delete, to_keep = self._apply_with_mocked_now(
            snapshots, SnapshotRetention(keep_days=14), now,
        )

        assert len(to_keep) == 3
        assert len(to_delete) == 2

    def test_keep_days_integration(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
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


class TestKeepDaysBoundaryConditions:
    """Edge-case tests for time-window retention at exact cutoff boundaries.

    The implementation uses `created >= cutoff` for "keep" and
    `created < cutoff` for "delete/archive". When a snapshot's created_at
    is exactly equal to the cutoff timestamp, it is kept.
    """

    def test_snapshot_exactly_at_cutoff_is_kept(self) -> None:
        """Snapshot created at exactly the cutoff moment is kept (>=)."""
        now = datetime(2024, 6, 15, 12, 0, 0)
        cutoff = now - timedelta(days=30)

        snapshots = [
            {
                "id": "snap-at-cutoff",
                "name": "at-cutoff",
                "created_at": cutoff.isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
        ]

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots, SnapshotRetention(keep_days=30),
            )
        finally:
            snap_module.datetime = original_datetime

        assert "snap-at-cutoff" in to_keep
        assert "snap-at-cutoff" not in to_delete

    def test_snapshot_one_second_before_cutoff_is_deleted(self) -> None:
        """Snapshot one second before the cutoff is deleted (<)."""
        now = datetime(2024, 6, 15, 12, 0, 0)
        cutoff = now - timedelta(days=30)
        one_second_before = cutoff - timedelta(seconds=1)

        snapshots = [
            {
                "id": "snap-before-cutoff",
                "name": "before-cutoff",
                "created_at": one_second_before.isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
        ]

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots, SnapshotRetention(keep_days=30),
            )
        finally:
            snap_module.datetime = original_datetime

        assert "snap-before-cutoff" in to_delete
        assert "snap-before-cutoff" not in to_keep

    def test_snapshot_one_second_after_cutoff_is_kept(self) -> None:
        """Snapshot one second after the cutoff is kept (>=)."""
        now = datetime(2024, 6, 15, 12, 0, 0)
        cutoff = now - timedelta(days=30)
        one_second_after = cutoff + timedelta(seconds=1)

        snapshots = [
            {
                "id": "snap-after-cutoff",
                "name": "after-cutoff",
                "created_at": one_second_after.isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
        ]

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots, SnapshotRetention(keep_days=30),
            )
        finally:
            snap_module.datetime = original_datetime

        assert "snap-after-cutoff" in to_keep
        assert "snap-after-cutoff" not in to_delete

    def test_midnight_boundary_crossing(self) -> None:
        """Snapshots across a midnight boundary with keep_days=1.

        If now is 2024-06-15T00:00:01, keep_days=1 means cutoff is
        2024-06-14T00:00:01. A snapshot created at 2024-06-13T23:59:59
        is before cutoff (deleted), while one at 2024-06-14T00:00:01
        is at cutoff (kept).
        """
        now = datetime(2024, 6, 15, 0, 0, 1)
        cutoff = now - timedelta(days=1)

        snapshots = [
            {
                "id": "snap-just-before-midnight",
                "name": "just-before",
                "created_at": (cutoff - timedelta(seconds=2)).isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
            {
                "id": "snap-at-cutoff-midnight",
                "name": "at-cutoff",
                "created_at": cutoff.isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
            {
                "id": "snap-after-midnight",
                "name": "after-midnight",
                "created_at": (cutoff + timedelta(seconds=2)).isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
        ]

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots, SnapshotRetention(keep_days=1),
            )
        finally:
            snap_module.datetime = original_datetime

        assert "snap-just-before-midnight" in to_delete
        assert "snap-at-cutoff-midnight" in to_keep
        assert "snap-after-midnight" in to_keep

    def test_archive_per_month_boundary_snapshot_at_cutoff(self) -> None:
        """With archive_per_month, a snapshot exactly at the cutoff is recent (kept)."""
        now = datetime(2024, 6, 15, 12, 0, 0)
        cutoff = now - timedelta(days=30)

        snapshots = [
            {
                "id": "snap-at-cutoff",
                "name": "at-cutoff",
                "created_at": cutoff.isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
            {
                "id": "snap-before-cutoff",
                "name": "before-cutoff",
                "created_at": (cutoff - timedelta(seconds=1)).isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
        ]

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots,
                SnapshotRetention(keep_days=30, archive_per_month=1),
            )
        finally:
            snap_module.datetime = original_datetime

        assert "snap-at-cutoff" in to_keep
        assert "snap-before-cutoff" in to_keep

    def test_cutoff_at_month_boundary(self) -> None:
        """Cutoff falls exactly on a month boundary (1st of month 00:00).

        A snapshot created at 2024-05-01T00:00:00 when cutoff is
        2024-05-01T00:00:00 should be kept (>=).
        """
        now = datetime(2024, 6, 1, 0, 0, 0)
        cutoff = now - timedelta(days=31)

        snapshots = [
            {
                "id": "snap-at-month-start",
                "name": "month-start",
                "created_at": cutoff.isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
            {
                "id": "snap-before-month-start",
                "name": "before-month-start",
                "created_at": (cutoff - timedelta(seconds=1)).isoformat(timespec="seconds"),
                "report_type": "balance_sheet",
            },
        ]

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots, SnapshotRetention(keep_days=31),
            )
        finally:
            snap_module.datetime = original_datetime

        assert "snap-at-month-start" in to_keep
        assert "snap-before-month-start" in to_delete


class TestArchiveMonthly:
    """Tests for monthly archive retention policy.

    The archive_per_month policy keeps the most recent N days of snapshots
    intact, and for older snapshots only retains up to M per calendar month.
    This is useful for businesses that need to maintain a monthly audit trail
    while keeping recent snapshots fully available.
    """

    def _make_monthly_snapshots(
        self,
        now: datetime,
    ) -> list[dict]:
        """Create snapshot metadata spanning several months.

        Layout (relative to now=2024-06-15):
          - 2 days ago, 5 days ago        (recent, within keep_days=30)
          - 35 days ago, 40 days ago       (May - 2 snapshots)
          - 65 days ago, 70 days ago, 75 days ago  (April - 3 snapshots)
          - 95 days ago                     (March - 1 snapshot)
        """
        snapshots = []
        offsets = [2, 5, 35, 40, 65, 70, 75, 95]
        for i, days_ago in enumerate(offsets):
            created = now - timedelta(days=days_ago)
            snapshots.append(
                {
                    "id": f"snap-{i}",
                    "name": f"snap-{i}",
                    "created_at": created.isoformat(timespec="seconds"),
                    "report_type": "balance_sheet",
                },
            )
        return snapshots

    def test_archive_per_month_keeps_recent_and_archives_older(self) -> None:
        """Test that recent snapshots are kept and older ones are archived per month."""
        now = datetime(2024, 6, 15, 12, 0, 0)
        snapshots = self._make_monthly_snapshots(now)

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots,
                SnapshotRetention(keep_days=30, archive_per_month=1),
            )
        finally:
            snap_module.datetime = original_datetime

        assert f"snap-0" in to_keep
        assert f"snap-1" in to_keep

        assert f"snap-2" in to_keep
        assert f"snap-3" in to_delete

        assert f"snap-4" in to_keep
        assert f"snap-5" in to_delete
        assert f"snap-6" in to_delete

        assert f"snap-7" in to_keep

    def test_archive_per_month_2_keeps_more(self) -> None:
        """Test archive_per_month=2 keeps up to 2 per older month."""
        now = datetime(2024, 6, 15, 12, 0, 0)
        snapshots = self._make_monthly_snapshots(now)

        import fava.core.snapshots as snap_module

        class MockDatetime:
            @classmethod
            def now(cls):
                return now

            @classmethod
            def fromisoformat(cls, s):
                return datetime.fromisoformat(s)

        original_datetime = snap_module.datetime
        snap_module.datetime = MockDatetime
        try:
            to_delete, to_keep = SnapshotStore._apply_retention(
                snapshots,
                SnapshotRetention(keep_days=30, archive_per_month=2),
            )
        finally:
            snap_module.datetime = original_datetime

        assert f"snap-0" in to_keep
        assert f"snap-1" in to_keep

        assert f"snap-2" in to_keep
        assert f"snap-3" in to_keep

        assert f"snap-4" in to_keep
        assert f"snap-5" in to_keep
        assert f"snap-6" in to_delete

        assert f"snap-7" in to_keep

    def test_archive_without_keep_days_raises(self) -> None:
        """Test that archive_per_month without keep_days is invalid."""
        policy = SnapshotRetention(archive_per_month=1)
        with pytest.raises(ValueError, match="archive_per_month requires keep_days"):
            policy.validate()


class TestCleanIntegration:
    """Integration tests for the clean() method."""

    def test_clean_empty(self, snapshot_store: SnapshotStore) -> None:
        result = snapshot_store.clean(SnapshotRetention(keep_last_n=10))
        assert result["deleted"] == []
        assert result["kept"] == []

    def test_auto_clean_on_save(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
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


class TestConcurrentClean:
    """Tests for concurrent cleanup operations.

    In a multi-user scenario, two requests may trigger clean() simultaneously.
    These tests verify that the clean() method handles race conditions
    gracefully: it should not crash when a file has already been deleted
    by a concurrent operation, and the final state should be consistent.
    """

    def test_concurrent_clean_does_not_crash_on_deleted_file(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Two clean() calls targeting the same snapshots should not crash.

        The first clean() deletes the files; the second clean() reads the
        same meta list but finds the files already gone. It should silently
        skip those files and return a valid result.
        """
        filters = SnapshotFilters("", "", "", "", "")
        for i in range(5):
            snapshot_store.save(
                f"snap-{i}", "balance_sheet", filters, {}, [],
            )

        policy = SnapshotRetention(keep_last_n=2)

        result1 = snapshot_store.clean(policy)

        ids_still_on_disk = set()
        for p in snapshot_store.snapshots_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                ids_still_on_disk.add(data["id"])
            except (json.JSONDecodeError, KeyError):
                pass

        assert len(ids_still_on_disk) == 2, f"Expected 2, got {ids_still_on_disk}"

        result2 = snapshot_store.clean(policy)

        assert isinstance(result2["deleted"], list)
        assert isinstance(result2["kept"], list)

        remaining = snapshot_store.list_snapshots()
        assert len(remaining) == 2

    def test_concurrent_clean_with_interleaved_save(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """A save() interleaved between two clean() calls should be preserved.

        Simulates: User A starts clean, User B saves a new snapshot,
        User A's clean completes. The new snapshot from User B should survive
        if it's within the retention policy.
        """
        filters = SnapshotFilters("", "", "", "", "")
        for i in range(5):
            snapshot_store.save(
                f"snap-{i}", "balance_sheet", filters, {}, [],
            )

        result1 = snapshot_store.clean(SnapshotRetention(keep_last_n=2))
        assert len(result1["deleted"]) == 3

        new_snap = snapshot_store.save(
            "interleaved", "balance_sheet", filters, {}, [],
        )

        remaining = snapshot_store.list_snapshots()
        ids = {s["id"] for s in remaining}
        assert new_snap.id in ids
        assert len(remaining) == 3

    def test_concurrent_clean_file_removed_between_meta_load_and_delete(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """A file removed externally between _load_all_snapshots_meta and delete.

        Simulates: clean() reads meta and decides to delete snap-X,
        but another process deletes snap-X before clean() can.
        clean() should handle the missing file gracefully (delete returns False).
        """
        filters = SnapshotFilters("", "", "", "", "")
        snapshots = []
        for i in range(3):
            snapshots.append(
                snapshot_store.save(
                    f"snap-{i}", "balance_sheet", filters, {}, [],
                ),
            )

        doomed_path = snapshot_store._snapshot_path(snapshots[0].id)
        assert doomed_path.exists()
        doomed_path.unlink()

        result = snapshot_store.clean(SnapshotRetention(keep_last_n=1))

        assert isinstance(result["deleted"], list)
        assert isinstance(result["kept"], list)

        remaining = snapshot_store.list_snapshots()
        assert len(remaining) == 1

    def test_concurrent_clean_idempotent(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
        """Running the same clean() twice should be idempotent.

        After the first clean, running the same policy again should
        delete nothing and keep the same set.
        """
        filters = SnapshotFilters("", "", "", "", "")
        for i in range(5):
            snapshot_store.save(
                f"snap-{i}", "balance_sheet", filters, {}, [],
            )

        policy = SnapshotRetention(keep_last_n=2)
        result1 = snapshot_store.clean(policy)

        result2 = snapshot_store.clean(policy)

        assert result2["deleted"] == []
        assert len(result2["kept"]) == 2
        assert len(snapshot_store.list_snapshots()) == 2
