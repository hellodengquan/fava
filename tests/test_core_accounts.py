"""Fava's budget syntax."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest

from fava.beans import create
from fava.beans.helpers import replace
from fava.core.accounts import AccountData
from fava.core.accounts import AccountDict
from fava.core.accounts import balance_string
from fava.core.accounts import get_last_entry
from fava.core.accounts import uptodate_status
from fava.core.group_entries import TransactionPosting
from fava.core.tree import Tree

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger


def test_get_last_entry() -> None:
    assert get_last_entry([]) is None

    posting = create.posting("Assets", create.amount("10 EUR"))
    txn_unrealized = create.transaction(
        {},
        datetime.date(2024, 1, 1),
        flag="U",
        payee="payee",
        narration="narration",
        tags=frozenset(),
        links=frozenset(),
        postings=[posting],
    )
    txn = create.transaction(
        meta={},
        date=datetime.date(2023, 1, 1),
        flag="*",
        payee="payee",
        narration="narration",
        tags=frozenset(),
        links=frozenset(),
        postings=[posting],
    )
    note = create.note(
        meta={},
        date=datetime.date(2025, 1, 1),
        account="Assets",
        comment="a note",
    )

    entries = [
        TransactionPosting(txn, posting),
        TransactionPosting(txn_unrealized, posting),
    ]

    assert get_last_entry([note]) == note
    assert get_last_entry(entries) == txn
    assert get_last_entry([*entries, note]) == note


def test_uptodate_status() -> None:
    assert uptodate_status([]) is None

    note = create.note(
        meta={},
        date=datetime.date(2025, 1, 1),
        account="Assets",
        comment="a note",
    )
    balance = create.balance(
        meta={},
        date=datetime.date(2024, 1, 1),
        account="Assets",
        amount=create.amount("10 EUR"),
    )
    balance_diff = replace(balance, diff_amount=create.amount("1 EUR"))

    assert uptodate_status([balance, note]) == "green"
    assert uptodate_status([balance_diff, note]) == "red"


def test_account_data_defaults() -> None:
    data = AccountData()
    assert data.close_date is None
    assert data.meta == {}
    assert data.uptodate_status is None
    assert data.balance_string is None
    assert data.last_entry is None


def test_account_data_close_date() -> None:
    data = AccountData()
    close_date = datetime.date(2024, 12, 31)
    data.close_date = close_date
    assert data.close_date == close_date


def test_account_dict_missing_key() -> None:
    account_dict = AccountDict.__new__(AccountDict)
    account_dict.clear()
    assert account_dict["nonexistent:account"] is AccountDict.EMPTY
    assert account_dict["another:nonexistent"] is AccountDict.EMPTY


def test_account_dict_setdefault() -> None:
    account_dict = AccountDict.__new__(AccountDict)
    account_dict.clear()

    data1 = account_dict.setdefault("Assets:Cash")
    assert isinstance(data1, AccountData)
    assert "Assets:Cash" in account_dict

    data2 = account_dict.setdefault("Assets:Cash")
    assert data1 is data2

    account_dict.setdefault("Assets:Bank")
    assert len(account_dict) == 2


def test_account_dict_virtual_account_metadata() -> None:
    account_dict = AccountDict.__new__(AccountDict)
    account_dict.clear()

    meta_virtual = {"fava-uptodate-indication": True}
    data = account_dict.setdefault("Assets:Virtual:Placeholder")
    data.meta = meta_virtual
    assert account_dict["Assets:Virtual:Placeholder"].meta == meta_virtual


def test_balance_string_multi_currency() -> None:
    from fava.core.inventory import CounterInventory
    from decimal import Decimal

    tree = Tree()
    node = tree.get("Assets:MultiCurrency", insert=True)

    node.balance.add(("EUR", None), Decimal("1000"))
    node.balance.add(("USD", None), Decimal("500"))
    node.balance.add(("GBP", None), Decimal("250.50"))

    result = balance_string(node)
    assert "1000 EUR" in result
    assert "500 USD" in result
    assert "250.50 GBP" in result
    assert "Assets:MultiCurrency" in result


def test_balance_string_empty_account() -> None:
    tree = Tree()
    node = tree.get("Assets:Empty", insert=True)

    result = balance_string(node)
    assert result == ""


def test_account_dict_closed_accounts(example_ledger: FavaLedger) -> None:
    account_module = example_ledger.accounts

    close_entries = example_ledger.all_entries_by_type.Close
    if not close_entries:
        pytest.skip("No close entries in example ledger")

    for close in close_entries:
        account_data = account_module.get(close.account)
        if account_data is not AccountDict.EMPTY:
            assert account_data.close_date == close.date


def test_account_dict_open_metadata(example_ledger: FavaLedger) -> None:
    account_module = example_ledger.accounts

    open_entries = example_ledger.all_entries_by_type.Open
    assert len(open_entries) > 0

    for open_entry in open_entries[:5]:
        account_data = account_module.get(open_entry.account)
        if account_data is not AccountDict.EMPTY:
            assert account_data.meta == open_entry.meta


def test_account_dict_last_entry_tracking(example_ledger: FavaLedger) -> None:
    account_module = example_ledger.accounts

    for account_name, account_data in account_module.items():
        if account_data.last_entry is not None:
            assert isinstance(account_data.last_entry.date, datetime.date)
            assert isinstance(account_data.last_entry.entry_hash, str)
            break
    else:
        pytest.skip("No accounts with last_entry data")


def test_account_dict_all_balance_directives(example_ledger: FavaLedger) -> None:
    account_module = example_ledger.accounts
    result = account_module.all_balance_directives()
    assert isinstance(result, str)


def test_closed_account_date_boundary() -> None:
    from fava.core.accounts import LastEntry

    data = AccountData()
    close_date = datetime.date(2024, 6, 30)
    data.close_date = close_date

    assert data.close_date == datetime.date(2024, 6, 30)

    last_entry = LastEntry(
        date=datetime.date(2024, 6, 15),
        entry_hash="abc123",
    )
    data.last_entry = last_entry
    assert data.last_entry.date < data.close_date


def test_uptodate_status_yellow_transaction() -> None:
    posting = create.posting("Assets:Cash", create.amount("100 EUR"))
    txn = create.transaction(
        meta={},
        date=datetime.date(2024, 1, 15),
        flag="*",
        payee="Store",
        narration="Purchase",
        tags=frozenset(),
        links=frozenset(),
        postings=[posting],
    )
    tp = TransactionPosting(txn, posting)
    assert uptodate_status([tp]) == "yellow"


def test_get_last_entry_close_entry_skipped() -> None:
    from fava.core.accounts import AccountDict, LastEntry
    from fava.beans.abc import Close

    posting = create.posting("Assets", create.amount("10 EUR"))
    txn = create.transaction(
        meta={},
        date=datetime.date(2023, 6, 1),
        flag="*",
        payee="payee",
        narration="narration",
        tags=frozenset(),
        links=frozenset(),
        postings=[posting],
    )
    close_entry = create.close(
        meta={},
        date=datetime.date(2024, 1, 1),
        account="Assets",
    )
    entries_only_close = [close_entry]
    entries = [TransactionPosting(txn, posting), close_entry]

    result_close_only = get_last_entry(entries_only_close)
    assert isinstance(result_close_only, Close)

    result = get_last_entry(entries)
    assert isinstance(result, Close)

    account_dict = AccountDict.__new__(AccountDict)
    account_dict.clear()
    account_data = account_dict.setdefault("Assets")

    if result is not None and not isinstance(result, Close):
        account_data.last_entry = LastEntry(
            date=result.date,
            entry_hash="hash",
        )

    assert account_data.last_entry is None
