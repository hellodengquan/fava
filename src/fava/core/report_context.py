"""Unified report filter context.

This module provides a unified context for report filtering that encapsulates
all parameters used across different reports (time, account, filter, conversion,
interval). This ensures consistent parameter parsing and data source usage
between charts and tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import request

from fava.core.conversion import conversion_from_str
from fava.util.date import INTERVALS
from fava.util.date import Month

if TYPE_CHECKING:
    from fava.core.conversion import Conversion
    from fava.core import FavaLedger
    from fava.core import FilteredLedger
    from fava.util.date import Interval


@dataclass(frozen=True)
class ReportContext:
    """Unified context for report filtering parameters.

    This class encapsulates all filtering and display parameters used by
    Fava's reports. It provides a single source of truth for parameter
    parsing, ensuring that both chart data and table data are derived
    from the same filtering context.

    Attributes:
        time: Time filter string (e.g., "2024", "2024-Q1", "2024-01-01").
        account: Account filter string (account name or regex pattern).
        filter: Advanced filter string in Fava's filter query language.
        conversion: Conversion mode string (e.g., "at_cost", "USD", "EUR").
        interval: Interval string for grouping data (e.g., "month", "year").
    """

    time: str = ""
    account: str = ""
    filter: str = ""
    conversion: str = "at_cost"
    interval: str = "month"

    @classmethod
    def from_request(cls) -> "ReportContext":
        """Create a ReportContext from the current Flask request.

        Extracts all filter parameters from the request's query string.
        This is the primary way to create a context for HTTP requests.

        Returns:
            A ReportContext populated from request arguments.
        """
        args = request.args
        return cls(
            time=args.get("time", ""),
            account=args.get("account", ""),
            filter=args.get("filter", ""),
            conversion=args.get("conversion", "") or "at_cost",
            interval=args.get("interval", "").lower() or "month",
        )

    @classmethod
    def from_dict(cls, params: dict[str, str]) -> "ReportContext":
        """Create a ReportContext from a dictionary of parameters.

        Useful for testing or when parameters come from a different source
        than the HTTP request.

        Args:
            params: Dictionary containing filter parameters.

        Returns:
            A ReportContext populated from the dictionary.
        """
        return cls(
            time=params.get("time", ""),
            account=params.get("account", ""),
            filter=params.get("filter", ""),
            conversion=params.get("conversion", "") or "at_cost",
            interval=params.get("interval", "").lower() or "month",
        )

    def to_dict(self) -> dict[str, str]:
        """Convert the context to a dictionary of parameters.

        Returns:
            Dictionary with all non-empty context parameters.
        """
        result: dict[str, str] = {}
        if self.time:
            result["time"] = self.time
        if self.account:
            result["account"] = self.account
        if self.filter:
            result["filter"] = self.filter
        if self.conversion and self.conversion != "at_cost":
            result["conversion"] = self.conversion
        if self.interval and self.interval != "month":
            result["interval"] = self.interval
        return result

    @property
    def parsed_conversion(self) -> Conversion:
        """Get the parsed conversion object.

        Returns:
            The Conversion object parsed from the conversion string.
        """
        return conversion_from_str(self.conversion)

    @property
    def parsed_interval(self) -> Interval:
        """Get the parsed interval object.

        Returns:
            The Interval object parsed from the interval string.
        """
        return INTERVALS.get(self.interval, Month)

    def create_filtered_ledger(self, ledger: FavaLedger) -> FilteredLedger:
        """Create a FilteredLedger from this context.

        This ensures that the FilteredLedger uses the same parameters
        as the rest of the report context.

        Args:
            ledger: The FavaLedger to filter.

        Returns:
            A FilteredLedger configured with this context's parameters.
        """
        return ledger.get_filtered(
            account=self.account,
            filter=self.filter,
            time=self.time,
        )

    def url_params(self) -> dict[str, str]:
        """Get parameters for use in URL generation.

        Returns:
            Dictionary of parameters suitable for URL search params.
        """
        return {
            "time": self.time,
            "account": self.account,
            "filter": self.filter,
            "conversion": self.conversion,
            "interval": self.interval,
        }

    def __repr__(self) -> str:
        return (
            f"ReportContext(time={self.time!r}, account={self.account!r}, "
            f"filter={self.filter!r}, conversion={self.conversion!r}, "
            f"interval={self.interval!r})"
        )
