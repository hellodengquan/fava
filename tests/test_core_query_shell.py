from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from fava.core.query import QueryResultTable
from fava.core.query import QueryResultText
from fava.core.query_shell import NonExportableQueryError
from fava.core.query_shell import QueryCompilationError
from fava.core.query_shell import QueryNotFoundError
from fava.core.query_shell import QueryParseError
from fava.core.query_shell import TooManyRunArgsError
from fava.util import excel

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from fava.core.query import QueryResult

    from .conftest import GetFavaLedger
    from .conftest import SnapshotFunc


@pytest.fixture
def run_query(get_ledger: GetFavaLedger) -> Callable[[str], QueryResult]:
    query_ledger = get_ledger("query-example")

    def _run_query(query_string: str) -> QueryResult:
        return query_ledger.query_shell.execute_query_serialised(
            query_ledger.all_entries,
            query_string,
        )

    return _run_query


@pytest.fixture
def run_text_query(
    run_query: Callable[[str], QueryResult],
) -> Callable[[str], str]:
    def _run_text_query(query_string: str) -> str:
        """Run a query that should only return string contents."""
        result = run_query(query_string)
        assert isinstance(result, QueryResultText)
        return result.contents

    return _run_text_query


def test_text_queries(
    snapshot: SnapshotFunc, run_text_query: Callable[[str], str]
) -> None:
    assert run_text_query(".help")

    noop_doc = "Doesn't do anything in Fava's query shell."
    assert run_text_query(".exit") == noop_doc
    assert run_text_query(".help exit") == noop_doc
    snapshot(run_text_query(".explain select date, balance")[:100])

    assert run_text_query(".run") == "custom_query\ncustom query with space"


def test_query_balances(
    snapshot: SnapshotFunc, run_query: Callable[[str], QueryResult]
) -> None:
    assert isinstance(run_query(".run custom_query"), QueryResultTable)
    bal = run_query("balances")
    if sys.version_info >= (3, 12):
        # This fails for some reason on older Pythons, probably some minor
        # difference there.
        snapshot(bal)
    assert run_query(".run custom_query") == bal
    assert run_query(".run 'custom query with space'") == bal


def test_query_types(run_query: Callable[[str], QueryResult]) -> None:
    various_types = run_query(
        "select date, payee, weight, position, balance, "
        "cost_number, cost_number, tags, entry, meta"
    )
    assert isinstance(various_types, QueryResultTable)
    assert len(various_types.types) == 10


def test_query_errors(run_query: Callable[[str], QueryResult]) -> None:
    with pytest.raises(TooManyRunArgsError):
        run_query(".run custom_query other")
    with pytest.raises(QueryNotFoundError):
        run_query(".run unknown")
    with pytest.raises(QueryParseError):
        run_query("asdf")
    with pytest.raises(QueryCompilationError):
        run_query("select asdf")


def test_query_to_file(
    snapshot: SnapshotFunc,
    get_ledger: GetFavaLedger,
) -> None:
    query_ledger = get_ledger("query-example")
    entries = query_ledger.all_entries
    query_shell = query_ledger.query_shell

    name, data = query_shell.query_to_file(entries, "run custom_query", "csv")
    assert name == "custom_query"
    name, data = query_shell.query_to_file(entries, "balances", "csv")
    assert name == "query_result"
    snapshot(data.getvalue())

    with pytest.raises(NonExportableQueryError):
        query_shell.query_to_file(entries, ".help targets", "csv")
    with pytest.raises(TooManyRunArgsError):
        query_shell.query_to_file(entries, "run custom_query other", "csv")
    with pytest.raises(QueryNotFoundError):
        query_shell.query_to_file(entries, "run testsetest", "csv")
    with pytest.raises(QueryParseError):
        query_shell.query_to_file(entries, "asdf", "csv")
    with pytest.raises(QueryCompilationError):
        query_shell.query_to_file(entries, "select asdf", "csv")


@pytest.mark.skipif(not excel.HAVE_EXCEL, reason="pyexcel not installed")
def test_query_to_excel_file(get_ledger: GetFavaLedger) -> None:
    query_ledger = get_ledger("query-example")
    entries = query_ledger.all_entries
    query_shell = query_ledger.query_shell

    name, _data = query_shell.query_to_file(entries, "run custom_query", "ods")
    assert name == "custom_query"


def test_export_with_canonicalizer_uses_unified_interface(
    get_ledger: GetFavaLedger,
) -> None:
    """导出报表应该使用统一的别名归并接口，与前台展示数据口径一致。

    验证：
    1. query_to_file 接受 canonicalizer 参数
    2. execute_query_serialised 接受 canonicalizer 参数
    3. 两者使用相同的 canonicalizer 时结果一致
    """
    query_ledger = get_ledger("query-example")
    entries = query_ledger.all_entries
    query_shell = query_ledger.query_shell
    canonicalizer = query_ledger.commodities.canonical

    _name, csv_data = query_shell.query_to_file(
        entries, "balances", "csv", canonicalizer=canonicalizer
    )
    csv_content = csv_data.getvalue().decode("utf-8")

    serialised_result = query_shell.execute_query_serialised(
        entries, "balances", canonicalizer=canonicalizer
    )
    assert isinstance(serialised_result, QueryResultTable)

    header_row = csv_content.split("\n")[0]
    for col in serialised_result.types:
        assert col.name in header_row

    assert "usd" not in csv_content.lower() or "USD" in csv_content


def test_canonicalize_raw_value_handles_all_types(
    get_ledger: GetFavaLedger,
) -> None:
    """_canonicalize_raw_value 应该正确处理各种原始查询结果类型。"""
    from decimal import Decimal

    from beancount.core.amount import Amount
    from beancount.core.inventory import Inventory
    from beancount.core.position import Cost
    from beancount.core.position import Position

    from fava.core.query_shell import QueryShell

    query_ledger = get_ledger("query-example")
    canonicalizer = query_ledger.commodities.canonical

    assert canonicalizer("USD") == "USD"
    assert canonicalizer("usd") == "USD"

    amount = Amount(Decimal("100"), "usd")
    canonical_amount = QueryShell._canonicalize_raw_value(amount, canonicalizer)
    assert canonical_amount.currency == "USD"
    assert canonical_amount.number == Decimal("100")

    pos = Position(
        Amount(Decimal("10"), "gld"),
        Cost(Decimal("190.30"), "usd", None, None),
    )
    canonical_pos = QueryShell._canonicalize_raw_value(pos, canonicalizer)
    assert canonical_pos.units.currency == "GLD"
    assert canonical_pos.cost.currency == "USD"

    inv = Inventory()
    inv.add_position(
        Position(Amount(Decimal("5"), "itot"), None)
    )
    inv.add_position(
        Position(Amount(Decimal("3"), "ITOT"), None)
    )
    canonical_inv = QueryShell._canonicalize_raw_value(inv, canonicalizer)
    assert len(canonical_inv) == 1
    for pos in canonical_inv:
        assert pos.units.currency == "ITOT"
        assert pos.units.number == Decimal("8")

    account_str = "Assets:US:BofA:Checking"
    assert (
        QueryShell._canonicalize_raw_value(account_str, canonicalizer)
        == account_str
    )
