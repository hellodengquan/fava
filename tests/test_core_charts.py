from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from fava.core.conversion import AT_COST
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


def test_hierarchy_nonexistent_account(example_ledger: FavaLedger) -> None:
    filtered = example_ledger.get_filtered()

    data = example_ledger.charts.hierarchy(
        filtered, "Assets:NonExistent:Account", AT_COST
    )
    assert data.account == "Assets:NonExistent:Account"
    assert data.balance == {}
    assert data.balance_children == {}
    assert data.children == []


def test_hierarchy_leaf_account(example_ledger: FavaLedger) -> None:
    filtered = example_ledger.get_filtered()

    data = example_ledger.charts.hierarchy(
        filtered, "Assets:US:BofA:Checking", AT_COST
    )
    assert data.account == "Assets:US:BofA:Checking"
    assert data.children == []
    assert len(data.balance) > 0


def test_interval_totals_nonexistent_account(
    small_example_ledger: FavaLedger,
) -> None:
    filtered = small_example_ledger.get_filtered()

    data = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        "Expenses:NonExistent",
        "at_cost",
    )
    assert len(data) > 0
    for item in data:
        assert item.balance == {}
        assert item.budgets == {}
        assert item.account_balances == {}


def test_interval_totals_empty_filtered(
    small_example_ledger: FavaLedger,
) -> None:
    from fava.core import FilteredLedger

    filtered_empty = FilteredLedger(small_example_ledger, time="1900")
    data = small_example_ledger.charts.interval_totals(
        filtered_empty,
        Month,
        "Expenses",
        "at_cost",
    )
    for item in data:
        assert item.balance == {}
        assert item.budgets == {}
        assert item.account_balances == {}


def test_interval_totals_multiple_accounts(
    small_example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    filtered = small_example_ledger.get_filtered()

    accounts = ("Expenses:Food", "Expenses:Home")
    data = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        accounts,
        "at_cost",
    )
    for item in data:
        assert item.budgets == {}
    snapshot(data, json=True)


def test_interval_totals_invert_with_budgets(
    small_example_ledger: FavaLedger,
) -> None:
    from fava.core import FilteredLedger

    filtered = FilteredLedger(small_example_ledger, time="2016")

    data_normal = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        "Expenses",
        "at_cost",
    )
    data_inverted = small_example_ledger.charts.interval_totals(
        filtered,
        Month,
        "Expenses",
        "at_cost",
        invert=True,
    )

    assert len(data_normal) == len(data_inverted)
    for normal, inverted in zip(data_normal, data_inverted):
        assert normal.date == inverted.date
        for currency, value in normal.balance.items():
            assert inverted.balance[currency] == -value
        for currency, value in normal.budgets.items():
            assert inverted.budgets[currency] == -value
        for account, balances in normal.account_balances.items():
            for currency, value in balances.items():
                assert inverted.account_balances[account][currency] == -value


def test_interval_totals_boundary_dates(
    get_ledger: GetFavaLedger,
) -> None:
    off_by_one = get_ledger("off-by-one")
    filtered = off_by_one.get_filtered()

    data_day = off_by_one.charts.interval_totals(
        filtered,
        Day,
        "Assets",
        "at_cost",
    )
    assert len(data_day) == 4

    data_month = off_by_one.charts.interval_totals(
        filtered,
        Month,
        "Assets",
        "at_cost",
    )
    assert len(data_month) == 1

    first_day = data_day[0]
    assert first_day.date.isoformat() == "2022-01-01"
    last_day = data_day[-1]
    assert last_day.date.isoformat() == "2022-01-04"


def test_linechart_nonexistent_account(
    example_ledger: FavaLedger,
) -> None:
    filtered = example_ledger.get_filtered()

    data = example_ledger.charts.linechart(
        filtered,
        "Assets:NonExistent:Account",
        "units",
    )
    assert data == []


def test_linechart_empty_filtered(
    example_ledger: FavaLedger,
) -> None:
    from fava.core import FilteredLedger

    filtered_empty = FilteredLedger(example_ledger, time="1900")
    data = example_ledger.charts.linechart(
        filtered_empty,
        "Assets:US:BofA:Checking",
        "units",
    )
    assert data == []


def test_linechart_zero_balance_tracking(
    example_ledger: FavaLedger,
) -> None:
    filtered = example_ledger.get_filtered()

    data = example_ledger.charts.linechart(
        filtered,
        "Assets:Testing:MultipleCommodities",
        "units",
    )

    if len(data) >= 2:
        currencies_first = set(data[0].balance.keys())
        for i in range(1, len(data)):
            currencies_current = set(data[i].balance.keys())
            for currency in currencies_first - currencies_current:
                assert currency in data[i].balance
                assert data[i].balance[currency] == Decimal(0)


def test_net_worth_empty_filtered(
    example_ledger: FavaLedger,
) -> None:
    from fava.core import FilteredLedger

    filtered_empty = FilteredLedger(example_ledger, time="1900")
    data = example_ledger.charts.net_worth(
        filtered_empty,
        Month,
        "USD",
    )
    for item in data:
        for value in item.balance.values():
            assert value == Decimal(0)


def test_net_worth_no_transactions(
    get_ledger: GetFavaLedger,
) -> None:
    from fava.core import FilteredLedger

    ledger = get_ledger("example")
    filtered = FilteredLedger(ledger, time="2000")
    data = ledger.charts.net_worth(
        filtered,
        Month,
        "USD",
    )
    assert len(data) > 0
    for item in data:
        for value in item.balance.values():
            assert value == Decimal(0)


def test_interval_totals_100_interval_limit(
    get_ledger: GetFavaLedger,
) -> None:
    from fava.core import FilteredLedger
    from fava.util.date import Day

    ledger = get_ledger("long-example")
    filtered = FilteredLedger(ledger, time="2010-2020")

    data = ledger.charts.interval_totals(
        filtered,
        Day,
        "Expenses",
        "at_cost",
    )

    assert len(data) <= 100


def test_hierarchy_deep_account(example_ledger: FavaLedger) -> None:
    filtered = example_ledger.get_filtered()

    data = example_ledger.charts.hierarchy(
        filtered, "Assets:US:BofA:Checking", AT_COST
    )
    assert data.account == "Assets:US:BofA:Checking"
    assert data.children == []
    assert len(data.balance) > 0


def test_interval_totals_conversion_edge_cases(
    small_example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    filtered = small_example_ledger.get_filtered()

    for conversion in ["at_cost", "units", "at_value"]:
        data = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            conversion,
        )
        snapshot(data, json=True, name=conversion)


def test_linechart_conversion_edge_cases(
    example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    filtered = example_ledger.get_filtered()

    for conversion in ["at_cost", "units", "at_value"]:
        data = example_ledger.charts.linechart(
            filtered,
            "Assets:Testing:MultipleCommodities",
            conversion,
        )
        snapshot(data, json=True, name=conversion)
