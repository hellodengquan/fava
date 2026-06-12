"""Suspicious transaction review module.

This module provides functionality for marking transactions as suspicious
and generating review lists aggregated by account and time period.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fava.beans.abc import Transaction
from fava.beans.funcs import hash_entry
from fava.core.module_base import FavaModule
from fava.util.date import DateRange
from fava.util.date import Interval

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from fava.beans.abc import Directive


SUSPICIOUS_META_KEY = "suspicious"


@dataclass(frozen=True)
class SuspiciousTransaction:
    """A suspicious transaction with entry hash and details."""

    entry_hash: str
    date: date
    payee: str
    narration: str
    accounts: list[str]
    suspicious_reason: str | None


@dataclass(frozen=True)
class SuspiciousByAccount:
    """Suspicious transactions aggregated by account."""

    account: str
    count: int
    transactions: list[SuspiciousTransaction]


@dataclass(frozen=True)
class SuspiciousByTime:
    """Suspicious transactions aggregated by time period."""

    period: str
    date_range: DateRange
    count: int
    by_account: list[SuspiciousByAccount]


def is_suspicious(entry: Directive) -> bool:
    """Check if an entry is marked as suspicious.

    Args:
        entry: A directive entry.

    Returns:
        True if the entry has a 'suspicious' metadata key.
    """
    if not hasattr(entry, "meta") or not entry.meta:
        return False
    return SUSPICIOUS_META_KEY in entry.meta


def get_suspicious_reason(entry: Directive) -> str | None:
    """Get the suspicious reason from an entry's metadata.

    Args:
        entry: A directive entry.

    Returns:
        The suspicious reason string or None.
    """
    if not hasattr(entry, "meta") or not entry.meta:
        return None
    value = entry.meta.get(SUSPICIOUS_META_KEY)
    return str(value) if value else None


class SuspiciousModule(FavaModule):
    """Module for managing suspicious transaction marking and review."""

    def load_file(self) -> None:
        """Run when the file has been (re)loaded."""

    @property
    def all_suspicious_transactions(self) -> list[SuspiciousTransaction]:
        """Get all suspicious transactions from the ledger.

        Returns:
            A list of all suspicious transactions.
        """
        result: list[SuspiciousTransaction] = []
        for entry in self.ledger.all_entries:
            if isinstance(entry, Transaction) and is_suspicious(entry):
                accounts = [posting.account for posting in entry.postings]
                result.append(
                    SuspiciousTransaction(
                        entry_hash=hash_entry(entry),
                        date=entry.date,
                        payee=entry.payee or "",
                        narration=entry.narration or "",
                        accounts=accounts,
                        suspicious_reason=get_suspicious_reason(entry),
                    )
                )
        return result

    def by_account(
        self, entries: Sequence[Directive] | None = None
    ) -> list[SuspiciousByAccount]:
        """Aggregate suspicious transactions by account.

        Args:
            entries: Entries to consider. If None, use all entries.

        Returns:
            List of suspicious transaction counts grouped by account.
        """
        if entries is None:
            entries = self.ledger.all_entries

        account_map: dict[str, list[SuspiciousTransaction]] = {}
        seen: dict[str, set[str]] = {}

        for entry in entries:
            if isinstance(entry, Transaction) and is_suspicious(entry):
                transaction = SuspiciousTransaction(
                    entry_hash=hash_entry(entry),
                    date=entry.date,
                    payee=entry.payee or "",
                    narration=entry.narration or "",
                    accounts=[p.account for p in entry.postings],
                    suspicious_reason=get_suspicious_reason(entry),
                )
                for posting in entry.postings:
                    account = posting.account
                    if account not in seen:
                        seen[account] = set()
                        account_map[account] = []
                    if transaction.entry_hash not in seen[account]:
                        seen[account].add(transaction.entry_hash)
                        account_map[account].append(transaction)

        result = [
            SuspiciousByAccount(
                account=account,
                count=len(transactions),
                transactions=transactions,
            )
            for account, transactions in sorted(account_map.items())
        ]
        return result

    def by_time(
        self,
        interval: Interval,
        entries: Sequence[Directive] | None = None,
    ) -> list[SuspiciousByTime]:
        """Aggregate suspicious transactions by time period.

        Args:
            interval: The time interval to group by.
            entries: Entries to consider. If None, use all entries.

        Returns:
            List of suspicious transaction counts grouped by time period.
        """
        if entries is None:
            entries = self.ledger.all_entries

        suspicious_entries = [
            entry
            for entry in entries
            if isinstance(entry, Transaction) and is_suspicious(entry)
        ]

        if not suspicious_entries:
            return []

        start_date = min(e.date for e in suspicious_entries)
        end_date = max(e.date for e in suspicious_entries)

        from fava.util.date import dateranges
        from datetime import timedelta

        adjusted_end = end_date + timedelta(days=1)
        periods = list(dateranges(start_date, adjusted_end, interval, complete=False))

        result: list[SuspiciousByTime] = []

        for period_range in periods:
            period_transactions = [
                entry
                for entry in suspicious_entries
                if period_range.begin <= entry.date < period_range.end
            ]

            if not period_transactions:
                continue

            account_map: dict[str, list[SuspiciousTransaction]] = {}
            seen: dict[str, set[str]] = {}

            for entry in period_transactions:
                transaction = SuspiciousTransaction(
                    entry_hash=hash_entry(entry),
                    date=entry.date,
                    payee=entry.payee or "",
                    narration=entry.narration or "",
                    accounts=[p.account for p in entry.postings],
                    suspicious_reason=get_suspicious_reason(entry),
                )
                for posting in entry.postings:
                    account = posting.account
                    if account not in seen:
                        seen[account] = set()
                        account_map[account] = []
                    if transaction.entry_hash not in seen[account]:
                        seen[account].add(transaction.entry_hash)
                        account_map[account].append(transaction)

            by_account = [
                SuspiciousByAccount(
                    account=account,
                    count=len(transactions),
                    transactions=transactions,
                )
                for account, transactions in sorted(account_map.items())
            ]

            result.append(
                SuspiciousByTime(
                    period=str(period_range),
                    date_range=period_range,
                    count=len(period_transactions),
                    by_account=by_account,
                )
            )

        return result

    def mark_suspicious(
        self, entry_hash: str, reason: str = "suspicious"
    ) -> None:
        """Mark an entry as suspicious.

        Args:
            entry_hash: Hash of the entry to mark.
            reason: Reason for marking as suspicious.
        """
        self.ledger.file.insert_metadata(entry_hash, SUSPICIOUS_META_KEY, reason)

    def unmark_suspicious(self, entry_hash: str) -> bool:
        """Remove suspicious mark from an entry.

        Args:
            entry_hash: Hash of the entry to unmark.

        Returns:
            True if the suspicious mark was found and removed.
        """
        return self.ledger.file.remove_metadata(entry_hash, SUSPICIOUS_META_KEY)
