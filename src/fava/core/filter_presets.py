"""Filter presets storage module.

This module handles saving, loading, updating and deleting filter presets
for accounts, ledger and charts pages.

It implements:
- File-based locking using fcntl (Unix) / msvcrt (Windows) for cross-process safety
- Optimistic concurrency control via two independent mechanisms:
  * **Per-preset version number** (integer, increments on every update) – the
    primary contract exposed to API consumers.  Clients can optionally pass
    the `expected_version` they saw when reading; if the server-side version
    has drifted the write is rejected with HTTP 409.
  * **Storage etag** (SHA-256 of the on-disk bytes) – catches races between
    two writers that are not visible through per-preset versions alone
    (e.g. concurrent deletes of different presets).
- Rich error metadata including conflicting preset details for frontend display
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fava.helpers import FavaAPIError

if TYPE_CHECKING:
    from typing import Any


# --- Platform-specific file locking ------------------------------------------------

if sys.platform == "win32":  # pragma: no cover - Windows specific
    import msvcrt

    def _acquire_file_lock(fp):  # type: ignore[no-untyped-def]
        msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, 1)

    def _release_file_lock(fp):  # type: ignore[no-untyped-def]
        msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _acquire_file_lock(fp):  # type: ignore[no-untyped-def]
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)

    def _release_file_lock(fp):  # type: ignore[no-untyped-def]
        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)


# --- Error classes -----------------------------------------------------------------


class FilterPresetError(FavaAPIError):
    """An error related to filter presets."""

    #: Short machine-readable error code.
    code: str = "filter_preset_error"
    #: Additional structured context for the frontend.
    details: dict[str, Any]

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a dict for the JSON response."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class FilterPresetNotFoundError(FilterPresetError):
    """The requested filter preset was not found."""

    code = "not_found"

    def __init__(self, preset_id: str) -> None:
        super().__init__(
            f"Filter preset '{preset_id}' not found.",
            preset_id=preset_id,
        )


class FilterPresetNameConflictError(FilterPresetError):
    """A filter preset with this name already exists."""

    code = "name_conflict"

    def __init__(self, name: str, existing_preset_id: str | None = None) -> None:
        super().__init__(
            f"A filter preset named '{name}' already exists.",
            conflicting_name=name,
            existing_preset_id=existing_preset_id,
        )


class FilterPresetConcurrentModificationError(FilterPresetError):
    """A preset write was rejected because another session modified it first."""

    code = "concurrent_modification"

    def __init__(
        self,
        *,
        preset_id: str | None = None,
        expected_version: int | None = None,
        actual_version: int | None = None,
        expected_etag: str | None = None,
        actual_etag: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if preset_id is not None:
            details["preset_id"] = preset_id
        if expected_version is not None:
            details["expected_version"] = expected_version
        if actual_version is not None:
            details["actual_version"] = actual_version
        if expected_etag is not None:
            details["expected_etag"] = expected_etag
        if actual_etag is not None:
            details["actual_etag"] = actual_etag

        super().__init__(
            "The filter preset was modified by another session. "
            "Please reload the preset list and try again.",
            **details,
        )


# --- Page type constants -----------------------------------------------------------


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


# --- Data classes ------------------------------------------------------------------


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
    """A named filter preset with an optimistic-lock version counter.

    ``version`` is incremented every time the preset is mutated (rename,
    filter update, etc.).  Clients can pass the last-seen version when
    writing back; if the server's version has advanced the write is
    rejected with :class:`FilterPresetConcurrentModificationError`.
    """

    id: str
    name: str
    page: str
    filters: FilterPresetFilters
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "page": self.page,
            "filters": self.filters.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FilterPreset":
        """Create a FilterPreset from a dictionary.

        Tolerates missing ``version`` fields (defaults to ``1``) so legacy
        JSON files written before the version field was introduced are
        still readable.
        """
        filters_data = data.get("filters", {})
        raw_version = data.get("version", 1)
        try:
            version = int(raw_version)
            if version < 1:
                version = 1
        except (TypeError, ValueError):
            version = 1

        return FilterPreset(
            id=data["id"],
            name=data["name"],
            page=data.get("page", FilterPresetPageType.ALL),
            filters=FilterPresetFilters(
                account=str(filters_data.get("account", "")),
                filter=str(filters_data.get("filter", "")),
                time=str(filters_data.get("time", "")),
                conversion=str(filters_data.get("conversion", "")),
                interval=str(filters_data.get("interval", "")),
            ),
            created_at=float(data.get("created_at", datetime.now().timestamp())),
            updated_at=float(data.get("updated_at", datetime.now().timestamp())),
            version=version,
        )


# --- Helpers -----------------------------------------------------------------------


def _generate_id() -> str:
    """Generate a unique ID for a filter preset."""
    from uuid import uuid4

    return uuid4().hex[:12]


def _compute_etag(raw_bytes: bytes) -> str:
    """Compute an etag (SHA-256 hex digest) for the storage content."""
    return hashlib.sha256(raw_bytes).hexdigest()


def _validate_page_type(page: str) -> str:
    """Validate page type."""
    if page not in FilterPresetPageType.VALID_TYPES:
        raise FilterPresetError(
            f"Invalid page type: '{page}'. "
            f"Valid types are: {', '.join(sorted(FilterPresetPageType.VALID_TYPES))}",
            code="invalid_page_type",
            invalid_page=page,
        )
    return page


def _validate_name(name: str) -> str:
    """Validate preset name."""
    name = name.strip()
    if not name:
        raise FilterPresetError(
            "Filter preset name cannot be empty.",
            code="empty_name",
        )
    if len(name) > 100:
        raise FilterPresetError(
            "Filter preset name is too long (max 100 characters).",
            code="name_too_long",
        )
    return name


# --- Main module -------------------------------------------------------------------


class FilterPresetsModule:
    """Module for managing filter presets stored in a JSON file.

    Presets are stored in a ``.fava-filter-presets.json`` file next to the
    Beancount ledger file.  The on-disk format is::

        {
          "schema_version": 2,
          "presets": [
            {
              "id": "...",
              "name": "...",
              "page": "account" | "balance_sheet" | ... | "all",
              "version": 3,
              "filters": { "account": "...", ... },
              "created_at": 1234.0,
              "updated_at": 1234.0
            },
            ...
          ]
        }

    Thread/cross-process safety:
        * Every **write** operation acquires an exclusive file lock and
          re-reads the file from disk, so concurrent writes from different
          processes or Fava instances are serialised and detected.
        * The etag of the last-known file content is tracked; if another
          client modified the file between our read and write, the write
          is rejected with ``FilterPresetConcurrentModificationError``.
        * Each preset carries a monotonically increasing ``version``
          counter.  Callers of :meth:`update_preset` and
          :meth:`delete_preset` may pass the last-seen version; if the
          server-side version is higher the write is rejected.
    """

    #: Current schema version written to disk.  Bump this whenever the
    #: JSON shape changes in a non-backwards-compatible way.
    SCHEMA_VERSION = 2

    def __init__(self, beancount_file_path: str | Path) -> None:
        """Initialize the filter presets module.

        Args:
            beancount_file_path: Path to the main Beancount file.
        """
        self._ledger_path = Path(beancount_file_path)
        self._storage_path = self._ledger_path.parent / ".fava-filter-presets.json"
        self._presets: dict[str, FilterPreset] = {}
        #: ETag of the storage content last read from disk.
        self._etag: str = ""
        self._load()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def storage_path(self) -> Path:
        """The path to the presets storage file."""
        return self._storage_path

    @property
    def etag(self) -> str:
        """The etag of the last-known storage file content."""
        return self._etag

    # ------------------------------------------------------------------
    # Internal I/O with locking + etag + version tracking
    # ------------------------------------------------------------------

    def _read_storage_locked(self) -> tuple[dict[str, Any], str, bytes]:
        """Read the storage file under an exclusive lock.

        Returns:
            A tuple ``(data, etag, raw_bytes)`` where *data* is the parsed
            JSON document, *etag* is its SHA-256 digest, and *raw_bytes*
            is the raw file content.
        """
        # Ensure the file exists before trying to lock it.
        if not self._storage_path.exists():
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.touch()

        with self._storage_path.open("r+b") as fp:
            _acquire_file_lock(fp)
            try:
                raw_bytes = fp.read()
                if not raw_bytes:
                    data: dict[str, Any] = {
                        "schema_version": self.SCHEMA_VERSION,
                        "presets": [],
                    }
                    raw_bytes = (
                        json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                    ).encode("utf-8")
                    fp.seek(0)
                    fp.write(raw_bytes)
                    fp.truncate()
                    fp.flush()
                    os.fsync(fp.fileno())
                else:
                    try:
                        data = json.loads(raw_bytes.decode("utf-8"))
                    except json.JSONDecodeError:
                        # Start fresh on corruption.
                        data = {
                            "schema_version": self.SCHEMA_VERSION,
                            "presets": [],
                        }
                    if "schema_version" not in data:
                        # Legacy file – transparently upgrade the stored
                        # schema so future writes carry version info.
                        data["schema_version"] = self.SCHEMA_VERSION
            finally:
                _release_file_lock(fp)

        return data, _compute_etag(raw_bytes), raw_bytes

    def _load(self) -> None:
        """Load presets from the storage file (called from __init__)."""
        self._presets = {}
        if not self._storage_path.exists():
            self._etag = ""
            return
        try:
            data, etag, _ = self._read_storage_locked()
        except OSError:
            self._etag = ""
            return

        for preset_data in data.get("presets", []):
            try:
                preset = FilterPreset.from_dict(preset_data)
                self._presets[preset.id] = preset
            except (KeyError, TypeError):
                continue
        self._etag = etag

    def _reload_under_lock(self) -> str:
        """Re-read the file (under lock) and refresh the in-memory state.

        Returns:
            The etag of the freshly-read content.
        """
        data, etag, _ = self._read_storage_locked()
        self._presets = {}
        for preset_data in data.get("presets", []):
            try:
                preset = FilterPreset.from_dict(preset_data)
                self._presets[preset.id] = preset
            except (KeyError, TypeError):
                continue
        self._etag = etag
        return etag

    def _write_storage_locked(
        self,
        presets_dict: dict[str, FilterPreset],
        expected_etag: str,
    ) -> str:
        """Write presets to the storage file under exclusive lock.

        Before writing, the file is re-read and its etag compared with
        *expected_etag*; if it differs a concurrent-modification error is
        raised and the in-memory state is refreshed from disk.

        Returns:
            The new etag after the successful write.
        """
        with self._storage_path.open("r+b") as fp:
            _acquire_file_lock(fp)
            try:
                raw_current = fp.read()
                current_etag = _compute_etag(raw_current) if raw_current else ""
                if expected_etag and current_etag != expected_etag:
                    # Another session changed the file between our reads.
                    # Refresh our in-memory state and bail out.
                    try:
                        data = (
                            json.loads(raw_current.decode("utf-8"))
                            if raw_current
                            else {
                                "schema_version": self.SCHEMA_VERSION,
                                "presets": [],
                            }
                        )
                    except json.JSONDecodeError:
                        data = {
                            "schema_version": self.SCHEMA_VERSION,
                            "presets": [],
                        }
                    self._presets = {}
                    for pd in data.get("presets", []):
                        try:
                            p = FilterPreset.from_dict(pd)
                            self._presets[p.id] = p
                        except (KeyError, TypeError):
                            continue
                    self._etag = current_etag
                    raise FilterPresetConcurrentModificationError(
                        expected_etag=expected_etag,
                        actual_etag=current_etag,
                    )

                data = {
                    "schema_version": self.SCHEMA_VERSION,
                    "presets": [p.to_dict() for p in presets_dict.values()],
                }
                new_raw = (
                    json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8")
                fp.seek(0)
                fp.write(new_raw)
                fp.truncate()
                fp.flush()
                os.fsync(fp.fileno())
                new_etag = _compute_etag(new_raw)
                self._etag = new_etag
                return new_etag
            finally:
                _release_file_lock(fp)

    # ------------------------------------------------------------------
    # Conflict detection helpers
    # ------------------------------------------------------------------

    def _find_preset_by_name(
        self, name: str, exclude_id: str | None = None
    ) -> FilterPreset | None:
        """Find an existing preset by name, optionally excluding an ID."""
        for preset in self._presets.values():
            if preset.id != exclude_id and preset.name == name:
                return preset
        return None

    def _check_name_conflict(
        self, name: str, exclude_id: str | None = None
    ) -> None:
        """Raise ``FilterPresetNameConflictError`` if *name* is taken."""
        existing = self._find_preset_by_name(name, exclude_id)
        if existing is not None:
            raise FilterPresetNameConflictError(name, existing.id)

    @staticmethod
    def _check_version(
        preset: FilterPreset,
        expected_version: int | None,
    ) -> None:
        """Verify the caller-supplied version matches the current preset.

        ``expected_version=None`` means "don't check", which keeps the API
        backwards-compatible with callers that do not yet pass versions.
        """
        if expected_version is None:
            return
        if expected_version != preset.version:
            raise FilterPresetConcurrentModificationError(
                preset_id=preset.id,
                expected_version=expected_version,
                actual_version=preset.version,
            )

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def list_presets(self, page: str | None = None) -> list[dict[str, Any]]:
        """List all filter presets.

        Args:
            page: Optional page type to filter by. If None, returns all presets.
                  Presets with page='all' are always included.

        Returns:
            A list of preset dictionaries, sorted by name.  Each entry
            carries its current ``version`` so clients can pass it back
            when mutating the preset.
        """
        # Re-read from disk under lock so we always see the latest state.
        self._reload_under_lock()

        result: list[FilterPreset] = []
        for preset in self._presets.values():
            if (
                page is None
                or preset.page == FilterPresetPageType.ALL
                or preset.page == page
            ):
                result.append(preset)
        result.sort(key=lambda p: (p.name.lower(), p.created_at))
        return [p.to_dict() for p in result]

    def get_preset(self, preset_id: str) -> dict[str, Any]:
        """Get a specific filter preset by ID.

        Args:
            preset_id: The preset ID.

        Returns:
            The preset dictionary including its current ``version``.

        Raises:
            FilterPresetNotFoundError: If the preset does not exist.
        """
        self._reload_under_lock()
        preset = self._presets.get(preset_id)
        if preset is None:
            raise FilterPresetNotFoundError(preset_id)
        return preset.to_dict()

    # ------------------------------------------------------------------
    # Public write API – all honour per-preset version + file-level etag
    # ------------------------------------------------------------------

    def create_preset(
        self,
        name: str,
        page: str,
        filters: dict[str, str],
    ) -> dict[str, Any]:
        """Create a new filter preset.

        The new preset is created with ``version=1``.

        Args:
            name: The preset name.
            page: The page type.
            filters: The filter parameters dictionary.

        Returns:
            The newly created preset dictionary.

        Raises:
            FilterPresetNameConflictError: If a preset with this name exists.
            FilterPresetConcurrentModificationError: If another session modified
                the storage file concurrently.
            FilterPresetError: If validation fails.
        """
        validated_name = _validate_name(name)
        validated_page = _validate_page_type(page)

        # Re-read under lock to get the latest state + current etag.
        current_etag = self._reload_under_lock()

        # Conflict check on the latest state.
        self._check_name_conflict(validated_name)

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
            name=validated_name,
            page=validated_page,
            filters=preset_filters,
            created_at=now,
            updated_at=now,
            version=1,
        )

        new_presets = dict(self._presets)
        new_presets[preset_id] = preset
        self._write_storage_locked(new_presets, current_etag)
        self._presets = new_presets
        return preset.to_dict()

    def update_preset(
        self,
        preset_id: str,
        *,
        name: str | None = None,
        page: str | None = None,
        filters: dict[str, str] | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing filter preset.

        If *expected_version* is provided and does not match the preset's
        current version on disk, the write is rejected with a 409 so the
        caller can reload and retry.  The preset's version is incremented
        on a successful update.

        Args:
            preset_id: The preset ID to update.
            name: Optional new name.
            page: Optional new page type.
            filters: Optional new filter parameters.
            expected_version: If given, the update is only applied when
                the server-side version exactly matches this value.

        Returns:
            The updated preset dictionary (with the incremented ``version``).

        Raises:
            FilterPresetNotFoundError: If the preset does not exist.
            FilterPresetNameConflictError: If the new name conflicts.
            FilterPresetConcurrentModificationError: If the expected version
                does not match or another session modified the storage.
            FilterPresetError: If validation fails.
        """
        # Re-read under lock for the latest state + etag.
        current_etag = self._reload_under_lock()

        preset = self._presets.get(preset_id)
        if preset is None:
            raise FilterPresetNotFoundError(preset_id)

        # Per-preset optimistic lock check – checked BEFORE any mutation so
        # we do not partially apply a rename and then bail out on version.
        self._check_version(preset, expected_version)

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
                conversion=str(
                    filters.get("conversion", updated_filters.conversion)
                ),
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
            version=preset.version + 1,
        )

        new_presets = dict(self._presets)
        new_presets[preset_id] = updated_preset
        self._write_storage_locked(new_presets, current_etag)
        self._presets = new_presets
        return updated_preset.to_dict()

    def delete_preset(
        self,
        preset_id: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        """Delete a filter preset.

        Args:
            preset_id: The preset ID to delete.
            expected_version: If given, the delete is only performed when
                the server-side version matches.

        Raises:
            FilterPresetNotFoundError: If the preset does not exist.
            FilterPresetConcurrentModificationError: If the expected version
                does not match or another session modified the storage.
        """
        current_etag = self._reload_under_lock()

        preset = self._presets.get(preset_id)
        if preset is None:
            raise FilterPresetNotFoundError(preset_id)

        self._check_version(preset, expected_version)

        new_presets = dict(self._presets)
        del new_presets[preset_id]
        self._write_storage_locked(new_presets, current_etag)
        self._presets = new_presets
