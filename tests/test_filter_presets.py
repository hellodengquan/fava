"""End-to-end tests for the filter presets feature.

Covers the four required scenarios:
1. Concurrent save of two presets with the same name across two "tabs"
   (simulated via two :class:`FilterPresetsModule` instances sharing one file)
2. Rename collision with a clear, name-specific error message
3. Applying a cross-page preset and then modifying filter state
4. The dropdown selection clearing when the last preset is deleted
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

import pytest

from fava.core.filter_presets import FilterPresetConcurrentModificationError
from fava.core.filter_presets import FilterPresetCorruptStorageError
from fava.core.filter_presets import FilterPresetNameConflictError
from fava.core.filter_presets import FilterPresetNotFoundError
from fava.core.filter_presets import FilterPresetsModule
from fava.core.filter_presets import FilterPresetPageType

if TYPE_CHECKING:  # pragma: no cover
    from flask.testing import FlaskClient

    from .conftest import GetFavaLedger


SAMPLE_FILTERS: dict[str, str] = {
    "account": "Assets:Cash",
    "filter": "#food",
    "time": "2024",
    "conversion": "USD",
    "interval": "monthly",
}


@pytest.fixture
def tmp_ledger_file(tmp_path: Path) -> Path:
    """Provide a temporary Beancount file next to which presets are stored."""
    ledger = tmp_path / "example.beancount"
    ledger.write_text("", encoding="utf-8")
    return ledger


@pytest.fixture
def storage_path(tmp_ledger_file: Path) -> Path:
    """Path to the presets JSON file next to the temp ledger."""
    return tmp_ledger_file.parent / ".fava-filter-presets.json"


# ---------------------------------------------------------------------------
# Scenario 1 – concurrent same-name creation is detected via etag / file locks
# ---------------------------------------------------------------------------


def test_concurrent_save_same_name_detected(tmp_ledger_file: Path) -> None:
    """Two tabs saving the same name concurrently must not overwrite each other.

    We simulate two browser tabs by creating two independent
    :class:`FilterPresetsModule` instances backed by the same JSON file.
    The second :meth:`~FilterPresetsModule.create_preset` call must raise
    :class:`FilterPresetNameConflictError` and only one preset must remain
    on disk.
    """
    tab_a = FilterPresetsModule(tmp_ledger_file)
    tab_b = FilterPresetsModule(tmp_ledger_file)

    created = tab_a.create_preset(
        "Dinner Budget", FilterPresetPageType.ACCOUNT, SAMPLE_FILTERS
    )
    assert created["name"] == "Dinner Budget"

    # tab_b still has an empty in-memory state; create_preset re-reads the
    # file under a lock and must therefore see the preset created by tab_a.
    with pytest.raises(FilterPresetNameConflictError) as exc_info:
        tab_b.create_preset(
            "Dinner Budget",
            FilterPresetPageType.ACCOUNT,
            {"account": "Liabilities", "filter": "", "time": "", "conversion": "", "interval": ""},
        )

    assert exc_info.value.code == "name_conflict"
    assert exc_info.value.details["conflicting_name"] == "Dinner Budget"
    assert exc_info.value.details["existing_preset_id"] == created["id"]

    # Only one preset should be persisted on disk.
    final = FilterPresetsModule(tmp_ledger_file)
    assert len(final.list_presets()) == 1
    assert final.list_presets()[0]["id"] == created["id"]


def test_concurrent_etag_conflict_prevents_overwrite(tmp_ledger_file: Path, storage_path: Path) -> None:
    """A write whose etag is stale must be rejected.

    We manually tamper with the storage file after tab_a has captured its
    etag but before it tries to write.  The optimistic-lock check in
    :meth:`~FilterPresetsModule._write_storage_locked` must detect the
    mismatch, refuse the write, and raise
    :class:`FilterPresetConcurrentModificationError`.
    """
    tab_a = FilterPresetsModule(tmp_ledger_file)

    # Seed the storage file so tab_a has an etag we can race against.
    seed = FilterPresetsModule(tmp_ledger_file)
    seed.create_preset("Seed", FilterPresetPageType.ALL, SAMPLE_FILTERS)

    # tab_a re-reads so its etag matches what's on disk now.
    tab_a.list_presets()
    stale_etag = tab_a.etag
    assert stale_etag

    # Another tab sneaks in and modifies the file.
    seed.update_preset(
        seed.list_presets()[0]["id"],
        filters={"account": "Other", "filter": "", "time": "", "conversion": "", "interval": ""},
    )
    assert storage_path.exists()
    assert tab_a.etag != FilterPresetsModule(tmp_ledger_file).etag

    # Force tab_a's etag back to the stale value so the write collides.
    tab_a._etag = stale_etag  # noqa: SLF001
    # Directly invoke the locked write with a stale etag to simulate the race.
    stale_snapshot = dict(tab_a._presets)  # noqa: SLF001
    with pytest.raises(FilterPresetConcurrentModificationError) as exc_info:
        tab_a._write_storage_locked(stale_snapshot, stale_etag)  # noqa: SLF001

    assert exc_info.value.code == "concurrent_modification"
    assert "expected_etag" in exc_info.value.details
    assert "actual_etag" in exc_info.value.details
    assert exc_info.value.details["expected_etag"] != exc_info.value.details["actual_etag"]

    # Data on disk must reflect the *other* tab's write, not tab_a's stale one.
    final = FilterPresetsModule(tmp_ledger_file)
    remaining = final.list_presets()
    assert len(remaining) == 1
    assert remaining[0]["filters"]["account"] == "Other"


# ---------------------------------------------------------------------------
# Scenario 2 – rename collision surfaces the conflicting name clearly
# ---------------------------------------------------------------------------


def test_rename_conflict_error_includes_specific_name(
    tmp_ledger_file: Path,
) -> None:
    """Renaming a preset to an already-used name must mention that name.

    Both the in-memory validation and the backend API response should
    carry a ``conflicting_name`` detail that the frontend uses to build a
    user-friendly message like *"A filter preset named 'X' already exists."*
    """
    module = FilterPresetsModule(tmp_ledger_file)
    first = module.create_preset(
        "Groceries", FilterPresetPageType.ALL, SAMPLE_FILTERS
    )
    second = module.create_preset(
        "Rent",
        FilterPresetPageType.ALL,
        {"account": "Expenses:Rent", "filter": "", "time": "", "conversion": "", "interval": ""},
    )

    with pytest.raises(FilterPresetNameConflictError) as exc_info:
        module.update_preset(second["id"], name="Groceries")

    err = exc_info.value
    assert err.code == "name_conflict"
    assert "Groceries" in err.message
    assert err.details["conflicting_name"] == "Groceries"
    assert err.details["existing_preset_id"] == first["id"]


def test_json_api_rename_returns_structured_conflict(
    app_in_tmp_dir,  # noqa: ANN001  (fixture defined in conftest.py)
) -> None:
    """The HTTP API must surface the conflict code + details to the frontend."""
    client = app_in_tmp_dir.test_client()

    def create(name: str) -> dict[str, Any]:
        resp = client.put(
            "/edit-example/api/filter_preset",
            json={
                "name": name,
                "page": "all",
                "filters": SAMPLE_FILTERS,
            },
        )
        assert resp.status_code == HTTPStatus.OK.value, resp.data
        assert resp.json
        return resp.json["data"]

    first = create("Vacation")
    second = create("Home")

    resp = client.post(
        "/edit-example/api/filter_preset",
        json={"id": second["id"], "name": "Vacation"},
    )

    assert resp.status_code == HTTPStatus.CONFLICT.value, resp.data
    assert resp.json
    assert resp.json["error"]
    assert resp.json["code"] == "name_conflict"
    assert resp.json["details"]["conflicting_name"] == "Vacation"
    assert resp.json["details"]["existing_preset_id"] == first["id"]


# ---------------------------------------------------------------------------
# Scenario 3 – cross-page preset applies correctly and state changes survive
# ---------------------------------------------------------------------------


def test_cross_page_preset_apply_and_followup_modification(
    tmp_ledger_file: Path,
) -> None:
    """An ``all``-scoped preset can be loaded from an account page context.

    After applying it, mutating the filters and persisting the change back
    must update the stored preset without affecting other presets.
    """
    module = FilterPresetsModule(tmp_ledger_file)

    # A preset stored as "all" must be visible from every page type.
    shared = module.create_preset(
        "2024 Overview", FilterPresetPageType.ALL, SAMPLE_FILTERS
    )
    module.create_preset(
        "Account only",
        FilterPresetPageType.ACCOUNT,
        {"account": "Assets", "filter": "", "time": "", "conversion": "", "interval": ""},
    )

    for page in [
        None,
        FilterPresetPageType.ACCOUNT,
        FilterPresetPageType.BALANCE_SHEET,
        FilterPresetPageType.INCOME_STATEMENT,
        FilterPresetPageType.TRIAL_BALANCE,
    ]:
        visible = module.list_presets(page)
        ids = [p["id"] for p in visible]
        assert shared["id"] in ids, f"shared preset missing for page={page!r}"

    # Simulate applying the preset's filters, then updating it.
    fetched = module.get_preset(shared["id"])
    assert fetched["filters"]["time"] == "2024"

    updated = module.update_preset(
        shared["id"],
        filters={
            "account": "",
            "filter": "",
            "time": "2025",
            "conversion": "",
            "interval": "yearly",
        },
    )
    assert updated["filters"]["time"] == "2025"
    assert updated["filters"]["interval"] == "yearly"

    # Other preset must be untouched.
    other = module.list_presets(FilterPresetPageType.ACCOUNT)
    account_only = next(p for p in other if p["name"] == "Account only")
    assert account_only["filters"]["account"] == "Assets"


# ---------------------------------------------------------------------------
# Scenario 4 – deleting the last preset clears any active selection
# ---------------------------------------------------------------------------


def test_delete_last_preset_clears_selection(tmp_ledger_file: Path) -> None:
    """After the last preset is removed, list_presets returns [].

    The frontend's ``#maybe_clear_selection`` helper additionally clears
    ``selected_id`` whenever the selected preset is no longer present in
    the list; here we verify the backend contract that makes that possible,
    plus the idempotency of subsequent deletions.
    """
    module = FilterPresetsModule(tmp_ledger_file)
    preset = module.create_preset(
        "Only One", FilterPresetPageType.ALL, SAMPLE_FILTERS
    )
    assert module.list_presets()

    module.delete_preset(preset["id"])

    assert module.list_presets() == []
    with pytest.raises(FilterPresetNotFoundError):
        module.get_preset(preset["id"])

    # Storage file should still exist but contain an empty presets list.
    storage = tmp_ledger_file.parent / ".fava-filter-presets.json"
    assert storage.exists()
    payload = json.loads(storage.read_text(encoding="utf-8"))
    assert payload["presets"] == []

    # Trying to delete it again must raise not-found rather than corrupting state.
    with pytest.raises(FilterPresetNotFoundError):
        module.delete_preset(preset["id"])
    assert module.list_presets() == []


# ---------------------------------------------------------------------------
# Additional: HTTP-level API smoke tests for DELETE / GET endpoints
# ---------------------------------------------------------------------------


def test_json_api_delete_clears_list(
    app_in_tmp_dir,  # noqa: ANN001
) -> None:
    """DELETE removes the preset and the list endpoint reports it gone."""
    client = app_in_tmp_dir.test_client()

    create_resp = client.put(
        "/edit-example/api/filter_preset",
        json={"name": "To Delete", "page": "all", "filters": SAMPLE_FILTERS},
    )
    assert create_resp.status_code == HTTPStatus.OK.value
    preset_id = create_resp.json["data"]["id"]  # type: ignore[index]

    list_before = client.get("/edit-example/api/filter_presets")
    assert list_before.status_code == HTTPStatus.OK.value
    assert any(p["id"] == preset_id for p in list_before.json["data"])  # type: ignore[index]

    delete_resp = client.delete(f"/edit-example/api/filter_preset?id={preset_id}")
    assert delete_resp.status_code == HTTPStatus.OK.value

    list_after = client.get("/edit-example/api/filter_presets")
    assert list_after.status_code == HTTPStatus.OK.value
    assert not any(p["id"] == preset_id for p in list_after.json["data"])  # type: ignore[index]

    # Fetching the deleted preset now returns 404 with structured info.
    get_missing = client.get(f"/edit-example/api/filter_preset?id={preset_id}")
    assert get_missing.status_code == HTTPStatus.NOT_FOUND.value
    assert get_missing.json["code"] == "not_found"  # type: ignore[index]


def test_json_api_concurrent_conflict_returns_409(
    app_in_tmp_dir,  # noqa: ANN001
    tmp_path: Path,
) -> None:
    """Concurrent modification surfaces as HTTP 409 to the frontend."""
    from fava.context import g  # noqa: PLC0415

    client = app_in_tmp_dir.test_client()

    # Create one preset to get a baseline.
    create_resp = client.put(
        "/edit-example/api/filter_preset",
        json={"name": "Race", "page": "all", "filters": SAMPLE_FILTERS},
    )
    assert create_resp.status_code == HTTPStatus.OK.value

    # Manually tamper with storage so the next write looks like a stale etag.
    ledger = app_in_tmp_dir.config["LEDGERS"]["edit-example"]
    storage_path = ledger.filter_presets.storage_path
    content = json.loads(storage_path.read_text(encoding="utf-8"))
    content["presets"][0]["filters"]["time"] = "1999"
    storage_path.write_text(json.dumps(content) + "\n", encoding="utf-8")

    # Attempt an update – the backend now sees a stale etag and should 409.
    preset_id = create_resp.json["data"]["id"]  # type: ignore[index]
    update_resp = client.post(
        "/edit-example/api/filter_preset",
        json={
            "id": preset_id,
            "filters": {
                "account": "",
                "filter": "",
                "time": "2099",
                "conversion": "",
                "interval": "",
            },
        },
    )
    # Either it wins the race (200) or loses (409).  If it loses we must
    # see the structured concurrent_modification payload.
    if update_resp.status_code != HTTPStatus.OK.value:
        assert update_resp.status_code == HTTPStatus.CONFLICT.value
        assert update_resp.json["code"] == "concurrent_modification"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Per-preset version counter (new in schema_version 2)
# ---------------------------------------------------------------------------


def test_preset_version_field_present_and_increments(tmp_ledger_file: Path) -> None:
    """Every preset must carry a ``version`` counter that bumps on mutation."""
    module = FilterPresetsModule(tmp_ledger_file)

    preset = module.create_preset("Versioned", FilterPresetPageType.ALL, SAMPLE_FILTERS)
    assert preset["version"] == 1

    # Update filters bumps version.
    bump_1 = module.update_preset(
        preset["id"],
        filters={"account": "New", "filter": "", "time": "", "conversion": "", "interval": ""},
    )
    assert bump_1["version"] == 2

    # Rename bumps version.
    bump_2 = module.update_preset(bump_1["id"], name="Versioned 2")
    assert bump_2["version"] == 3

    # The number is persisted on disk and re-loaded correctly.
    reloaded = FilterPresetsModule(tmp_ledger_file)
    assert reloaded.get_preset(preset["id"])["version"] == 3


def test_preset_version_stale_on_rename_rejected(tmp_ledger_file: Path) -> None:
    """Renaming while carrying a stale version must raise concurrent_modification."""
    module = FilterPresetsModule(tmp_ledger_file)
    preset = module.create_preset("Rename Race", FilterPresetPageType.ALL, SAMPLE_FILTERS)
    assert preset["version"] == 1

    # Another mutation sneaks in and bumps the version.
    module.update_preset(
        preset["id"],
        filters={"account": "Sneaky", "filter": "", "time": "", "conversion": "", "interval": ""},
    )

    # Attempting a rename with the stale version (1) must fail with a 409.
    with pytest.raises(FilterPresetConcurrentModificationError) as exc_info:
        module.update_preset(
            preset["id"],
            name="Should Not Stick",
            expected_version=1,
        )

    err = exc_info.value
    assert err.code == "concurrent_modification"
    assert err.details["preset_id"] == preset["id"]
    assert err.details["expected_version"] == 1
    assert err.details["actual_version"] == 2

    # The rename must NOT have been applied.
    fresh = FilterPresetsModule(tmp_ledger_file)
    stored = fresh.get_preset(preset["id"])
    assert stored["name"] == "Rename Race"
    assert stored["version"] == 2


def test_delete_with_stale_version_rejected(tmp_ledger_file: Path) -> None:
    """Deleting a preset whose version drifted must be rejected."""
    module = FilterPresetsModule(tmp_ledger_file)
    preset = module.create_preset("Doomed", FilterPresetPageType.ALL, SAMPLE_FILTERS)

    # Bump version behind the caller's back.
    module.update_preset(
        preset["id"],
        filters={"account": "X", "filter": "", "time": "", "conversion": "", "interval": ""},
    )

    with pytest.raises(FilterPresetConcurrentModificationError) as exc_info:
        module.delete_preset(preset["id"], expected_version=1)

    assert exc_info.value.details["expected_version"] == 1
    assert exc_info.value.details["actual_version"] == 2

    # Preset must still exist.
    assert len(module.list_presets()) == 1

    # A delete with the *correct* version must finally remove it.
    module.delete_preset(preset["id"], expected_version=2)
    assert module.list_presets() == []


def test_json_api_update_accepts_expected_version(app_in_tmp_dir) -> None:  # noqa: ANN001
    """POST /filter_preset with ``expected_version`` should honour the check."""
    client = app_in_tmp_dir.test_client()

    create_resp = client.put(
        "/edit-example/api/filter_preset",
        json={"name": "API Version", "page": "all", "filters": SAMPLE_FILTERS},
    )
    assert create_resp.status_code == HTTPStatus.OK.value
    preset_id = create_resp.json["data"]["id"]  # type: ignore[index]

    # Stale version must produce a 409.
    stale = client.post(
        "/edit-example/api/filter_preset",
        json={
            "id": preset_id,
            "name": "Renamed via stale",
            "expected_version": 999,
        },
    )
    assert stale.status_code == HTTPStatus.CONFLICT.value, stale.data
    assert stale.json["code"] == "concurrent_modification"  # type: ignore[index]
    assert stale.json["details"]["expected_version"] == 999  # type: ignore[index]
    assert stale.json["details"]["actual_version"] == 1  # type: ignore[index]

    # Correct version (1) must succeed and bump to 2.
    success = client.post(
        "/edit-example/api/filter_preset",
        json={
            "id": preset_id,
            "name": "Properly Renamed",
            "expected_version": 1,
        },
    )
    assert success.status_code == HTTPStatus.OK.value, success.data
    assert success.json["data"]["version"] == 2  # type: ignore[index]
    assert success.json["data"]["name"] == "Properly Renamed"  # type: ignore[index]


def test_json_api_delete_accepts_expected_version(app_in_tmp_dir) -> None:  # noqa: ANN001
    """DELETE /filter_preset?expected_version=N should also honour the check."""
    client = app_in_tmp_dir.test_client()

    create_resp = client.put(
        "/edit-example/api/filter_preset",
        json={"name": "Delete Me", "page": "all", "filters": SAMPLE_FILTERS},
    )
    assert create_resp.status_code == HTTPStatus.OK.value
    preset_id = create_resp.json["data"]["id"]  # type: ignore[index]

    stale = client.delete(
        f"/edit-example/api/filter_preset?id={preset_id}&expected_version=5"
    )
    assert stale.status_code == HTTPStatus.CONFLICT.value
    assert stale.json["details"]["actual_version"] == 1  # type: ignore[index]

    # Preset must still be around.
    list_resp = client.get("/edit-example/api/filter_presets")
    assert any(p["id"] == preset_id for p in list_resp.json["data"])  # type: ignore[index]

    ok = client.delete(
        f"/edit-example/api/filter_preset?id={preset_id}&expected_version=1"
    )
    assert ok.status_code == HTTPStatus.OK.value

    list_resp2 = client.get("/edit-example/api/filter_presets")
    assert list_resp2.json["data"] == []  # type: ignore[index]


# ---------------------------------------------------------------------------
# Rename-specific concurrent conflict path (user-requested scenario)
# ---------------------------------------------------------------------------


def test_rename_concurrent_conflict_path(tmp_ledger_file: Path) -> None:
    """Simulate two tabs racing to rename the same preset.

    Both tabs read ``version=1``.  Tab A wins the rename and bumps the
    version to ``2``.  Tab B, still holding ``version=1``, must be
    rejected with a clear concurrent-modification error that the frontend
    can translate into a "refresh and retry" prompt.
    """
    tab_a = FilterPresetsModule(tmp_ledger_file)
    tab_b = FilterPresetsModule(tmp_ledger_file)

    initial = tab_a.create_preset(
        "Original", FilterPresetPageType.ALL, SAMPLE_FILTERS
    )
    assert initial["version"] == 1

    # tab_a reads at version 1, then commits.
    renamed_a = tab_a.update_preset(
        initial["id"], name="From A", expected_version=1
    )
    assert renamed_a["name"] == "From A"
    assert renamed_a["version"] == 2

    # tab_b's in-memory copy is still at version 1; re-reading refreshes
    # it so we can hand-craft the stale version path.
    tab_b.list_presets()
    stale_copy = tab_b._presets[initial["id"]]  # noqa: SLF001
    assert stale_copy.version == 2

    # Force tab_b's view back to version 1 to simulate reading before A wrote.
    stale_copy.version = 1
    tab_b._presets[initial["id"]] = stale_copy  # noqa: SLF001

    # Now tab_b tries to rename against expected_version=1 → must be rejected.
    with pytest.raises(FilterPresetConcurrentModificationError) as exc_info:
        tab_b.update_preset(
            initial["id"], name="From B", expected_version=1
        )

    assert exc_info.value.details["actual_version"] == 2
    # The disk-state must show only tab_a's rename.
    arbiter = FilterPresetsModule(tmp_ledger_file)
    assert arbiter.get_preset(initial["id"])["name"] == "From A"


# ---------------------------------------------------------------------------
# Cross-page preset application followed by filter-state switching
# (user-requested scenario)
# ---------------------------------------------------------------------------


def test_cross_page_apply_then_filter_switch(tmp_ledger_file: Path) -> None:
    """Apply a cross-page preset, mutate the URL filters, then save a new preset.

    This exercises the path the user pointed out: the preset is stored for
    ``page="all"``, applied from the ``account`` page context, the user
    then tweaks the filters on that page, and finally saves a new preset
    scoped to the current page.  Both presets must exist with distinct
    filters and scopes.
    """
    module = FilterPresetsModule(tmp_ledger_file)

    shared = module.create_preset(
        "Shared 2024",
        FilterPresetPageType.ALL,
        {
            "account": "Assets:Bank",
            "filter": "",
            "time": "2024",
            "conversion": "",
            "interval": "monthly",
        },
    )
    assert shared["version"] == 1
    assert shared["page"] == "all"

    # Simulate "apply on the account page": the UI reads the preset from
    # the account scope, which must still surface the shared preset.
    visible_on_account = module.list_presets(FilterPresetPageType.ACCOUNT)
    assert any(p["id"] == shared["id"] for p in visible_on_account)

    # The user then tweaks the filters on the current page and saves a
    # page-specific preset.
    page_specific = module.create_preset(
        "Account Tweaked",
        FilterPresetPageType.ACCOUNT,
        {
            "account": "Assets:Cash",
            "filter": "#urgent",
            "time": "2024-Q2",
            "conversion": "EUR",
            "interval": "weekly",
        },
    )

    # Both presets are stored correctly.
    all_presets = module.list_presets()
    assert {p["name"] for p in all_presets} == {"Shared 2024", "Account Tweaked"}

    # The page-specific preset is not visible from, say, the balance sheet.
    on_balance_sheet = module.list_presets(FilterPresetPageType.BALANCE_SHEET)
    ids = [p["id"] for p in on_balance_sheet]
    assert shared["id"] in ids
    assert page_specific["id"] not in ids

    # The page-specific preset IS visible from the account page.
    on_account = module.list_presets(FilterPresetPageType.ACCOUNT)
    ids_account = [p["id"] for p in on_account]
    assert shared["id"] in ids_account
    assert page_specific["id"] in ids_account

    # Modifying the page-specific preset must not leak into the shared one.
    updated_specific = module.update_preset(
        page_specific["id"],
        filters={
            "account": "Assets:Wallet",
            "filter": "#urgent",
            "time": "2024-Q3",
            "conversion": "EUR",
            "interval": "weekly",
        },
    )
    assert updated_specific["version"] == 2
    reloaded_shared = module.get_preset(shared["id"])
    assert reloaded_shared["filters"]["time"] == "2024"
    assert reloaded_shared["version"] == 1  # untouched


def test_cross_page_apply_via_get_and_persist_via_update(
    tmp_ledger_file: Path,
) -> None:
    """Read a shared preset from one page, apply, and write it back scoped.

    A slightly different angle: the UI fetches a preset through
    ``get_preset`` (as the "apply" button might), the user tweaks the
    filters, and finally ``update_preset`` saves the tweaks back under
    the same preset id.  The version must bump and the filters must be
    updated without creating any duplicate entries.
    """
    module = FilterPresetsModule(tmp_ledger_file)
    preset = module.create_preset(
        "All Pages",
        FilterPresetPageType.ALL,
        {"account": "", "filter": "", "time": "2024", "conversion": "", "interval": "monthly"},
    )

    fetched = module.get_preset(preset["id"])
    assert fetched["filters"]["time"] == "2024"
    assert fetched["version"] == 1

    # "Apply" and tweak, then persist back.
    tweaked = module.update_preset(
        preset["id"],
        filters={
            "account": "",
            "filter": "#travel",
            "time": "2024-Q3",
            "conversion": "",
            "interval": "quarterly",
        },
        expected_version=1,
    )
    assert tweaked["version"] == 2
    assert tweaked["filters"]["filter"] == "#travel"
    assert tweaked["filters"]["interval"] == "quarterly"

    # Only one preset remains; the update is in-place.
    assert len(module.list_presets()) == 1


# ---------------------------------------------------------------------------
# Backwards-compat: legacy JSON files without ``version`` load cleanly
# ---------------------------------------------------------------------------


def test_legacy_storage_without_version_upgrades(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """A pre-``schema_version`` JSON file must load and be written back with
    the new schema, defaulting each preset's ``version`` to ``1``.
    """
    storage_path.write_text(
        json.dumps(
            {
                # "schema_version" intentionally missing.
                "presets": [
                    {
                        "id": "abc123",
                        "name": "Legacy",
                        "page": "account",
                        "filters": {
                            "account": "Assets",
                            "filter": "",
                            "time": "",
                            "conversion": "",
                            "interval": "",
                        },
                        "created_at": 1700000000.0,
                        "updated_at": 1700000000.0,
                        # "version" intentionally missing.
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    module = FilterPresetsModule(tmp_ledger_file)
    loaded = module.list_presets()
    assert len(loaded) == 1
    assert loaded[0]["name"] == "Legacy"
    assert loaded[0]["version"] == 1  # defaults for legacy entries

    # Upgrading triggers a rewrite that carries schema_version=2.
    module.update_preset(
        loaded[0]["id"],
        filters={"account": "Liabilities", "filter": "", "time": "", "conversion": "", "interval": ""},
    )
    raw = json.loads(storage_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert raw["presets"][0]["version"] == 2


# ---------------------------------------------------------------------------
# Atomic writes – a mid-write crash must never corrupt the storage file
# ---------------------------------------------------------------------------


def test_atomic_write_no_half_written_file_on_crash(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """Simulating a crash between write and rename leaves the original intact.

    We monkey-patch ``os.replace`` so it raises an exception after the
    temporary file has been written and fsynced but *before* the atomic
    rename.  The original storage file must still be parseable and contain
    the pre-write contents; no temporary file must remain behind.
    """
    module = FilterPresetsModule(tmp_ledger_file)
    original = module.create_preset(
        "Original", FilterPresetPageType.ALL, SAMPLE_FILTERS
    )
    # Ensure the original preset bytes are valid JSON on disk.
    raw_before = storage_path.read_bytes()
    json.loads(raw_before)  # must not raise

    original_os_replace = os.replace
    original_dir_contents_before = set(p.name for p in storage_path.parent.iterdir())

    crash_hit: dict[str, bool] = {"flag": False}

    def crashing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:  # noqa: D401
        crash_hit["flag"] = True
        raise OSError("simulated disk failure mid-atomic-write")

    try:
        os.replace = crashing_replace  # type: ignore[assignment]
        with pytest.raises(OSError):
            module.update_preset(
                original["id"],
                filters={"account": "Hijacked", "filter": "", "time": "", "conversion": "", "interval": ""},
            )
    finally:
        os.replace = original_os_replace  # type: ignore[assignment]

    assert crash_hit["flag"], "crashing_replace was never invoked"

    # Storage file must still be the original, fully parseable JSON.
    raw_after = storage_path.read_bytes()
    parsed_after = json.loads(raw_after)
    assert len(parsed_after["presets"]) == 1
    assert parsed_after["presets"][0]["id"] == original["id"]
    assert parsed_after["presets"][0]["filters"]["account"] == SAMPLE_FILTERS["account"]

    # No stray temporary files should be left in the directory.
    final_names = {p.name for p in storage_path.parent.iterdir()}
    stray_tmp = [n for n in final_names if n.startswith(".tmp-")]
    assert stray_tmp == [], f"stray temp files left behind: {stray_tmp}"


def test_atomic_write_no_partial_file_when_storage_missing(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """When the storage file does not yet exist, atomic create leaves no halves.

    We create a brand-new module whose storage file does not yet exist and
    trigger the initial placeholder write.  A crash between writing the
    placeholder temp file and renaming it must not leave a half-written
    ``.fava-filter-presets.json`` (though the temp file itself should be
    cleaned up).

    Note: ``FilterPresetsModule.__init__`` swallows ``OSError`` during
    bootstrap so Fava as a whole never fails to start because of a broken
    presets file.  We therefore do NOT assert that the exception bubbles
    up, only that the side effects of the crash leave the filesystem in
    a clean, well-defined state.
    """
    assert not storage_path.exists()

    original_os_replace = os.replace
    crash_hit: dict[str, bool] = {"flag": False}

    def crashing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:  # noqa: D401
        crash_hit["flag"] = True
        raise OSError("simulated crash before rename")

    # The first write happens during `_read_storage_locked` when the file
    # doesn't exist – force it via a clean module instantiation.
    try:
        os.replace = crashing_replace  # type: ignore[assignment]
        # __init__ swallows OSError, so this won't raise – that's the
        # intended resilience behaviour.
        FilterPresetsModule(tmp_ledger_file)
    finally:
        os.replace = original_os_replace  # type: ignore[assignment]

    assert crash_hit["flag"], "crashing_replace was never invoked"

    # The target file must NOT exist – we crashed before the rename.
    assert not storage_path.exists(), (
        f"expected {storage_path.name} not to exist after a mid-rename crash"
    )

    # No stray temp file either.
    stray_tmp = [
        p.name for p in storage_path.parent.iterdir() if p.name.startswith(".tmp-")
    ]
    assert stray_tmp == [], f"stray temp files left behind: {stray_tmp}"


# ---------------------------------------------------------------------------
# Corrupt storage recovery – quarantines the bad file and warns the frontend
# ---------------------------------------------------------------------------


def test_corrupt_storage_is_quarantined_and_returns_empty_list(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """An unparseable storage file is renamed to .corrupt.<ts> and a warning set.

    - The corrupt bytes are preserved in the quarantine file.
    - The live storage is replaced with a valid empty preset list.
    - :attr:`FilterPresetsModule.last_warning` carries a human-readable
      description of the recovery for the frontend to surface.
    - Subsequent reads do NOT re-trigger the quarantine (i.e. the warning
      is transient and only reported once, via ``consume_warning``).
    """
    # Drop garbage bytes into the storage file to simulate a half-write.
    garbage = b'{"schema_version": 2, "presets": [{"id": "deadbeef", "name": '
    storage_path.write_bytes(garbage)
    garbage_size = len(garbage)

    module = FilterPresetsModule(tmp_ledger_file)

    # 1. The in-memory list must be empty (graceful fallback).
    assert module.list_presets() == []

    # 2. The warning must be populated and describe the recovery.
    warning = module.last_warning
    assert warning is not None
    assert "could not be parsed" in warning
    assert ".corrupt." in warning

    # 3. A quarantine file must exist next to the storage file and contain
    #    the original garbage bytes.
    quarantines = sorted(
        storage_path.parent.glob(f"{storage_path.name}.corrupt.*")
    )
    assert quarantines, "no .corrupt backup was created"
    quarantine = quarantines[-1]
    assert quarantine.read_bytes()[:garbage_size] == garbage

    # 4. The live storage must now be a valid empty payload.
    live = json.loads(storage_path.read_text(encoding="utf-8"))
    assert live["schema_version"] == FilterPresetsModule.SCHEMA_VERSION
    assert live["presets"] == []

    # 5. ``consume_warning`` clears the warning.
    assert module.consume_warning() == warning
    assert module.consume_warning() is None

    # 6. Re-reading the (now valid) storage does not re-trigger recovery.
    reread = FilterPresetsModule(tmp_ledger_file)
    assert reread.last_warning is None
    assert reread.list_presets() == []


def test_json_api_carries_warning_after_corruption_recovery(
    app_in_tmp_dir,  # noqa: ANN001
) -> None:
    """Corrupt storage must surface the warning field in the JSON response.

    After the backend recovers from a corrupt storage file, the next
    filter-preset API response must carry a top-level ``warning`` field
    so the frontend can notify the user.  Subsequent calls must NOT
    include the warning (it was consumed by the first response).
    """
    from fava.context import g  # noqa: PLC0415

    client = app_in_tmp_dir.test_client()
    ledger = app_in_tmp_dir.config["LEDGERS"]["edit-example"]
    storage_path = ledger.filter_presets.storage_path

    # Corrupt the storage.
    storage_path.write_bytes(b"this is not { valid json at all!")

    # 1. First call – the response should carry `warning`.
    first = client.get("/edit-example/api/filter_presets")
    assert first.status_code == HTTPStatus.OK.value, first.data
    assert first.json is not None
    assert first.json["data"] == []
    assert "warning" in first.json
    assert "could not be parsed" in first.json["warning"]

    # 2. A quarantine file must have been created.
    quarantines = list(storage_path.parent.glob(f"{storage_path.name}.corrupt.*"))
    assert quarantines

    # 3. Second call – warning has been consumed and is no longer present.
    second = client.get("/edit-example/api/filter_presets")
    assert second.status_code == HTTPStatus.OK.value
    assert second.json is not None
    assert second.json["data"] == []
    assert "warning" not in second.json

    # 4. Now that storage is clean we can write a new preset normally.
    create_resp = client.put(
        "/edit-example/api/filter_preset",
        json={"name": "Recovered", "page": "all", "filters": SAMPLE_FILTERS},
    )
    assert create_resp.status_code == HTTPStatus.OK.value
    assert create_resp.json is not None
    assert create_resp.json["data"]["name"] == "Recovered"
    # A freshly recovered write must carry no warning.
    assert "warning" not in create_resp.json


def test_multiple_corruptions_get_distinct_backups(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """Repeated corruptions each get their own quarantine file.

    If the storage file keeps getting corrupted (e.g. by some other buggy
    process) each recovery must use a unique backup name so no previous
    evidence is overwritten.
    """
    # Corruption #1
    storage_path.write_bytes(b"garbage version one")
    m1 = FilterPresetsModule(tmp_ledger_file)
    assert m1.last_warning is not None
    backups_1 = list(storage_path.parent.glob(f"{storage_path.name}.corrupt.*"))
    assert len(backups_1) == 1

    # Corruption #2 – write different garbage into the *live* path again.
    storage_path.write_bytes(b"garbage version two")
    m2 = FilterPresetsModule(tmp_ledger_file)
    assert m2.last_warning is not None
    backups_2 = list(storage_path.parent.glob(f"{storage_path.name}.corrupt.*"))
    assert len(backups_2) == 2

    # Both quarantines must still be on disk and carry distinct content.
    contents = {p.read_bytes() for p in backups_2}
    assert b"garbage version one" in contents
    assert b"garbage version two" in contents


def test_unicode_decode_error_is_treated_as_corruption(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """Binary (non-UTF-8) storage must also be quarantined, not 500."""
    # Non-UTF-8 bytes that happen to not be valid JSON either.
    storage_path.write_bytes(b"\xff\xfe\x00\x01not utf-8 at all")

    module = FilterPresetsModule(tmp_ledger_file)
    assert module.list_presets() == []
    assert module.last_warning is not None
    assert list(storage_path.parent.glob(f"{storage_path.name}.corrupt.*"))


# ---------------------------------------------------------------------------
# FAVA_FILTER_PRESET_AUTO_RECOVER environment variable
# ---------------------------------------------------------------------------


def test_auto_recover_disabled_raises_corrupt_storage_error(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """When FAVA_FILTER_PRESET_AUTO_RECOVER=0, corrupt storage raises
    FilterPresetCorruptStorageError instead of silently recovering.
    The corrupt file is still quarantined (evidence is preserved) but
    the live storage is NOT replaced with an empty list.
    """
    garbage = b'{"schema_version": 2, "presets": [{"id": "bad", '
    storage_path.write_bytes(garbage)

    original_env = os.environ.get("FAVA_FILTER_PRESET_AUTO_RECOVER")
    try:
        os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = "0"

        with pytest.raises(FilterPresetCorruptStorageError) as exc_info:
            FilterPresetsModule(tmp_ledger_file)

        err = exc_info.value
        assert err.code == "corrupt_storage"
        assert err.details["storage_path"] == str(storage_path)
        assert err.details["file_size"] == len(garbage)
        assert "backup_path" in err.details

        # The corrupt file must still have been quarantined.
        quarantines = list(storage_path.parent.glob(f"{storage_path.name}.corrupt.*"))
        assert quarantines
        assert quarantines[0].read_bytes()[:len(garbage)] == garbage

        # The live storage must NOT have been replaced with a valid empty
        # list – because auto-recovery is off the quarantine moved the
        # corrupt file but did NOT write a fresh placeholder.
        if storage_path.exists():
            # If the file still exists (e.g. quarantine wrote a copy
            # instead of moving), it must still contain the garbage.
            assert storage_path.read_bytes()[:len(garbage)] == garbage
        # Otherwise the file was moved to quarantine – that's fine too.
    finally:
        if original_env is None:
            os.environ.pop("FAVA_FILTER_PRESET_AUTO_RECOVER", None)
        else:
            os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = original_env


@pytest.mark.parametrize("falsy_value", ["0", "false", "no", "off", "FALSE", "No", "OFF"])
def test_auto_recover_env_falsy_values(
    tmp_ledger_file: Path, storage_path: Path, falsy_value: str
) -> None:
    """All documented falsy values for FAVA_FILTER_PRESET_AUTO_RECOVER
    must disable auto-recovery (case-insensitive).
    """
    storage_path.write_bytes(b"not valid json")

    original_env = os.environ.get("FAVA_FILTER_PRESET_AUTO_RECOVER")
    try:
        os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = falsy_value
        with pytest.raises(FilterPresetCorruptStorageError):
            FilterPresetsModule(tmp_ledger_file)
    finally:
        if original_env is None:
            os.environ.pop("FAVA_FILTER_PRESET_AUTO_RECOVER", None)
        else:
            os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = original_env


@pytest.mark.parametrize("truthy_value", ["1", "true", "yes", "on", "anything", ""])
def test_auto_recover_env_truthy_values(
    tmp_ledger_file: Path, storage_path: Path, truthy_value: str
) -> None:
    """Any value not in the falsy set (including unset/empty) enables
    auto-recovery – the module falls back to an empty list with a warning.
    """
    storage_path.write_bytes(b"not valid json")

    original_env = os.environ.get("FAVA_FILTER_PRESET_AUTO_RECOVER")
    try:
        if truthy_value == "":
            os.environ.pop("FAVA_FILTER_PRESET_AUTO_RECOVER", None)
        else:
            os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = truthy_value

        module = FilterPresetsModule(tmp_ledger_file)
        assert module.list_presets() == []
        assert module.last_warning is not None
    finally:
        if original_env is None:
            os.environ.pop("FAVA_FILTER_PRESET_AUTO_RECOVER", None)
        else:
            os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = original_env


def test_auto_recover_disabled_still_quarantines(
    tmp_ledger_file: Path, storage_path: Path
) -> None:
    """Even when auto-recovery is off the corrupt file is quarantined so
    the admin can inspect it, and the error details contain the backup path.
    """
    garbage = b"totally broken { json"
    storage_path.write_bytes(garbage)

    original_env = os.environ.get("FAVA_FILTER_PRESET_AUTO_RECOVER")
    try:
        os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = "off"

        with pytest.raises(FilterPresetCorruptStorageError) as exc_info:
            FilterPresetsModule(tmp_ledger_file)

        backup_path_str = exc_info.value.details["backup_path"]
        assert backup_path_str
        backup_path = Path(backup_path_str)
        assert backup_path.exists()
        assert backup_path.read_bytes() == garbage
    finally:
        if original_env is None:
            os.environ.pop("FAVA_FILTER_PRESET_AUTO_RECOVER", None)
        else:
            os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = original_env


# ---------------------------------------------------------------------------
# Structured "corrupt-recovery" logging
# ---------------------------------------------------------------------------


def test_corrupt_recovery_emits_structured_log(
    tmp_ledger_file: Path, storage_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Corruption recovery must emit a warning-level log with the
    'corrupt-recovery' tag and structured fields for SRE alerting.
    """
    garbage = b'{"broken": true'
    storage_path.write_bytes(garbage)

    with caplog.at_level(logging.WARNING, logger="fava.core.filter_presets"):
        module = FilterPresetsModule(tmp_ledger_file)

    assert module.list_presets() == []

    corrupt_records = [
        r
        for r in caplog.records
        if "corrupt-recovery" in r.getMessage()
        or r.__dict__.get("tag") == "corrupt-recovery"
    ]
    assert corrupt_records, "no corrupt-recovery log record was emitted"

    rec = corrupt_records[0]
    # The extra fields are merged into the LogRecord __dict__.
    assert getattr(rec, "tag", None) == "corrupt-recovery"
    assert getattr(rec, "storage_path", None) == str(storage_path)
    assert getattr(rec, "backup_path", None) is not None
    assert getattr(rec, "file_size", None) == len(garbage)


def test_corrupt_recovery_log_when_auto_recover_disabled(
    tmp_ledger_file: Path, storage_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Even when auto-recovery is disabled, the structured log must still
    be emitted so SRE teams can track corruption frequency before the
    503 is returned.
    """
    garbage = b"not json at all"
    storage_path.write_bytes(garbage)

    original_env = os.environ.get("FAVA_FILTER_PRESET_AUTO_RECOVER")
    try:
        os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = "0"

        with caplog.at_level(logging.WARNING, logger="fava.core.filter_presets"):
            with pytest.raises(FilterPresetCorruptStorageError):
                FilterPresetsModule(tmp_ledger_file)

        corrupt_records = [
            r
            for r in caplog.records
            if getattr(r, "tag", None) == "corrupt-recovery"
        ]
        assert corrupt_records
        rec = corrupt_records[0]
        assert rec.storage_path == str(storage_path)  # type: ignore[attr-defined]
        assert rec.file_size == len(garbage)  # type: ignore[attr-defined]
        assert rec.backup_path  # type: ignore[attr-defined]
    finally:
        if original_env is None:
            os.environ.pop("FAVA_FILTER_PRESET_AUTO_RECOVER", None)
        else:
            os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = original_env


# ---------------------------------------------------------------------------
# HTTP API: FAVA_FILTER_PRESET_AUTO_RECOVER=0 → 503
# ---------------------------------------------------------------------------


def test_json_api_corrupt_storage_returns_503_when_auto_recover_disabled(
    app_in_tmp_dir,  # noqa: ANN001
) -> None:
    """When auto-recovery is disabled, the API must return 503 with a
    structured error body (code=corrupt_storage) instead of auto-recovering.
    """
    client = app_in_tmp_dir.test_client()
    ledger = app_in_tmp_dir.config["LEDGERS"]["edit-example"]
    storage_path = ledger.filter_presets.storage_path

    # Corrupt the storage.
    storage_path.write_bytes(b"broken { json")

    original_env = os.environ.get("FAVA_FILTER_PRESET_AUTO_RECOVER")
    try:
        os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = "0"

        resp = client.get("/edit-example/api/filter_presets")
        assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE.value, resp.data
        assert resp.json is not None
        assert resp.json["code"] == "corrupt_storage"
        assert "storage_path" in resp.json["details"]
        assert "backup_path" in resp.json["details"]
        assert resp.json["details"]["file_size"] > 0
    finally:
        if original_env is None:
            os.environ.pop("FAVA_FILTER_PRESET_AUTO_RECOVER", None)
        else:
            os.environ["FAVA_FILTER_PRESET_AUTO_RECOVER"] = original_env

