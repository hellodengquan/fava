"""Helpers for Beancount entries."""

from __future__ import annotations

from bisect import bisect_left
from operator import attrgetter
from typing import Any
from typing import Callable
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


# ============================================================================
# System entry identification with pluggable rules
# ============================================================================

_SystemEntryRule = Callable[["Directive"], bool]
"""Type alias for a system entry identification rule."""

_system_entry_rules: list[_SystemEntryRule] = []
"""List of registered rules for identifying system-generated entries."""


def _rule_filename_angular_bracket(entry: Directive) -> bool:
    """Rule: Transaction with meta.filename starting with '<'.

    Beancount's clamp_opt function creates summarization entries with
    filenames like '<internal>', '<conversion>', etc. The leading '<'
    indicates a programmatically generated entry rather than one from
    a user's ledger file.

    Args:
        entry: The directive to check.

    Returns:
        True if the entry is a Transaction with a '<' prefixed filename.
    """
    from fava.beans.abc import Transaction

    if not isinstance(entry, Transaction):
        return False
    filename = entry.meta.get("filename", "")
    return filename.startswith("<")


def _rule_meta_system_flag(entry: Directive) -> bool:
    """Rule: Entry with a 'system' flag in its meta dict.

    Entries marked with meta.system = True are considered system-generated.
    This provides a standard way for plugins and modules to tag entries
    as system-generated without relying on filename patterns.

    The 'system' key can be:
    - A boolean True value
    - A truthy string (e.g. "true", "1", "yes")
    - Any truthy value

    Args:
        entry: The directive to check.

    Returns:
        True if the entry's meta dict contains a truthy 'system' key.
    """
    from fava.beans.abc import Transaction

    if not isinstance(entry, Transaction):
        return False
    system_flag = entry.meta.get("system", False)
    return bool(system_flag)


def register_system_entry_rule(rule: _SystemEntryRule) -> None:
    """Register a new rule for identifying system-generated entries.

    Rules are callables that take a Directive and return True if the
    entry should be considered system-generated. All registered rules
    are checked in order, and *any* rule returning True will cause
    the entry to be classified as system-generated.

    Built-in rules (registered by default):
    1. Filename angular bracket rule: meta.filename starts with '<'
    2. Meta system flag rule: meta.system is truthy

    Args:
        rule: A callable that takes a Directive and returns a bool.
              True means the entry is system-generated.

    Example::

        from fava.beans.helpers import register_system_entry_rule

        def my_custom_rule(entry):
            return entry.meta.get("source") == "auto-generated"

        register_system_entry_rule(my_custom_rule)

    """
    if rule not in _system_entry_rules:
        _system_entry_rules.append(rule)


def reset_system_entry_rules() -> None:
    """Reset system entry rules to the default set.

    This removes all custom-registered rules and restores only the
    built-in default rules. Useful for testing or when you need to
    clear all custom rules.
    """
    _system_entry_rules.clear()
    register_system_entry_rule(_rule_filename_angular_bracket)
    register_system_entry_rule(_rule_meta_system_flag)


def is_system_entry(entry: Directive) -> bool:
    """Check if an entry is a system-generated entry.

    System-generated entries include opening balance summarizations,
    transfer entries from clamp operations, and conversion entries
    added by Beancount's clamp_opt function. These entries are not
    actual user transactions and should be excluded from transaction
    statistics.

    Identification uses a pluggable rule system. See
    :func:`register_system_entry_rule` for adding custom rules.

    Default identification rules:
    1. **Filename angular bracket rule**: Transaction entries with
       ``meta.filename`` starting with ``'<'`` are system-generated.
    2. **Meta system flag rule**: Transaction entries with a truthy
       ``meta.system`` flag are system-generated.

    Args:
        entry: The directive to check.

    Returns:
        True if the entry is system-generated, False otherwise.
        Only Transaction entries can be system-generated; all other
        entry types (Open, Close, Note, Document, etc.) return False.
    """
    from fava.beans.abc import Transaction

    if not isinstance(entry, Transaction):
        return False
    return any(rule(entry) for rule in _system_entry_rules)


# Initialize with default rules
reset_system_entry_rules()


def is_system_generated_transaction(entry: Directive) -> bool:
    """Check if an entry is a system-generated transaction.

    .. deprecated::
        Use :func:`is_system_entry` instead. This function is kept
        for backward compatibility.

    System-generated transactions include opening balance summarizations,
    transfer entries from clamp operations, and conversion entries.
    These entries are not actual user transactions and should be excluded
    from transaction statistics.

    Args:
        entry: The directive to check.

    Returns:
        True if the entry is a system-generated transaction, False otherwise.
    """
    return is_system_entry(entry)


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
    return not is_system_entry(entry)


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


def filter_system_generated(entries: Sequence[Directive]) -> list[Directive]:
    """Filter a list of entries to exclude system-generated entries.

    This excludes system-generated transactions like opening balance
    summarizations, but preserves all other entry types (Open, Close,
    Note, Document, etc.).

    Args:
        entries: A list of directives.

    Returns:
        A list of directives with system-generated entries removed.
    """
    return [e for e in entries if not is_system_entry(e)]
