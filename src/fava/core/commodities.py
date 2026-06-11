"""Attributes for auto-completion."""

from __future__ import annotations

from contextlib import suppress
from decimal import Decimal
from typing import TYPE_CHECKING

from fava.core.module_base import FavaModule

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger


class CommoditiesModule(FavaModule):
    """Details about the currencies and commodities.

    Provides unified commodity alias canonicalization to ensure consistent
    handling across holdings, charts, and exports.
    """

    def __init__(self, ledger: FavaLedger) -> None:
        super().__init__(ledger)
        self.names: dict[str, str] = {}
        self.precisions: dict[str, int] = {}
        self.aliases: dict[str, str] = {}
        self._canonical_map: dict[str, str] = {}
        self._case_insensitive_map: dict[str, str] = {}

    def load_file(self) -> None:  # noqa: D102
        self.names = {}
        self.precisions = {}
        self.aliases = {}
        self._canonical_map = {}
        self._case_insensitive_map = {}

        for commodity in self.ledger.all_entries_by_type.Commodity:
            canonical = commodity.currency
            self._canonical_map[canonical] = canonical
            self._case_insensitive_map[canonical.lower()] = canonical

            name = commodity.meta.get("name")
            if name:
                self.names[canonical] = str(name)

            precision = commodity.meta.get("precision")
            if isinstance(precision, (str, int, Decimal)):
                with suppress(ValueError):
                    self.precisions[canonical] = int(precision)

            alias_value = commodity.meta.get("alias")
            if alias_value is not None:
                aliases = (
                    str(alias_value).split(",")
                    if "," in str(alias_value)
                    else [str(alias_value)]
                )
                for alias in aliases:
                    alias = alias.strip()
                    if alias and alias != canonical:
                        self.aliases[alias] = canonical
                        self._canonical_map[alias] = canonical
                        self._case_insensitive_map[alias.lower()] = canonical

    def name(self, commodity: str) -> str:
        """Get the name of a commodity (or the commodity itself if not set)."""
        canonical = self.canonical(commodity)
        return self.names.get(canonical, canonical)

    def canonical(self, commodity: str) -> str:
        """Get the canonical name for a commodity.

        Resolves aliases and normalizes commodity names to their canonical form.
        This ensures consistent commodity identification across holdings, charts,
        and export reports.

        Matching strategy (in order of priority):
        1. Exact match in the canonical map (case-sensitive)
        2. Case-insensitive match against known commodities and aliases
        3. Return the original value if no match found

        Args:
            commodity: The commodity name or alias to canonicalize.

        Returns:
            The canonical commodity name. If the commodity is already canonical
            or has no known alias, returns the original value.
        """
        if commodity in self._canonical_map:
            return self._canonical_map[commodity]
        lower_commodity = commodity.lower()
        if lower_commodity in self._case_insensitive_map:
            return self._case_insensitive_map[lower_commodity]
        return commodity

    def is_alias(self, alias: str, canonical: str) -> bool:
        """Check if a string is an alias for the given canonical commodity.

        Args:
            alias: The alias to check.
            canonical: The canonical commodity name.

        Returns:
            True if the alias resolves to the given canonical name.
        """
        return self.canonical(alias) == canonical

    def precision(self, commodity: str) -> int | None:
        """Get the precision for a commodity (canonicalized).

        Args:
            commodity: The commodity name or alias.

        Returns:
            The precision for the commodity, or None if not set.
        """
        canonical = self.canonical(commodity)
        return self.precisions.get(canonical)
