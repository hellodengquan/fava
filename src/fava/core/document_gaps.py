"""Document gap checking functionality.

This module provides functionality to check for missing documents/receipts
for transactions, both by transaction and by account dimensions.
It supports filtering, marking items as handled, and viewing statistics.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fava.beans.abc import Document
from fava.beans.abc import Transaction
from fava.beans.funcs import hash_entry
from fava.beans.helpers import replace

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Sequence
    from datetime import date
    from decimal import Decimal

    from fava.beans.abc import Directive
    from fava.beans.abc import Posting
    from fava.core import FilteredLedger
    from fava.core import FavaLedger


@dataclass(frozen=True)
class TransactionGap:
    """A transaction that is missing associated documents."""

    entry_hash: str
    date: date
    payee: str
    narration: str
    accounts: list[str]
    total_amount: str
    has_document_metadata: bool
    has_linked_documents: bool
    handled: bool
    tag_count: int
    link_count: int


@dataclass(frozen=True)
class AccountGapSummary:
    """Summary of document gaps for a single account."""

    account: str
    total_transactions: int
    transactions_with_docs: int
    transactions_without_docs: int
    handled_count: int
    total_amount: str
    missing_amount: str


@dataclass(frozen=True)
class DocumentGapStats:
    """Overall statistics for document gaps."""

    total_transactions: int
    transactions_with_docs: int
    transactions_without_docs: int
    handled_count: int
    unhandled_count: int
    total_amount: str
    missing_amount: str
    accounts_with_gaps: int
    total_accounts: int


@dataclass(frozen=True)
class DocumentGapReport:
    """Complete document gap report."""

    stats: DocumentGapStats
    transaction_gaps: list[TransactionGap]
    account_summaries: list[AccountGapSummary]


def _posting_total_amount(postings: Sequence[Posting]) -> str:
    """Calculate a representative total amount string from postings.

    Takes the first non-zero amount as the representative total.
    """
    for posting in postings:
        units = getattr(posting, "units", None)
        if units and units.number:
            return f"{units.number} {units.currency}"
    return ""


def _has_document_metadata(entry: Directive) -> bool:
    """Check if entry has document-related metadata keys."""
    return any(
        isinstance(v, str) and k.lower().startswith("document")
        for k, v in entry.meta.items()
    )


def _is_handled(entry: Directive) -> bool:
    """Check if a transaction has been marked as having its document gap handled."""
    value = entry.meta.get("document_gap_handled", None)
    return value is not None and value is not False


def _build_document_link_set(
    documents: Sequence[Document],
) -> set[str]:
    """Build a set of all links referenced by documents."""
    links: set[str] = set()
    for doc in documents:
        for link in doc.links:
            links.add(link)
    return links


def _transaction_has_linked_document(
    txn: Transaction, document_links: set[str]
) -> bool:
    """Check if transaction shares any link with a document."""
    return any(link in document_links for link in txn.links)


def _transaction_accounts(txn: Transaction) -> list[str]:
    """Get all unique accounts from a transaction's postings."""
    return list({posting.account for posting in txn.postings})


def _account_root(account: str, depth: int = 2) -> str:
    """Get the root of an account up to given depth."""
    parts = account.split(":")
    return ":".join(parts[:depth]) if len(parts) > depth else account


class DocumentGapChecker:
    """Check for missing documents in transactions."""

    def __init__(self, ledger: FavaLedger) -> None:
        self.ledger = ledger

    def _all_transactions(
        self, filtered: FilteredLedger
    ) -> list[tuple[int, Transaction]]:
        """Get all transactions from the filtered ledger."""
        return [
            (idx, entry)
            for idx, entry in enumerate(filtered.entries)
            if isinstance(entry, Transaction)
        ]

    def check_transaction_gaps(
        self,
        filtered: FilteredLedger,
        *,
        only_unhandled: bool = False,
        account_filter: str = "",
    ) -> list[TransactionGap]:
        """Find all transactions missing associated documents.

        Args:
            filtered: The filtered ledger to check.
            only_unhandled: If True, only return unhandled gaps.
            account_filter: If non-empty, only include transactions with
                           postings to accounts starting with this string.

        Returns:
            List of TransactionGap for transactions without documents.
        """
        documents = [
            entry
            for entry in filtered.entries
            if isinstance(entry, Document)
        ]
        document_links = _build_document_link_set(documents)
        transactions = self._all_transactions(filtered)

        gaps: list[TransactionGap] = []
        for _idx, txn in transactions:
            txn_accounts = _transaction_accounts(txn)

            if account_filter:
                if not any(
                    acc.startswith(account_filter) for acc in txn_accounts
                ):
                    continue

            has_meta_doc = _has_document_metadata(txn)
            has_linked = _transaction_has_linked_document(txn, document_links)
            has_any_doc = has_meta_doc or has_linked

            if not has_any_doc:
                handled = _is_handled(txn)
                if only_unhandled and handled:
                    continue

                gaps.append(
                    TransactionGap(
                        entry_hash=hash_entry(txn),
                        date=txn.date,
                        payee=txn.payee or "",
                        narration=txn.narration or "",
                        accounts=txn_accounts,
                        total_amount=_posting_total_amount(txn.postings),
                        has_document_metadata=has_meta_doc,
                        has_linked_documents=has_linked,
                        handled=handled,
                        tag_count=len(txn.tags),
                        link_count=len(txn.links),
                    )
                )

        gaps.sort(key=lambda g: g.date, reverse=True)
        return gaps

    def account_summaries(
        self,
        filtered: FilteredLedger,
        transaction_gaps: list[TransactionGap],
    ) -> list[AccountGapSummary]:
        """Generate account-level summary of document gaps.

        Args:
            filtered: The filtered ledger.
            transaction_gaps: Pre-computed list of transaction gaps.

        Returns:
            List of AccountGapSummary, sorted by missing count descending.
        """
        documents = [
            entry
            for entry in filtered.entries
            if isinstance(entry, Document)
        ]
        document_links = _build_document_link_set(documents)
        transactions = self._all_transactions(filtered)

        gap_by_hash = {g.entry_hash: g for g in transaction_gaps}

        account_stats: dict[str, dict] = defaultdict(
            lambda: {
                "total": 0,
                "with_docs": 0,
                "without_docs": 0,
                "handled": 0,
                "total_amount_str": "",
                "missing_amount_str": "",
            }
        )

        all_amounts: dict[str, list[Decimal]] = defaultdict(list)
        missing_amounts: dict[str, list[Decimal]] = defaultdict(list)

        for _idx, txn in transactions:
            txn_hash = hash_entry(txn)
            has_meta_doc = _has_document_metadata(txn)
            has_linked = _transaction_has_linked_document(txn, document_links)
            has_any_doc = has_meta_doc or has_linked
            handled = _is_handled(txn)
            gap_missing = txn_hash in gap_by_hash

            for posting in txn.postings:
                account_root = _account_root(posting.account)
                stats = account_stats[account_root]
                stats["total"] += 1

                if has_any_doc:
                    stats["with_docs"] += 1
                else:
                    stats["without_docs"] += 1
                    if handled:
                        stats["handled"] += 1

                units = getattr(posting, "units", None)
                if units and units.number:
                    if not has_any_doc:
                        missing_amounts[account_root].append(
                            abs(units.number)
                        )
                    all_amounts[account_root].append(abs(units.number))

        summaries: list[AccountGapSummary] = []
        for account, stats in sorted(account_stats.items()):
            all_sum = (
                f"{sum(all_amounts[account])}" if all_amounts[account] else ""
            )
            miss_sum = (
                f"{sum(missing_amounts[account])}"
                if missing_amounts[account]
                else ""
            )

            summaries.append(
                AccountGapSummary(
                    account=account,
                    total_transactions=stats["total"],
                    transactions_with_docs=stats["with_docs"],
                    transactions_without_docs=stats["without_docs"],
                    handled_count=stats["handled"],
                    total_amount=all_sum,
                    missing_amount=miss_sum,
                )
            )

        summaries.sort(
            key=lambda s: s.transactions_without_docs, reverse=True
        )
        return summaries

    def compute_statistics(
        self,
        filtered: FilteredLedger,
        transaction_gaps: list[TransactionGap],
    ) -> DocumentGapStats:
        """Compute overall statistics for document gaps.

        Args:
            filtered: The filtered ledger.
            transaction_gaps: Pre-computed list of transaction gaps.

        Returns:
            DocumentGapStats with overall summary.
        """
        documents = [
            entry
            for entry in filtered.entries
            if isinstance(entry, Document)
        ]
        document_links = _build_document_link_set(documents)
        transactions = self._all_transactions(filtered)

        total_txn = len(transactions)
        with_docs = 0
        handled = sum(1 for g in transaction_gaps if g.handled)
        unhandled = len(transaction_gaps) - handled

        all_amounts: list[Decimal] = []
        missing_amounts: list[Decimal] = []

        accounts_with_gaps: set[str] = set()
        all_accounts: set[str] = set()

        for _idx, txn in transactions:
            has_meta_doc = _has_document_metadata(txn)
            has_linked = _transaction_has_linked_document(txn, document_links)
            has_any_doc = has_meta_doc or has_linked

            if has_any_doc:
                with_docs += 1

            for posting in txn.postings:
                all_accounts.add(_account_root(posting.account))
                units = getattr(posting, "units", None)
                if units and units.number:
                    if not has_any_doc:
                        missing_amounts.append(abs(units.number))
                        accounts_with_gaps.add(
                            _account_root(posting.account)
                        )
                    all_amounts.append(abs(units.number))

        total_amount = f"{sum(all_amounts)}" if all_amounts else ""
        missing_amount = (
            f"{sum(missing_amounts)}" if missing_amounts else ""
        )

        return DocumentGapStats(
            total_transactions=total_txn,
            transactions_with_docs=with_docs,
            transactions_without_docs=total_txn - with_docs,
            handled_count=handled,
            unhandled_count=unhandled,
            total_amount=total_amount,
            missing_amount=missing_amount,
            accounts_with_gaps=len(accounts_with_gaps),
            total_accounts=len(all_accounts),
        )

    def generate_report(
        self,
        filtered: FilteredLedger,
        *,
        only_unhandled: bool = False,
        account_filter: str = "",
    ) -> DocumentGapReport:
        """Generate a complete document gap report.

        Args:
            filtered: The filtered ledger to check.
            only_unhandled: If True, only return unhandled gaps in the list.
            account_filter: If non-empty, only include matching transactions.

        Returns:
            DocumentGapReport with stats, gaps, and account summaries.
        """
        gaps = self.check_transaction_gaps(
            filtered, only_unhandled=only_unhandled, account_filter=account_filter
        )
        stats = self.compute_statistics(filtered, gaps)
        accounts = self.account_summaries(filtered, gaps)
        return DocumentGapReport(stats=stats, transaction_gaps=gaps, account_summaries=accounts)
