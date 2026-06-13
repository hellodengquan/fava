"""Snapshot storage for report comparison."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

from fava.core.module_base import FavaModule

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping
    from collections.abc import Sequence

    from fava.core import FavaLedger
    from fava.core.inventory import SimpleCounterInventory
    from fava.core.tree import SerialisedTreeNode

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotRetention:
    """Snapshot retention policy configuration.

    Attributes:
        keep_last_n: Keep the N most recent snapshots per report type.
                     0 or None means no limit.
        keep_days: Keep snapshots created within the last N days.
                   0 or None means no limit.
        per_report_type: Whether the retention policy applies per report type
                         or globally across all report types.
    """

    keep_last_n: int | None = None
    keep_days: int | None = None
    per_report_type: bool = True

    def validate(self) -> None:
        """Validate the retention policy configuration."""
        if self.keep_last_n is not None and self.keep_last_n < 0:
            raise ValueError("keep_last_n must be non-negative")
        if self.keep_days is not None and self.keep_days < 0:
            raise ValueError("keep_days must be non-negative")
        if (
            self.keep_last_n in (None, 0)
            and self.keep_days in (None, 0)
        ):
            raise ValueError(
                "At least one of keep_last_n or keep_days must be set",
            )


@dataclass(frozen=True)
class SnapshotFilters:
    """The filters used when creating a snapshot."""

    time: str
    account: str
    filter: str
    conversion: str
    interval: str


@dataclass(frozen=True)
class SnapshotData:
    """The data captured in a snapshot."""

    report_type: str
    balances: Mapping[str, SimpleCounterInventory]
    trees: Sequence[SerialisedTreeNode]
    budgets: Mapping[str, Sequence[Mapping[str, Any]]] | None
    holdings: Sequence[Mapping[str, Any]] | None


@dataclass
class Snapshot:
    """A report snapshot."""

    id: str
    name: str
    created_at: str
    filters: SnapshotFilters
    data: SnapshotData


class SnapshotStore(FavaModule):
    """Manage report snapshots for a ledger."""

    def __init__(self, ledger: FavaLedger) -> None:
        super().__init__(ledger)
        self._snapshots_dir: Path | None = None

    @property
    def snapshots_dir(self) -> Path:
        """Get the snapshots directory, creating it if needed."""
        if self._snapshots_dir is None:
            self._snapshots_dir = (
                Path(self.ledger.beancount_file_path).parent
                / ".fava-snapshots"
            )
        return self._snapshots_dir

    def _snapshot_path(self, snapshot_id: str) -> Path:
        """Get the file path for a snapshot."""
        return self.snapshots_dir / f"{snapshot_id}.json"

    def load_file(self) -> None:
        """Ensure snapshots directory exists."""
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        name: str,
        report_type: str,
        filters: SnapshotFilters,
        balances: Mapping[str, SimpleCounterInventory],
        trees: Sequence[SerialisedTreeNode],
        budgets: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        holdings: Sequence[Mapping[str, Any]] | None = None,
        auto_clean: SnapshotRetention | None = None,
    ) -> Snapshot:
        """Save a new snapshot.

        Args:
            name: Name of the snapshot.
            report_type: Type of report the snapshot is for.
            filters: Filters used when creating the snapshot.
            balances: Account balances map.
            trees: Serialised tree nodes.
            budgets: Budget data (optional).
            holdings: Holdings data (optional).
            auto_clean: Optional retention policy to apply after saving.

        Returns:
            The saved snapshot.
        """
        snapshot_id = uuid.uuid4().hex[:12]
        created_at = datetime.now().isoformat(timespec="seconds")
        data = SnapshotData(
            report_type=report_type,
            balances=balances,
            trees=trees,
            budgets=budgets,
            holdings=holdings,
        )
        snapshot = Snapshot(
            id=snapshot_id,
            name=name,
            created_at=created_at,
            filters=filters,
            data=data,
        )
        self._write_snapshot(snapshot)

        if auto_clean is not None:
            self.clean(auto_clean)

        return snapshot

    def _write_snapshot(self, snapshot: Snapshot) -> None:
        """Write a snapshot to disk."""
        path = self._snapshot_path(snapshot.id)

        def _default(obj: Any) -> Any:
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            if hasattr(obj, "__dataclass_fields__"):
                return asdict(obj)
            if hasattr(obj, "items"):
                return dict(obj)
            raise TypeError(f"Object of type {type(obj)} is not serializable")

        data = asdict(snapshot)
        path.write_text(
            json.dumps(data, default=_default, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list_snapshots(self) -> Sequence[Mapping[str, Any]]:
        """List all snapshots (metadata only, without full data)."""
        snapshots: list[Mapping[str, Any]] = []
        if not self.snapshots_dir.exists():
            return snapshots
        for path in sorted(self.snapshots_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                snapshots.append(
                    {
                        "id": raw["id"],
                        "name": raw["name"],
                        "created_at": raw["created_at"],
                        "filters": raw["filters"],
                        "report_type": raw["data"]["report_type"],
                    },
                )
            except (json.JSONDecodeError, KeyError):
                log.warning("Failed to read snapshot file: %s", path)
        return snapshots

    def get_snapshot(self, snapshot_id: str) -> Mapping[str, Any] | None:
        """Get a full snapshot by ID."""
        path = self._snapshot_path(snapshot_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot by ID."""
        path = self._snapshot_path(snapshot_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def clean(self, retention: SnapshotRetention) -> dict[str, Any]:
        """Clean up snapshots according to the retention policy.

        Args:
            retention: The retention policy to apply.

        Returns:
            A dict with 'deleted' (list of deleted snapshot IDs)
            and 'kept' (list of kept snapshot IDs).
        """
        retention.validate()

        all_snapshots = self._load_all_snapshots_meta()
        if not all_snapshots:
            return {"deleted": [], "kept": []}

        to_delete: set[str] = set()
        to_keep: set[str] = set()

        if retention.per_report_type:
            by_type: dict[str, list[Mapping[str, Any]]] = {}
            for snap in all_snapshots:
                rtype = snap.get("report_type", "unknown")
                by_type.setdefault(rtype, []).append(snap)
            for snaps in by_type.values():
                d, k = self._apply_retention(snaps, retention)
                to_delete.update(d)
                to_keep.update(k)
        else:
            d, k = self._apply_retention(all_snapshots, retention)
            to_delete.update(d)
            to_keep.update(k)

        deleted = []
        for sid in to_delete:
            if self.delete(sid):
                deleted.append(sid)

        return {
            "deleted": sorted(deleted),
            "kept": sorted(to_keep - to_delete),
        }

    def _load_all_snapshots_meta(
        self,
    ) -> list[Mapping[str, Any]]:
        """Load metadata for all snapshots, sorted by created_at desc."""
        snapshots = []
        if not self.snapshots_dir.exists():
            return snapshots
        for path in self.snapshots_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                snapshots.append(
                    {
                        "id": raw["id"],
                        "name": raw["name"],
                        "created_at": raw["created_at"],
                        "report_type": raw["data"]["report_type"],
                    },
                )
            except (json.JSONDecodeError, KeyError):
                log.warning("Failed to read snapshot file: %s", path)
        snapshots.sort(key=lambda s: s["created_at"], reverse=True)
        return snapshots

    @staticmethod
    def _apply_retention(
        snapshots: Sequence[Mapping[str, Any]],
        retention: SnapshotRetention,
    ) -> tuple[set[str], set[str]]:
        """Apply retention policy to a list of snapshots.

        Args:
            snapshots: List of snapshot metadata dicts, sorted newest first.
            retention: The retention policy.

        Returns:
            Tuple of (to_delete set, to_keep set) of snapshot IDs.
        """
        to_keep: set[str] = set()
        to_delete: set[str] = set()

        if not snapshots:
            return to_delete, to_keep

        if retention.keep_last_n and retention.keep_last_n > 0:
            for i, snap in enumerate(snapshots):
                if i < retention.keep_last_n:
                    to_keep.add(snap["id"])
                else:
                    to_delete.add(snap["id"])
        else:
            for snap in snapshots:
                to_keep.add(snap["id"])

        if retention.keep_days and retention.keep_days > 0:
            cutoff = datetime.now() - timedelta(days=retention.keep_days)
            for snap in snapshots:
                sid = snap["id"]
                try:
                    created = datetime.fromisoformat(snap["created_at"])
                except (ValueError, KeyError):
                    continue
                if created < cutoff:
                    to_delete.add(sid)
                    to_keep.discard(sid)
                else:
                    to_keep.add(sid)

        return to_delete, to_keep

    def compare(
        self,
        snapshot_id_a: str,
        snapshot_id_b: str,
    ) -> Mapping[str, Any] | None:
        """Compare two snapshots and return the differences."""
        snap_a = self.get_snapshot(snapshot_id_a)
        snap_b = self.get_snapshot(snapshot_id_b)
        if snap_a is None or snap_b is None:
            return None

        balances_a = snap_a["data"].get("balances", {})
        balances_b = snap_b["data"].get("balances", {})
        balance_diff = self._compute_balance_diff(balances_a, balances_b)

        trees_a = snap_a["data"].get("trees", [])
        trees_b = snap_b["data"].get("trees", [])
        tree_diff = self._compute_tree_diff(trees_a, trees_b)

        budgets_a = snap_a["data"].get("budgets")
        budgets_b = snap_b["data"].get("budgets")
        budget_diff = None
        if budgets_a is not None and budgets_b is not None:
            budget_diff = self._compute_budget_diff(budgets_a, budgets_b)

        holdings_a = snap_a["data"].get("holdings")
        holdings_b = snap_b["data"].get("holdings")
        holdings_diff = None
        if holdings_a is not None and holdings_b is not None:
            holdings_diff = self._compute_holdings_diff(holdings_a, holdings_b)

        return {
            "snapshot_a": {
                "id": snap_a["id"],
                "name": snap_a["name"],
                "created_at": snap_a["created_at"],
                "filters": snap_a["filters"],
            },
            "snapshot_b": {
                "id": snap_b["id"],
                "name": snap_b["name"],
                "created_at": snap_b["created_at"],
                "filters": snap_b["filters"],
            },
            "balance_diff": balance_diff,
            "tree_diff": tree_diff,
            "budget_diff": budget_diff,
            "holdings_diff": holdings_diff,
        }

    @staticmethod
    def _compute_balance_diff(
        balances_a: Mapping[str, Any],
        balances_b: Mapping[str, Any],
    ) -> Mapping[str, Mapping[str, float]]:
        """Compute the difference between two balance maps."""
        all_accounts = set(balances_a.keys()) | set(balances_b.keys())
        result: dict[str, dict[str, float]] = {}
        for account in sorted(all_accounts):
            ba = balances_a.get(account, {})
            bb = balances_b.get(account, {})
            all_currencies = set(ba.keys()) | set(bb.keys())
            diff: dict[str, float] = {}
            for currency in sorted(all_currencies):
                va = ba.get(currency, 0)
                vb = bb.get(currency, 0)
                va = float(va) if va else 0
                vb = float(vb) if vb else 0
                d = vb - va
                if abs(d) > 1e-10:
                    diff[currency] = d
            if diff:
                result[account] = diff
        return result

    @staticmethod
    def _compute_tree_diff(
        trees_a: Sequence[Mapping[str, Any]],
        trees_b: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        """Compute the difference between two tree snapshots."""
        result: list[Mapping[str, Any]] = []
        for tree_a, tree_b in zip(trees_a, trees_b, strict=False):
            diff = SnapshotStore._diff_tree_node(tree_a, tree_b)
            result.append(diff)
        extra = trees_b[len(trees_a) :]
        for tree_b in extra:
            diff = SnapshotStore._diff_tree_node({}, tree_b)
            result.append(diff)
        return result

    @staticmethod
    def _diff_tree_node(
        node_a: Mapping[str, Any],
        node_b: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Recursively diff two tree nodes."""
        balance_a = node_a.get("balance", {})
        balance_b = node_b.get("balance", {})
        balance_children_a = node_a.get("balance_children", {})
        balance_children_b = node_b.get("balance_children", {})
        cost_a = node_a.get("cost")
        cost_b = node_b.get("cost")
        cost_children_a = node_a.get("cost_children")
        cost_children_b = node_b.get("cost_children")

        account = node_b.get("account", node_a.get("account", ""))

        def _diff_inv(
            inv_a: Mapping[str, Any],
            inv_b: Mapping[str, Any],
        ) -> Mapping[str, float]:
            all_currencies = set(inv_a.keys()) | set(inv_b.keys())
            diff: dict[str, float] = {}
            for currency in sorted(all_currencies):
                va = float(inv_a.get(currency, 0) or 0)
                vb = float(inv_b.get(currency, 0) or 0)
                d = vb - va
                if abs(d) > 1e-10:
                    diff[currency] = d
            return diff

        children_a_list = node_a.get("children", [])
        children_b_list = node_b.get("children", [])

        children_by_account_a = {
            c["account"]: c for c in children_a_list if "account" in c
        }
        children_by_account_b = {
            c["account"]: c for c in children_b_list if "account" in c
        }

        all_child_accounts = sorted(
            set(children_by_account_a.keys())
            | set(children_by_account_b.keys()),
        )

        children_diff: list[Mapping[str, Any]] = []
        for child_account in all_child_accounts:
            ca = children_by_account_a.get(child_account, {})
            cb = children_by_account_b.get(child_account, {})
            children_diff.append(
                SnapshotStore._diff_tree_node(ca, cb),
            )

        return {
            "account": account,
            "balance_diff": _diff_inv(balance_a, balance_b),
            "balance_children_diff": _diff_inv(
                balance_children_a,
                balance_children_b,
            ),
            "cost_diff": (
                _diff_inv(cost_a or {}, cost_b or {})
                if cost_a is not None or cost_b is not None
                else None
            ),
            "cost_children_diff": (
                _diff_inv(cost_children_a or {}, cost_children_b or {})
                if cost_children_a is not None or cost_children_b is not None
                else None
            ),
            "has_txns": node_b.get(
                "has_txns",
                node_a.get("has_txns", False),
            ),
            "children": children_diff,
        }

    @staticmethod
    def _compute_budget_diff(
        budgets_a: Mapping[str, Sequence[Mapping[str, Any]]],
        budgets_b: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> Mapping[str, Any]:
        """Compute the difference between two budget snapshots."""
        all_accounts = set(budgets_a.keys()) | set(budgets_b.keys())
        result: dict[str, Any] = {}
        for account in sorted(all_accounts):
            ba_list = budgets_a.get(account, [])
            bb_list = budgets_b.get(account, [])
            max_len = max(len(ba_list), len(bb_list))
            diffs: list[Mapping[str, Any]] = []
            for i in range(max_len):
                ba = ba_list[i] if i < len(ba_list) else {}
                bb = bb_list[i] if i < len(bb_list) else {}
                budget_diff: dict[str, float] = {}
                budget_children_diff: dict[str, float] = {}
                ba_budget = ba.get("budget", {})
                bb_budget = bb.get("budget", {})
                for cur in set(ba_budget.keys()) | set(bb_budget.keys()):
                    d = float(bb_budget.get(cur, 0)) - float(
                        ba_budget.get(cur, 0),
                    )
                    if abs(d) > 1e-10:
                        budget_diff[cur] = d
                ba_children = ba.get("budget_children", {})
                bb_children = bb.get("budget_children", {})
                for cur in set(ba_children.keys()) | set(
                    bb_children.keys(),
                ):
                    d = float(bb_children.get(cur, 0)) - float(
                        ba_children.get(cur, 0),
                    )
                    if abs(d) > 1e-10:
                        budget_children_diff[cur] = d
                if budget_diff or budget_children_diff:
                    diffs.append(
                        {
                            "budget_diff": budget_diff,
                            "budget_children_diff": budget_children_diff,
                        },
                    )
            if diffs:
                result[account] = diffs
        return result

    @staticmethod
    def _compute_holdings_diff(
        holdings_a: Sequence[Mapping[str, Any]],
        holdings_b: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        """Compute the difference between two holdings snapshots."""
        result: list[Mapping[str, Any]] = []
        max_len = max(len(holdings_a), len(holdings_b))
        for i in range(max_len):
            ha = holdings_a[i] if i < len(holdings_a) else {}
            hb = holdings_b[i] if i < len(holdings_b) else {}
            diff: dict[str, Any] = {}
            all_keys = set(ha.keys()) | set(hb.keys())
            for key in all_keys:
                va = ha.get(key)
                vb = hb.get(key)
                if va != vb:
                    diff[key] = {"before": va, "after": vb}
            if diff:
                result.append(diff)
        return result
