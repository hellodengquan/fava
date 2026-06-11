"""Filter presets storage module.

This module handles saving, loading, updating and deleting filter presets
for accounts, ledger and charts pages.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fava.helpers import FavaAPIError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any


class FilterPresetError(FavaAPIError):
    """An error related to filter presets."""


class FilterPresetNotFoundError(FilterPresetError):
    """The requested filter preset was not found."""

    def __init__(self, preset_id: str) -> None:
        super().__init__(f"Filter preset '{preset_id}' not found.")


class FilterPresetNameConflictError(FilterPresetError):
    """A filter preset with this name already exists."""

    def __init__(self, name: str) -> None:
        super().__init__(f"A filter preset named '{name}' already exists.")


class FilterPresetPageType:
    """Valid page types for filter presets."""

    ACCOUNT = "account"
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    TRIAL_BALANCE = "trial_balance"
    ALL = "all"

    VALID_TYPES = {
        ACCOUNT,
        BALANCE_SHEET,
        INCOME_STATEMENT,
        TRIAL_BALANCE,
        ALL,
    }


@dataclass
class FilterPresetFilters:
    """The filter parameters for a preset."""

    account: str = ""
    filter: str = ""
    time: str = ""
    conversion: str = ""
    interval: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary."""
        return {
            "account": self.account,
            "filter": self.filter,
            "time": self.time,
            "conversion": self.conversion,
            "interval": self.interval,
        }


@dataclass
class FilterPreset:
    """A named filter preset."""

    id: str
    name: str
    page: str
    filters: FilterPresetFilters
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "page": self.page,
            "filters": self.filters.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FilterPreset":
        """Create a FilterPreset from a dictionary."""
        filters_data = data.get("filters", {})
        return FilterPreset(
            id=data["id"],
            name=data["name"],
            page=data.get("page", FilterPresetPageType.ALL),
            filters=FilterPresetFilters(
                account=filters_data.get("account", ""),
                filter=filters_data.get("filter", ""),
                time=filters_data.get("time", ""),
                conversion=filters_data.get("conversion", ""),
                interval=filters_data.get("interval", ""),
            ),
            created_at=data.get("created_at", datetime.now().timestamp()),
            updated_at=data.get("updated_at", datetime.now().timestamp()),
        )


def _generate_id() -> str:
    """Generate a unique ID for a filter preset."""
    from uuid import uuid4

    return uuid4().hex[:12]


def _validate_page_type(page: str) -> str:
    """Validate page type."""
    if page not in FilterPresetPageType.VALID_TYPES:
        raise FilterPresetError(
            f"Invalid page type: '{page}'. "
            f"Valid types are: {', '.join(sorted(FilterPresetPageType.VALID_TYPES))}"
        )
    return page


def _validate_name(name: str) -> str:
    """Validate preset name."""
    name = name.strip()
    if not name:
        raise FilterPresetError("Filter preset name cannot be empty.")
    if len(name) > 100:
        raise FilterPresetError("Filter preset name is too long (max 100 characters).")
    return name


class FilterPresetsModule:
    """Module for managing filter presets stored in a JSON file.

    Presets are stored in a `.fava-filter-presets.json` file next to the
    Beancount ledger file.
    """

    def __init__(self, beancount_file_path: str | Path) -> None:
        """Initialize the filter presets module.

        Args:
            beancount_file_path: Path to the main Beancount file.
        """
        self._ledger_path = Path(beancount_file_path)
        self._storage_path = self._ledger_path.parent / ".fava-filter-presets.json"
        self._presets: dict[str, FilterPreset] = {}
        self._load()

    @property
    def storage_path(self) -> Path:
        """The path to the presets storage file."""
        return self._storage_path

    def _load(self) -> None:
        """Load presets from the storage file."""
        self._presets = {}
        if not self._storage_path.exists():
            return
        try:
            with self._storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for preset_data in data.get("presets", []):
                try:
                    preset = FilterPreset.from_dict(preset_data)
                    self._presets[preset.id] = preset
                except (KeyError, TypeError) as e:
                    # Skip invalid preset entries
                    continue
        except (json.JSONDecodeError, OSError):
            # If file is corrupted, start with empty presets
            self._presets = {}

    def _save(self) -> None:
        """Save presets to the storage file."""
        data = {
            "presets": [preset.to_dict() for preset in self._presets.values()],
            "version": 1,
        }
        try:
            with self._storage_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            raise FilterPresetError(
                f"Failed to save filter presets: {e!s}"
            ) from e

    def _check_name_conflict(
        self, name: str, exclude_id: str | None = None
    ) -> None:
        """Check if a preset name already exists.

        Args:
            name: The name to check.
            exclude_id: Optional preset ID to exclude from the check (for renaming).

        Raises:
            FilterPresetNameConflictError: If a preset with the name exists.
        """
        for preset in self._presets.values():
            if preset.id != exclude_id and preset.name == name:
                raise FilterPresetNameConflictError(name)

    def list_presets(self, page: str | None = None) -> list[dict[str, Any]]:
        """List all filter presets.

        Args:
            page: Optional page type to filter by. If None, returns all presets.
                  Presets with page='all' are always included.

        Returns:
            A list of preset dictionaries, sorted by name.
        """
        result: list[FilterPreset] = []
        for preset in self._presets.values():
            if page is None or preset.page == FilterPresetPageType.ALL or preset.page == page:
                result.append(preset)
        result.sort(key=lambda p: (p.name.lower(), p.created_at))
        return [p.to_dict() for p in result]

    def get_preset(self, preset_id: str) -> dict[str, Any]:
        """Get a specific filter preset by ID.

        Args:
            preset_id: The preset ID.

        Returns:
            The preset dictionary.

        Raises:
            FilterPresetNotFoundError: If the preset does not exist.
        """
        preset = self._presets.get(preset_id)
        if preset is None:
            raise FilterPresetNotFoundError(preset_id)
        return preset.to_dict()

    def create_preset(
        self,
        name: str,
        page: str,
        filters: dict[str, str],
    ) -> dict[str, Any]:
        """Create a new filter preset.

        Args:
            name: The preset name.
            page: The page type.
            filters: The filter parameters dictionary.

        Returns:
            The newly created preset dictionary.

        Raises:
            FilterPresetNameConflictError: If a preset with this name exists.
            FilterPresetError: If validation fails.
        """
        name = _validate_name(name)
        page = _validate_page_type(page)
        self._check_name_conflict(name)

        preset_filters = FilterPresetFilters(
            account=str(filters.get("account", "")),
            filter=str(filters.get("filter", "")),
            time=str(filters.get("time", "")),
            conversion=str(filters.get("conversion", "")),
            interval=str(filters.get("interval", "")),
        )

        preset_id = _generate_id()
        now = datetime.now().timestamp()
        preset = FilterPreset(
            id=preset_id,
            name=name,
            page=page,
            filters=preset_filters,
            created_at=now,
            updated_at=now,
        )

        self._presets[preset_id] = preset
        self._save()
        return preset.to_dict()

    def update_preset(
        self,
        preset_id: str,
        *,
        name: str | None = None,
        page: str | None = None,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing filter preset.

        Args:
            preset_id: The preset ID to update.
            name: Optional new name.
            page: Optional new page type.
            filters: Optional new filter parameters.

        Returns:
            The updated preset dictionary.

        Raises:
            FilterPresetNotFoundError: If the preset does not exist.
            FilterPresetNameConflictError: If the new name conflicts.
            FilterPresetError: If validation fails.
        """
        preset = self._presets.get(preset_id)
        if preset is None:
            raise FilterPresetNotFoundError(preset_id)

        updated_name = preset.name
        updated_page = preset.page
        updated_filters = preset.filters

        if name is not None:
            updated_name = _validate_name(name)
            self._check_name_conflict(updated_name, exclude_id=preset_id)

        if page is not None:
            updated_page = _validate_page_type(page)

        if filters is not None:
            updated_filters = FilterPresetFilters(
                account=str(filters.get("account", updated_filters.account)),
                filter=str(filters.get("filter", updated_filters.filter)),
                time=str(filters.get("time", updated_filters.time)),
                conversion=str(filters.get("conversion", updated_filters.conversion)),
                interval=str(filters.get("interval", updated_filters.interval)),
            )

        now = datetime.now().timestamp()
        updated_preset = FilterPreset(
            id=preset.id,
            name=updated_name,
            page=updated_page,
            filters=updated_filters,
            created_at=preset.created_at,
            updated_at=now,
        )

        self._presets[preset_id] = updated_preset
        self._save()
        return updated_preset.to_dict()

    def delete_preset(self, preset_id: str) -> None:
        """Delete a filter preset.

        Args:
            preset_id: The preset ID to delete.

        Raises:
            FilterPresetNotFoundError: If the preset does not exist.
        """
        if preset_id not in self._presets:
            raise FilterPresetNotFoundError(preset_id)

        del self._presets[preset_id]
        self._save()
