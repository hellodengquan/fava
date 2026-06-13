"""Tests for the document_gaps core module."""

from __future__ import annotations

import datetime
import shutil
from decimal import Decimal
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from fava.beans import create
from fava.beans.funcs import hash_entry
from fava.beans.load import load_string
from fava.core import FavaLedger
from fava.core.document_gaps import DocumentGapChecker
from fava.core.document_gaps import _is_handled
from fava.core.document_gaps import TransactionGap
from fava.core.file import remove_metadata_from_file
from fava.core.group_entries import group_entries_by_type

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from fava.beans.abc import Directive
    from fava.core import FavaLedger


def _make_filtered_from_entries(
    ledger: FavaLedger, entries: Sequence[Directive]
):
    """Helper: set entries on a ledger and return filtered view."""
    ledger.all_entries = entries
    ledger.all_entries_by_type = group_entries_by_type(entries)
    ledger.get_filtered.cache_clear()
    return ledger.get_filtered()


def _amt(value: str, currency: str = "USD"):
    """Create an amount from a string value."""
    return create.amount(Decimal(value), currency)


def _two_postings(expense_account: str, amount: str, cash_account: str = "Assets:Cash"):
    """Create two balanced postings for a simple transaction."""
    return [
        create.posting(expense_account, _amt(amount)),
        create.posting(cash_account, _amt(f"-{amount}")),
    ]


def test_empty_ledger(example_ledger: FavaLedger) -> None:
    """An empty ledger should report no gaps."""
    filtered = _make_filtered_from_entries(example_ledger, [])
    report = example_ledger.document_gaps.generate_report(filtered)
    assert report.stats.total_transactions == 0
    assert report.stats.transactions_without_docs == 0
    assert report.stats.unhandled_count == 0
    assert len(report.transaction_gaps) == 0
    assert len(report.account_summaries) == 0


def test_transactions_without_any_docs(example_ledger: FavaLedger) -> None:
    """Transactions without any document association should show up as gaps."""
    entries = [
        create.transaction(
            {},
            datetime.date(2024, 1, 1),
            "*",
            "Coffee Shop",
            "Morning coffee",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "5.0"),
        ),
        create.transaction(
            {},
            datetime.date(2024, 1, 2),
            "*",
            "Supermarket",
            "Groceries",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "50.0"),
        ),
    ]
    filtered = _make_filtered_from_entries(example_ledger, entries)
    report = example_ledger.document_gaps.generate_report(filtered)

    assert report.stats.total_transactions == 2
    assert report.stats.transactions_with_docs == 0
    assert report.stats.transactions_without_docs == 2
    assert report.stats.unhandled_count == 2
    assert len(report.transaction_gaps) == 2

    payees = {g.payee for g in report.transaction_gaps}
    assert payees == {"Coffee Shop", "Supermarket"}

    for gap in report.transaction_gaps:
        assert gap.has_document_metadata is False
        assert gap.has_linked_documents is False
        assert gap.handled is False


def test_transactions_with_document_metadata(example_ledger: FavaLedger) -> None:
    """Transactions with document metadata should NOT show up as gaps."""
    entries = [
        create.transaction(
            {"document": "receipt.pdf"},
            datetime.date(2024, 1, 1),
            "*",
            "Coffee Shop",
            "With receipt",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "5.0"),
        ),
        create.transaction(
            {"document2": "invoice.jpg"},
            datetime.date(2024, 1, 2),
            "*",
            "Supermarket",
            "With invoice",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "50.0"),
        ),
    ]
    filtered = _make_filtered_from_entries(example_ledger, entries)
    report = example_ledger.document_gaps.generate_report(filtered)

    assert report.stats.total_transactions == 2
    assert report.stats.transactions_with_docs == 2
    assert report.stats.transactions_without_docs == 0
    assert len(report.transaction_gaps) == 0


def test_transactions_linked_to_documents(example_ledger: FavaLedger) -> None:
    """Transactions sharing a link with a Document entry should NOT show gaps."""
    entries = [
        create.transaction(
            {},
            datetime.date(2024, 1, 1),
            "*",
            "Coffee Shop",
            "Linked via dok-link",
            frozenset(),
            frozenset({"dok-2024-01-01"}),
            _two_postings("Expenses:Food", "5.0"),
        ),
        create.document(
            {},
            datetime.date(2024, 1, 1),
            "Expenses:Food",
            "/path/to/receipt.pdf",
            frozenset({"linked"}),
            frozenset({"dok-2024-01-01"}),
        ),
        create.transaction(
            {},
            datetime.date(2024, 1, 2),
            "*",
            "Supermarket",
            "No link",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "50.0"),
        ),
    ]
    filtered = _make_filtered_from_entries(example_ledger, entries)
    report = example_ledger.document_gaps.generate_report(filtered)

    assert report.stats.total_transactions == 2
    assert report.stats.transactions_with_docs == 1
    assert report.stats.transactions_without_docs == 1
    assert len(report.transaction_gaps) == 1
    assert report.transaction_gaps[0].payee == "Supermarket"


def test_handled_gap_via_metadata(example_ledger: FavaLedger) -> None:
    """Gaps marked with document_gap_handled meta should show handled=True."""
    entries = [
        create.transaction(
            {"document_gap_handled": True},
            datetime.date(2024, 1, 1),
            "*",
            "Coffee Shop",
            "Handled",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "5.0"),
        ),
        create.transaction(
            {},
            datetime.date(2024, 1, 2),
            "*",
            "Supermarket",
            "Unhandled",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "50.0"),
        ),
    ]
    filtered = _make_filtered_from_entries(example_ledger, entries)

    report_all = example_ledger.document_gaps.generate_report(filtered)
    assert len(report_all.transaction_gaps) == 2
    assert report_all.stats.handled_count == 1
    assert report_all.stats.unhandled_count == 1

    report_unhandled = example_ledger.document_gaps.generate_report(
        filtered, only_unhandled=True
    )
    assert len(report_unhandled.transaction_gaps) == 1
    assert report_unhandled.transaction_gaps[0].payee == "Supermarket"
    assert report_unhandled.transaction_gaps[0].handled is False


def test_account_filter(example_ledger: FavaLedger) -> None:
    """Filtering by account prefix should include only transactions with matching postings."""
    entries = [
        create.transaction(
            {},
            datetime.date(2024, 1, 1),
            "*",
            "Coffee Shop",
            "Food expense",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food", "5.0"),
        ),
        create.transaction(
            {},
            datetime.date(2024, 1, 2),
            "*",
            "Gas Station",
            "Travel expense",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Travel", "30.0"),
        ),
        create.transaction(
            {},
            datetime.date(2024, 1, 3),
            "*",
            "Landlord",
            "Rent",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Home:Rent", "1000.0", "Assets:Bank"),
        ),
    ]
    filtered = _make_filtered_from_entries(example_ledger, entries)

    report_food = example_ledger.document_gaps.generate_report(
        filtered, account_filter="Expenses:Food"
    )
    assert len(report_food.transaction_gaps) == 1
    assert report_food.transaction_gaps[0].payee == "Coffee Shop"

    report_travel = example_ledger.document_gaps.generate_report(
        filtered, account_filter="Expenses:Travel"
    )
    assert len(report_travel.transaction_gaps) == 1
    assert report_travel.transaction_gaps[0].payee == "Gas Station"

    report_expenses = example_ledger.document_gaps.generate_report(
        filtered, account_filter="Expenses"
    )
    assert len(report_expenses.transaction_gaps) == 3


def test_account_summaries(example_ledger: FavaLedger) -> None:
    """Account summaries should aggregate by top-level account and be sorted by missing count descending."""
    entries = [
        create.transaction(
            {},
            datetime.date(2024, 1, 1),
            "*",
            "Coffee 1",
            "",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food:Cafe", "5.0"),
        ),
        create.transaction(
            {},
            datetime.date(2024, 1, 2),
            "*",
            "Coffee 2",
            "",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Food:Cafe", "3.0"),
        ),
        create.transaction(
            {},
            datetime.date(2024, 1, 3),
            "*",
            "Gas",
            "",
            frozenset(),
            frozenset(),
            _two_postings("Expenses:Travel", "30.0"),
        ),
    ]
    filtered = _make_filtered_from_entries(example_ledger, entries)
    report = example_ledger.document_gaps.generate_report(filtered)

    summaries = report.account_summaries
    assert len(summaries) > 0

    food_summary = next(
        (a for a in summaries if a.account == "Expenses:Food"), None
    )
    assert food_summary is not None
    assert food_summary.transactions_without_docs == 2
    assert food_summary.total_transactions == 2

    missing_counts = [a.transactions_without_docs for a in summaries]
    assert missing_counts == sorted(missing_counts, reverse=True)


def test_transaction_gap_attributes(example_ledger: FavaLedger) -> None:
    """Transaction gap objects should have all expected attributes with correct values."""
    entries = [
        create.transaction(
            {"tag": "value"},
            datetime.date(2024, 5, 15),
            "*",
            "Test Payee",
            "Test Narration",
            frozenset({"tag1", "tag2"}),
            frozenset({"link1"}),
            _two_postings("Expenses:Food", "25.5"),
        ),
    ]
    filtered = _make_filtered_from_entries(example_ledger, entries)
    report = example_ledger.document_gaps.generate_report(filtered)

    assert len(report.transaction_gaps) == 1
    gap = report.transaction_gaps[0]

    assert isinstance(gap, TransactionGap)
    assert gap.date == datetime.date(2024, 5, 15)
    assert gap.payee == "Test Payee"
    assert gap.narration == "Test Narration"
    assert "Expenses:Food" in gap.accounts
    assert "Assets:Cash" in gap.accounts
    assert gap.handled is False
    assert gap.tag_count == 2
    assert gap.link_count == 1
    assert isinstance(gap.entry_hash, str)
    assert len(gap.entry_hash) > 0


def test_stats_computation(example_ledger: FavaLedger) -> None:
    """Overall statistics should accurately reflect the ledger state."""
    entries = []
    for i in range(5):
        entries.append(
            create.transaction(
                {"document": f"receipt{i}.pdf"},
                datetime.date(2024, 1, i + 1),
                "*",
                f"Shop {i}",
                "",
                frozenset(),
                frozenset(),
                _two_postings("Expenses:Food", f"{i + 1}.0"),
            )
        )
    for i in range(3):
        entries.append(
            create.transaction(
                {},
                datetime.date(2024, 2, i + 1),
                "*",
                f"NoDoc {i}",
                "",
                frozenset(),
                frozenset(),
                _two_postings("Expenses:Food", f"{i + 1}.0"),
            )
        )

    filtered = _make_filtered_from_entries(example_ledger, entries)
    report = example_ledger.document_gaps.generate_report(filtered)

    assert report.stats.total_transactions == 8
    assert report.stats.transactions_with_docs == 5
    assert report.stats.transactions_without_docs == 3
    assert report.stats.handled_count == 0
    assert report.stats.unhandled_count == 3
    assert report.stats.total_accounts > 0
    assert report.stats.accounts_with_gaps > 0


def test_sorting_by_date_descending(example_ledger: FavaLedger) -> None:
    """Transaction gaps should be sorted by date in descending order."""
    entries = []
    for month in [1, 3, 2, 5, 4]:
        entries.append(
            create.transaction(
                {},
                datetime.date(2024, month, 1),
                "*",
                f"Month {month}",
                "",
                frozenset(),
                frozenset(),
                _two_postings("Expenses:Food", "10.0"),
            )
        )
    filtered = _make_filtered_from_entries(example_ledger, entries)
    report = example_ledger.document_gaps.generate_report(filtered)

    dates = [g.date for g in report.transaction_gaps]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == datetime.date(2024, 5, 1)
    assert dates[-1] == datetime.date(2024, 1, 1)


def test_checker_is_in_ledger(example_ledger: FavaLedger) -> None:
    """The document_gaps checker should be properly integrated into the FavaLedger."""
    assert hasattr(example_ledger, "document_gaps")
    assert isinstance(example_ledger.document_gaps, DocumentGapChecker)


def test_is_handled_with_different_value_types() -> None:
    """_is_handled should correctly detect handled status for various value types."""

    def _make_entry_with_meta(meta_value):
        return create.transaction(
            {"document_gap_handled": meta_value},
            datetime.date(2024, 1, 1),
            "*",
            "Test",
            "",
            frozenset(),
            frozenset(),
            [
                create.posting("Expenses:Food", create.amount(Decimal("10"), "USD")),
                create.posting("Assets:Cash", create.amount(Decimal("-10"), "USD")),
            ],
        )

    entry_bool_true = _make_entry_with_meta(True)
    assert _is_handled(entry_bool_true) is True

    entry_bool_false = _make_entry_with_meta(False)
    assert _is_handled(entry_bool_false) is False

    entry_none = create.transaction(
        {},
        datetime.date(2024, 1, 1),
        "*",
        "Test",
        "",
        frozenset(),
        frozenset(),
        [
            create.posting("Expenses:Food", create.amount(Decimal("10"), "USD")),
            create.posting("Assets:Cash", create.amount(Decimal("-10"), "USD")),
        ],
    )
    assert _is_handled(entry_none) is False

    entry_str_true = _make_entry_with_meta("True")
    assert _is_handled(entry_str_true) is True

    entry_str_true_lower = _make_entry_with_meta("true")
    assert _is_handled(entry_str_true_lower) is True

    entry_str_yes = _make_entry_with_meta("yes")
    assert _is_handled(entry_str_yes) is True

    entry_str_1 = _make_entry_with_meta("1")
    assert _is_handled(entry_str_1) is True

    entry_str_false = _make_entry_with_meta("false")
    assert _is_handled(entry_str_false) is False

    entry_str_random = _make_entry_with_meta("maybe")
    assert _is_handled(entry_str_random) is False


@pytest.fixture
def ledger_in_tmp_path(test_data_dir: Path, tmp_path: Path) -> FavaLedger:
    """Create a FavaLedger with edit-example.beancount in a tmp_path."""
    ledger_path = tmp_path / "edit-example.beancount"
    shutil.copy(test_data_dir / "edit-example.beancount", ledger_path)
    ledger_path.chmod(tmp_path.stat().st_mode)
    return FavaLedger(str(ledger_path))


def test_insert_handled_metadata_persists(
    ledger_in_tmp_path: FavaLedger,
) -> None:
    """Inserting document_gap_handled metadata should persist after reload."""
    entry = ledger_in_tmp_path.all_entries_by_type.Transaction[-1]
    entry_date = entry.date
    entry_payee = entry.payee
    entry_narration = entry.narration

    assert _is_handled(entry) is False

    entry_hash = hash_entry(entry)
    ledger_in_tmp_path.file.insert_metadata(
        entry_hash, "document_gap_handled", "True"
    )

    ledger_in_tmp_path.load_file()

    reloaded_entry = None
    for txn in ledger_in_tmp_path.all_entries_by_type.Transaction:
        if (
            txn.date == entry_date
            and txn.payee == entry_payee
            and txn.narration == entry_narration
        ):
            reloaded_entry = txn
            break

    assert reloaded_entry is not None
    assert _is_handled(reloaded_entry) is True


def test_remove_handled_metadata_persists(
    ledger_in_tmp_path: FavaLedger,
) -> None:
    """Removing document_gap_handled metadata should persist after reload."""
    entry = ledger_in_tmp_path.all_entries_by_type.Transaction[-1]
    entry_date = entry.date
    entry_payee = entry.payee
    entry_narration = entry.narration

    entry_hash = hash_entry(entry)
    ledger_in_tmp_path.file.insert_metadata(
        entry_hash, "document_gap_handled", "True"
    )
    ledger_in_tmp_path.load_file()

    inserted_entry = None
    for txn in ledger_in_tmp_path.all_entries_by_type.Transaction:
        if (
            txn.date == entry_date
            and txn.payee == entry_payee
            and txn.narration == entry_narration
        ):
            inserted_entry = txn
            break

    assert inserted_entry is not None
    assert _is_handled(inserted_entry) is True

    inserted_hash = hash_entry(inserted_entry)
    ledger_in_tmp_path.file.remove_metadata(
        inserted_hash, "document_gap_handled"
    )
    ledger_in_tmp_path.load_file()

    final_entry = None
    for txn in ledger_in_tmp_path.all_entries_by_type.Transaction:
        if (
            txn.date == entry_date
            and txn.payee == entry_payee
            and txn.narration == entry_narration
        ):
            final_entry = txn
            break

    assert final_entry is not None
    assert _is_handled(final_entry) is False


def test_remove_metadata_from_file_directly(tmp_path: Path) -> None:
    """remove_metadata_from_file should correctly remove metadata lines."""
    file_content = dedent("""\
        2016-02-26 * "Uncle Boons" "Eating out alone"
            document_gap_handled: "True"
            document: "receipt.pdf"
            Liabilities:US:Chase:Slate                       -24.84 USD
            Expenses:Food:Restaurant                          24.84 USD
        """)
    samplefile = tmp_path / "example.beancount"
    samplefile.write_text(file_content)

    remove_metadata_from_file(samplefile, 1, "document_gap_handled")

    result = samplefile.read_text("utf-8")
    assert "document_gap_handled" not in result
    assert 'document: "receipt.pdf"' in result
    assert "Liabilities:US:Chase:Slate" in result


def test_remove_metadata_nonexistent_key_noop(tmp_path: Path) -> None:
    """Removing a non-existent metadata key should be a no-op."""
    file_content = dedent("""\
        2016-02-26 * "Uncle Boons" "Eating out alone"
            Liabilities:US:Chase:Slate                       -24.84 USD
            Expenses:Food:Restaurant                          24.84 USD
        """)
    samplefile = tmp_path / "example.beancount"
    samplefile.write_text(file_content)
    original = samplefile.read_text("utf-8")

    remove_metadata_from_file(samplefile, 1, "nonexistent_key")

    assert samplefile.read_text("utf-8") == original


def test_handled_count_in_report_after_metadata_insert(
    ledger_in_tmp_path: FavaLedger,
) -> None:
    """After inserting handled metadata, the report should reflect it correctly."""
    txns = ledger_in_tmp_path.all_entries_by_type.Transaction

    gap_entry = None
    for txn in txns:
        has_doc_meta = any(
            isinstance(v, str) and k.lower().startswith("document")
            for k, v in txn.meta.items()
        )
        if not has_doc_meta:
            gap_entry = txn
            break

    assert gap_entry is not None, "Need at least one transaction without docs"

    entry_date = gap_entry.date
    entry_payee = gap_entry.payee
    entry_narration = gap_entry.narration

    report_before = ledger_in_tmp_path.document_gaps.generate_report(
        ledger_in_tmp_path.get_filtered()
    )
    initial_handled = report_before.stats.handled_count

    entry_hash = hash_entry(gap_entry)
    ledger_in_tmp_path.file.insert_metadata(
        entry_hash, "document_gap_handled", "True"
    )
    ledger_in_tmp_path.load_file()

    report_after = ledger_in_tmp_path.document_gaps.generate_report(
        ledger_in_tmp_path.get_filtered()
    )
    assert report_after.stats.handled_count == initial_handled + 1


def test_only_unhandled_filter_with_persisted_metadata(
    ledger_in_tmp_path: FavaLedger,
) -> None:
    """only_unhandled filter should correctly exclude persisted handled entries."""
    txns = ledger_in_tmp_path.all_entries_by_type.Transaction

    gap_entry = None
    for txn in txns:
        has_doc_meta = any(
            isinstance(v, str) and k.lower().startswith("document")
            for k, v in txn.meta.items()
        )
        if not has_doc_meta:
            gap_entry = txn
            break

    assert gap_entry is not None, "Need at least one transaction without docs"

    report_before = ledger_in_tmp_path.document_gaps.generate_report(
        ledger_in_tmp_path.get_filtered(), only_unhandled=True
    )
    initial_gaps = len(report_before.transaction_gaps)

    entry_hash = hash_entry(gap_entry)
    ledger_in_tmp_path.file.insert_metadata(
        entry_hash, "document_gap_handled", "True"
    )
    ledger_in_tmp_path.load_file()

    report_after = ledger_in_tmp_path.document_gaps.generate_report(
        ledger_in_tmp_path.get_filtered(), only_unhandled=True
    )
    assert len(report_after.transaction_gaps) == initial_gaps - 1
