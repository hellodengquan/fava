from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from fava.core.inventory import CounterInventory
from fava.core.tree import Tree

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


def test_tree_cap_with_canonicalizer(
    example_ledger: FavaLedger,
) -> None:
    """cap() 方法应接受并使用 canonicalizer 参数。

    验证 cap() 中的 AT_COST.apply 传入 canonicalizer 后，
    转换计算中的商品名称被正确归并，不会出现同一商品因大小写
    不同而产生的重复键（同一商品不同成本批次是正常的，不应视为重复）。
    """
    tree = Tree(example_ledger.all_entries)
    canonicalizer = example_ledger.commodities.canonical

    tree.cap(example_ledger.options, canonicalizer=canonicalizer)

    for node in tree.values():
        for balance_dict in [node.balance, node.balance_children]:
            currencies = [k[0] for k in balance_dict.keys()]
            lower_to_original: dict[str, list[str]] = {}
            for c in currencies:
                lower_to_original.setdefault(c.lower(), []).append(c)
            for lower, originals in lower_to_original.items():
                unique_originals = set(originals)
                if len(unique_originals) > 1:
                    pytest.fail(
                        f"Duplicate case-variant keys in node '{node.name}': "
                        f"{unique_originals} all map to '{lower}'"
                    )


def test_tree_serialise_with_canonicalizer_aggregates_case_variants(
    example_ledger: FavaLedger,
) -> None:
    """serialise() 传入 canonicalizer 后应将不同大小写的商品归并聚合。"""
    from fava.core.conversion import UNITS

    tree = Tree()
    inv = CounterInventory()
    inv.add(("USD", None), Decimal("100"))
    inv.add(("usd", None), Decimal("200"))
    tree.insert("Assets:Test", inv)

    canonicalizer = example_ledger.commodities.canonical
    result = tree.get("Assets:Test").serialise(
        UNITS,
        example_ledger.prices,
        None,
        canonicalizer=canonicalizer,
    )

    assert result.balance == {"USD": Decimal("300")}
    assert "usd" not in result.balance
