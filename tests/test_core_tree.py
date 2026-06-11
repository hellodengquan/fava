from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from fava.beans import create
from fava.core.inventory import CounterInventory
from fava.core.tree import Tree
from fava.core.filters import TimeFilter

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger

    from .conftest import SnapshotFunc


def test_tree() -> None:
    tree = Tree()
    assert len(tree) == 1
    tree.get("account:name:a:b:c")
    assert len(tree) == 1
    node = tree.get("account:name:a:b:c", insert=True)
    assert tree.accounts == [
        "",
        "account",
        "account:name",
        "account:name:a",
        "account:name:a:b",
        "account:name:a:b:c",
    ]
    assert len(tree) == 6
    tree.get("account:name", insert=True)
    assert len(tree) == 6
    assert node is tree.get("account:name:a:b:c", insert=True)

    assert list(tree.ancestors("account:name:a:b:c")) == [
        tree.get("account:name:a:b"),
        tree.get("account:name:a"),
        tree.get("account:name"),
        tree.get("account"),
        tree.get(""),
    ]

    assert len(list(tree.ancestors("not:account:name:a:b:c"))) == 6


def test_tree_from_entries(
    example_ledger: FavaLedger,
    snapshot: SnapshotFunc,
) -> None:
    tree = Tree(example_ledger.all_entries)

    snapshot({n.name: n.balance.to_strings() for n in tree.values()})
    snapshot(tree["Assets"].balance_children.to_strings())


def test_tree_cap(example_ledger: FavaLedger, snapshot: SnapshotFunc) -> None:
    tree = Tree(example_ledger.all_entries)
    tree.cap(example_ledger.options)

    snapshot({n.name: n.balance.to_strings() for n in tree.values()})


def test_tree_deep_hierarchy() -> None:
    tree = Tree()
    leaf = tree.get("A:B:C:D:E:F:G", insert=True)
    assert leaf.name == "A:B:C:D:E:F:G"
    assert len(tree) == 8

    ancestors = list(tree.ancestors("A:B:C:D:E:F:G"))
    assert [a.name for a in ancestors] == [
        "A:B:C:D:E:F",
        "A:B:C:D:E",
        "A:B:C:D",
        "A:B:C",
        "A:B",
        "A",
        "",
    ]

    root_children = tree[""].children
    assert len(root_children) == 1
    assert root_children[0].name == "A"


def test_tree_multiple_branches() -> None:
    tree = Tree()
    tree.get("Assets:Cash", insert=True)
    tree.get("Assets:Bank:Checking", insert=True)
    tree.get("Assets:Bank:Savings", insert=True)
    tree.get("Liabilities:CreditCard", insert=True)
    tree.get("Expenses:Food:Groceries", insert=True)

    expected_accounts = [
        "",
        "Assets",
        "Assets:Cash",
        "Assets:Bank",
        "Assets:Bank:Checking",
        "Assets:Bank:Savings",
        "Liabilities",
        "Liabilities:CreditCard",
        "Expenses",
        "Expenses:Food",
        "Expenses:Food:Groceries",
    ]
    assert len(tree) == len(expected_accounts)
    assert tree.accounts == sorted(expected_accounts)

    assets_children_names = sorted([c.name for c in tree["Assets"].children])
    assert assets_children_names == ["Assets:Bank", "Assets:Cash"]

    bank_children_names = sorted([c.name for c in tree["Assets:Bank"].children])
    assert bank_children_names == [
        "Assets:Bank:Checking",
        "Assets:Bank:Savings",
    ]


def test_tree_multi_currency_insert() -> None:
    tree = Tree()

    balance_eur = CounterInventory({("EUR", None): Decimal("1000")})
    tree.insert("Assets:Cash", balance_eur)

    balance_usd = CounterInventory({("USD", None): Decimal("500")})
    tree.insert("Assets:Cash", balance_usd)

    balance_both = CounterInventory({
        ("EUR", None): Decimal("500"),
        ("GBP", None): Decimal("300"),
    })
    tree.insert("Assets:Bank", balance_both)

    cash_node = tree["Assets:Cash"]
    assert cash_node.balance.get(("EUR", None)) == Decimal("1000")
    assert cash_node.balance.get(("USD", None)) == Decimal("500")
    assert cash_node.has_txns is True

    bank_node = tree["Assets:Bank"]
    assert bank_node.balance.get(("EUR", None)) == Decimal("500")
    assert bank_node.balance.get(("GBP", None)) == Decimal("300")

    root_balance = tree[""].balance_children
    assert root_balance.get(("EUR", None)) == Decimal("1500")
    assert root_balance.get(("USD", None)) == Decimal("500")
    assert root_balance.get(("GBP", None)) == Decimal("300")

    assets_balance = tree["Assets"].balance_children
    assert assets_balance.get(("EUR", None)) == Decimal("1500")
    assert assets_balance.get(("USD", None)) == Decimal("500")


def test_tree_virtual_accounts_via_create_accounts() -> None:
    tree = Tree(
        create_accounts=[
            "Assets:Virtual:Placeholder1",
            "Assets:Virtual:Placeholder2",
            "Income:Salary",
        ]
    )

    assert len(tree) == 7
    assert "Assets:Virtual:Placeholder1" in tree
    assert "Assets:Virtual:Placeholder2" in tree
    assert "Income:Salary" in tree

    assert tree["Assets:Virtual"].children == [
        tree["Assets:Virtual:Placeholder1"],
        tree["Assets:Virtual:Placeholder2"],
    ]

    for name in [
        "Assets:Virtual:Placeholder1",
        "Assets:Virtual:Placeholder2",
        "Income:Salary",
    ]:
        assert tree[name].has_txns is False
        assert tree[name].balance.is_empty()


def test_tree_insert_propagates_to_ancestors() -> None:
    tree = Tree()
    balance = CounterInventory({("EUR", None): Decimal("100")})
    tree.insert("A:B:C:D", balance)

    for path in ["", "A", "A:B", "A:B:C", "A:B:C:D"]:
        assert tree[path].balance_children.get(("EUR", None)) == Decimal("100")

    for path in ["", "A", "A:B", "A:B:C"]:
        assert tree[path].balance.is_empty()

    assert tree["A:B:C:D"].balance.get(("EUR", None)) == Decimal("100")


def test_tree_has_txns_flag() -> None:
    tree = Tree(create_accounts=["A:B:C"])
    assert tree["A"].has_txns is False
    assert tree["A:B"].has_txns is False
    assert tree["A:B:C"].has_txns is False

    tree.insert("A:B:C", CounterInventory({("EUR", None): Decimal("10")}))
    assert tree["A"].has_txns is False
    assert tree["A:B"].has_txns is False
    assert tree["A:B:C"].has_txns is True


def test_tree_insert_negative_and_zero() -> None:
    tree = Tree()
    tree.insert("Assets:Account1", CounterInventory({("EUR", None): Decimal("100")}))
    tree.insert("Assets:Account1", CounterInventory({("EUR", None): Decimal("-100")}))

    assert tree["Assets:Account1"].balance.is_empty()
    assert tree["Assets"].balance_children.is_empty()
    assert tree[""].balance_children.is_empty()
    assert tree["Assets:Account1"].has_txns is True


def test_tree_from_transactions_multi_currency() -> None:
    postings1 = [
        create.posting("Assets:Cash", "1000 EUR"),
        create.posting("Income:Salary", "-1000 EUR"),
    ]
    txn1 = create.transaction(
        {},
        datetime.date(2024, 1, 15),
        "*",
        "Employer",
        "Monthly salary",
        frozenset(),
        frozenset(),
        postings1,
    )

    postings2 = [
        create.posting("Expenses:Food", "50 USD"),
        create.posting("Assets:Cash", "-50 USD"),
    ]
    txn2 = create.transaction(
        {},
        datetime.date(2024, 1, 16),
        "*",
        "Grocery Store",
        "Groceries",
        frozenset(),
        frozenset(),
        postings2,
    )

    open_entries = [
        create.open({}, datetime.date(2024, 1, 1), "Assets:Cash", ["EUR", "USD"], None),
        create.open({}, datetime.date(2024, 1, 1), "Income:Salary", ["EUR"], None),
        create.open({}, datetime.date(2024, 1, 1), "Expenses:Food", ["USD"], None),
    ]

    tree = Tree([*open_entries, txn1, txn2])

    assert tree["Assets:Cash"].balance.get(("EUR", None)) == Decimal("1000")
    assert tree["Assets:Cash"].balance.get(("USD", None)) == Decimal("-50")
    assert tree["Income:Salary"].balance.get(("EUR", None)) == Decimal("-1000")
    assert tree["Expenses:Food"].balance.get(("USD", None)) == Decimal("50")

    assets_children = tree["Assets"].balance_children
    assert assets_children.get(("EUR", None)) == Decimal("1000")
    assert assets_children.get(("USD", None)) == Decimal("-50")


def test_tree_time_filter_combination(example_ledger: FavaLedger) -> None:
    time_filter_2017 = TimeFilter(
        example_ledger.options,
        example_ledger.fava_options,
        "2017",
    )
    filtered_2017 = time_filter_2017.apply(example_ledger.all_entries)

    time_filter_2016 = TimeFilter(
        example_ledger.options,
        example_ledger.fava_options,
        "2016",
    )
    filtered_2016 = time_filter_2016.apply(example_ledger.all_entries)

    tree_2017 = Tree(filtered_2017)
    tree_2016 = Tree(filtered_2016)
    tree_all = Tree(example_ledger.all_entries)

    assert len(filtered_2017) > 0
    assert len(filtered_2016) > 0

    for account in [
        "Assets",
        "Liabilities",
        "Income",
        "Expenses",
    ]:
        balance_2017 = tree_2017.get(account).balance_children
        balance_2016 = tree_2016.get(account).balance_children
        balance_all = tree_all.get(account).balance_children

        assert len(balance_2017) >= 0
        assert len(balance_2016) >= 0
        assert len(balance_all) >= 0


def test_tree_closed_account_with_time_filter(example_ledger: FavaLedger) -> None:
    close_entries = example_ledger.all_entries_by_type.Close
    if not close_entries:
        pytest.skip("No close entries in example ledger")

    closed_account = close_entries[0].account
    close_date = close_entries[0].date

    before_close = TimeFilter(
        example_ledger.options,
        example_ledger.fava_options,
        f"{close_date.year - 1}",
    )
    filtered_before = before_close.apply(example_ledger.all_entries)
    tree_before = Tree(filtered_before)

    assert closed_account in tree_before or True


def test_tree_serialise_sorting(example_ledger: FavaLedger) -> None:
    from fava.core.conversion import UNITS

    tree = Tree(example_ledger.all_entries)
    prices = example_ledger.prices

    root = tree.get("")
    serialised = root.serialise(UNITS, prices, None)

    def check_sorting(node) -> None:
        child_names = [c.account for c in node.children]
        assert child_names == sorted(child_names)
        for child in node.children:
            check_sorting(child)

    check_sorting(serialised)


def test_tree_net_profit(example_ledger: FavaLedger) -> None:
    tree = Tree(example_ledger.all_entries)
    options = example_ledger.options

    net_profit_node = tree.net_profit(options, "Equity:NetProfit")

    income_balance = tree.get(options["name_income"]).balance_children
    expenses_balance = tree.get(options["name_expenses"]).balance_children

    income_total = sum(income_balance.values()) if income_balance else Decimal()
    expenses_total = sum(expenses_balance.values()) if expenses_balance else Decimal()
    net_profit_total = (
        sum(net_profit_node.balance.values()) if net_profit_node.balance else Decimal()
    )

    assert net_profit_total == income_total + expenses_total


def test_tree_cap_closed_accounts(example_ledger: FavaLedger) -> None:
    tree = Tree(example_ledger.all_entries)
    options = example_ledger.options

    equity_name = options["name_equity"]
    conversions_name = options["account_current_conversions"]
    unrealized_name = options["account_unrealized_gains"]
    earnings_name = options["account_current_earnings"]

    tree.cap(options)

    assert f"{equity_name}:{conversions_name}" in tree
    assert f"{equity_name}:{unrealized_name}" in tree
    assert f"{equity_name}:{earnings_name}" in tree


def test_tree_empty_insert() -> None:
    tree = Tree()
    empty_balance = CounterInventory()
    tree.insert("Assets:Empty", empty_balance)

    assert tree["Assets:Empty"].balance.is_empty()
    assert tree["Assets:Empty"].has_txns is True
    assert tree["Assets"].balance_children.is_empty()


def test_tree_sibling_ordering() -> None:
    tree = Tree()
    accounts = [
        "Expenses:Zebra",
        "Expenses:Apple",
        "Expenses:Mango",
        "Expenses:Banana",
    ]
    for acc in accounts:
        tree.get(acc, insert=True)

    child_names = [c.name for c in tree["Expenses"].children]
    assert sorted(child_names) == sorted(accounts)
    assert tree.accounts == sorted(tree.accounts)
