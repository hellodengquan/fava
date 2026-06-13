"""Specify types for the flask application context."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from fava.core import ReportContext
from fava.core.conversion import conversion_from_str
from fava.util.date import INTERVALS
from fava.util.date import Month

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger
    from fava.core import FilteredLedger
    from fava.core.conversion import Conversion
    from fava.ext import FavaExtensionBase
    from fava.util.date import Interval


class Context:
    """The context values - this is used for `flask.g`."""

    #: Slug for the active Beancount file.
    beancount_file_slug: str | None
    #: The ledger
    ledger: FavaLedger
    #: The current extension, if this is an extension endpoint
    extension: FavaExtensionBase | None

    @cached_property
    def report_context(self) -> ReportContext:
        """The unified report filter context.

        This provides a single source of truth for all filtering and display
        parameters (time, account, filter, conversion, interval).
        All other properties that depend on these parameters should derive
        from this context to ensure consistency.
        """
        return ReportContext.from_request()

    @cached_property
    def conversion(self) -> str:
        """Conversion to apply (raw string)."""
        return self.report_context.conversion

    @cached_property
    def conv(self) -> Conversion:
        """Conversion to apply (parsed)."""
        return self.report_context.parsed_conversion

    @cached_property
    def interval(self) -> Interval:
        """Interval to group by."""
        return self.report_context.parsed_interval

    @cached_property
    def filtered(self) -> FilteredLedger:
        """The filtered ledger."""
        return self.report_context.create_filtered_ledger(self.ledger)
