"""Tests for holdings comparison logic, including cross-currency regression tests."""

from __future__ import annotations

import pytest

from fava.core.snapshots import SnapshotFilters
from fava.core.snapshots import SnapshotStore


class TestHoldingsComparison:
    """Tests for holdings difference computation."""

    def test_holdings_diff_no_change(
        self,
        snapshot_store: SnapshotStore,
    ) -> None:
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
        """Regression test: units currency differs from price currency."""
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
        """Regression test: new currency position appears between snapshots."""
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
