"""Helpers for Beancount entries."""

from __future__ import annotations

from bisect import bisect_left
from operator import attrgetter
from typing import Any
from typing import TYPE_CHECKING
from typing import TypeVar

if TYPE_CHECKING:  # pragma: no cover
    import datetime
    from collections.abc import Sequence

    from fava.beans.abc import Directive
    from fava.beans.abc import Posting
    from fava.beans.abc import Transaction

    T = TypeVar("T", bound=Directive | Posting)


def replace(entry: T, **kwargs: Any) -> T:
    """Create a copy of the given directive, replacing some arguments."""
    if hasattr(entry, "_replace"):
        return entry._replace(**kwargs)  # type: ignore[no-any-return]  # ty:ignore[call-non-callable]
    msg = f"Could not replace attribute in type {type(entry)}"
    raise TypeError(msg)


_get_date = attrgetter("date")


def slice_entry_dates(
    entries: Sequence[T], begin: datetime.date, end: datetime.date
) -> Sequence[T]:
    """Get slice of entries in a date window.

    Args:
        entries: A date-sorted list of dated directives.
        begin: The first date to include.
        end: One day beyond the last date.

    Returns:
        The slice between the given dates.
    """
    index_begin = bisect_left(entries, begin, key=_get_date)
    index_end = bisect_left(entries, end, key=_get_date)
    return entries[index_begin:index_end]


def is_system_generated_transaction(entry: Directive) -> bool:
    """Check if an entry is a system-generated transaction.

    System-generated transactions include opening balance summarizations,
    transfer entries from clamp operations, and conversion entries.
    These entries are not actual user transactions and should be excluded
    from transaction statistics.

    Args:
        entry: The directive to check.

    Returns:
        True if the entry is a system-generated transaction, False otherwise.
    """
    from fava.beans.abc import Transaction

    if not isinstance(entry, Transaction):
        return False
    filename = entry.meta.get("filename", "")
    return filename.startswith("<")


def is_actual_transaction(entry: Directive) -> bool:
    """Check if an entry is an actual user transaction.

    This excludes system-generated transactions like opening balance
    summarizations.

    Args:
        entry: The directive to check.

    Returns:
        True if the entry is an actual user transaction, False otherwise.
    """
    from fava.beans.abc import Transaction

    if not isinstance(entry, Transaction):
        return False
    return not is_system_generated_transaction(entry)


def filter_actual_transactions(entries: Sequence[Directive]) -> list[Transaction]:
    """Filter a list of entries to include only actual user transactions.

    This excludes system-generated transactions like opening balance
    summarizations.

    Args:
        entries: A list of directives.

    Returns:
        A list of only actual user transactions.
    """
    from fava.beans.abc import Transaction

    return [e for e in entries if is_actual_transaction(e)]
