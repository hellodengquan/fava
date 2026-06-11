from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from fava.core.conversion import AT_COST
from fava.core.inventory import CounterInventory
from fava.util.date import Day
from fava.util.date import Month

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger

    from .conftest import GetFavaLedger
    from .conftest import SnapshotFunc


def test_interval_totals(
    small_example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    filtered = small_example_ledger.get_filtered()
    for conversion in ["at_cost", "USD"]:
        data = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            conversion,
        )
        snapshot(data, json=True)


def test_interval_totals_inverted(
    small_example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    filtered = small_example_ledger.get_filtered()
    for conversion in ["at_cost", "USD"]:
        data = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            conversion,
            invert=True,
        )
        snapshot(data, json=True)


def test_linechart_data(
    example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    filtered = example_ledger.get_filtered()
    for conversion in ["at_cost", "units", "at_value", "USD"]:
        data = example_ledger.charts.linechart(
            filtered,
            "Assets:Testing:MultipleCommodities",
            conversion,
        )
        snapshot(data, json=True)

    assert not example_ledger.charts.linechart(
        filtered,
        "Assets:Testing:MultipleCommodities:NotAnAccount",
        "units",
    )


def test_net_worth(example_ledger: FavaLedger, snapshot: SnapshotFunc) -> None:
    filtered = example_ledger.get_filtered()
    data = example_ledger.charts.net_worth(filtered, Month, "USD")
    snapshot(data, json=True)


def test_net_worth_off_by_one(
    snapshot: SnapshotFunc,
    get_ledger: GetFavaLedger,
) -> None:
    off_by_one = get_ledger("off-by-one")
    off_by_one_filtered = off_by_one.get_filtered()
    assert not off_by_one.errors
    assert len(off_by_one_filtered.entries) == 9

    for interval in [Day, Month]:
        data = off_by_one.charts.net_worth(
            off_by_one_filtered,
            interval,
            "at_value",
        )
        assert len(data) == 4 if interval == Day else 1
        snapshot(data, json=True)


def test_hierarchy(example_ledger: FavaLedger) -> None:
    filtered = example_ledger.get_filtered()

    data = example_ledger.charts.hierarchy(filtered, "Assets", AT_COST)
    assert data.balance_children == {
        "IRAUSD": Decimal("7200.00"),
        "USD": Decimal("94320.27840"),
        "VACHR": Decimal(-82),
    }
    assert data.balance == {}
    etrade = data.children[1].children[2]
    assert etrade.account == "Assets:US:ETrade"
    assert etrade.balance_children == {"USD": Decimal("23137.54")}


def test_chart_uses_canonicalizer_from_commodities_module(
    example_ledger: FavaLedger,
) -> None:
    """图表模块应通过统一归并接口聚合余额，确保与持仓页面一致。"""
    canonicalizer = example_ledger.commodities.canonical
    inv = CounterInventory()
    inv.add(("USD", None), Decimal("100"))
    inv.add(("usd", None), Decimal("200"))

    from fava.core.conversion import UNITS

    result = UNITS.apply(inv, None, None, canonicalizer=canonicalizer)
    assert "USD" in result
    assert result["USD"] == Decimal("300")
    assert "usd" not in result


def test_hierarchy_balance_children_matches_holdings(
    example_ledger: FavaLedger,
) -> None:
    """图表层次结构余额应与持仓页面使用同一归并接口。

    验证 hierarchy 的 balance_children 经过 canonicalizer 归并后，
    不会出现同一商品不同大小写的重复键。
    """
    filtered = example_ledger.get_filtered()

    from fava.core.conversion import UNITS, conversion_from_str

    for conversion in [AT_COST, UNITS, conversion_from_str("USD")]:
        data = example_ledger.charts.hierarchy(
            filtered, "Assets", conversion
        )
        _assert_no_case_duplicates(data)


def _assert_no_case_duplicates(node: object) -> None:
    """递归检查节点中不存在同一商品不同大小写的重复键。"""
    from fava.core.tree import SerialisedTreeNode

    assert isinstance(node, SerialisedTreeNode)
    for balance_dict in [node.balance, node.balance_children]:
        currencies_lower = {k.lower() for k in balance_dict.keys()}
        assert len(currencies_lower) == len(balance_dict), (
            f"Duplicate case-variant keys in balance: "
            f"{list(balance_dict.keys())}"
        )
    for child in node.children:
        _assert_no_case_duplicates(child)
