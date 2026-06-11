from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask
    from flask.testing import FlaskClient

    from fava.core import FavaLedger

    from .conftest import GetFavaLedger


def _find_entry_by_type(ledger: FavaLedger, type_name: str):
    """Find an entry of a given type in the ledger."""
    for entry in ledger.all_entries:
        if entry.__class__.__name__ == type_name:
            return entry
    return None


def _find_entry_by_date_and_type(
    ledger: FavaLedger, date: datetime.date, type_name: str
):
    """Find an entry by date and type."""
    for entry in ledger.all_entries:
        if entry.date == date and entry.__class__.__name__ == type_name:
            return entry
    return None


def test_set_metadata_update_existing(app_in_tmp_dir: Flask) -> None:
    """Test set_metadata updates existing metadata value instead of inserting."""
    with app_in_tmp_dir.test_request_context("/edit-example/"):
        app_in_tmp_dir.preprocess_request()
        from fava.context import g

        entry = _find_entry_by_type(g.ledger, "Transaction")
        assert entry is not None
        entry_date = entry.date
        entry_hash = hash_entry(entry)

        result = g.ledger.file.set_metadata(
            entry_hash, "review_status", "pending"
        )
        assert result is False

        g.ledger.load_file()
        entry2 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry2 is not None
        assert entry2.meta.get("review_status") == "pending"

        entry_hash2 = hash_entry(entry2)
        result2 = g.ledger.file.set_metadata(
            entry_hash2, "review_status", "approved"
        )
        assert result2 is True

        g.ledger.load_file()
        entry3 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry3 is not None
        assert entry3.meta.get("review_status") == "approved"

        file_path = Path(g.ledger.beancount_file_path)
        content = file_path.read_text("utf-8")
        status_matches = re.findall(r"review_status\s*:\s*", content)
        assert len(status_matches) == 1


def test_set_metadata_with_notes(app_in_tmp_dir: Flask) -> None:
    """Test set_metadata with review_notes."""
    with app_in_tmp_dir.test_request_context("/edit-example/"):
        app_in_tmp_dir.preprocess_request()
        from fava.context import g

        entry = _find_entry_by_type(g.ledger, "Transaction")
        assert entry is not None
        entry_date = entry.date
        entry_hash = hash_entry(entry)

        g.ledger.file.set_metadata(entry_hash, "review_notes", "Check amount")

        g.ledger.load_file()
        entry2 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry2 is not None
        assert entry2.meta.get("review_notes") == "Check amount"

        entry_hash2 = hash_entry(entry2)
        g.ledger.file.set_metadata(
            entry_hash2, "review_notes", "Amount verified"
        )

        g.ledger.load_file()
        entry3 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry3 is not None
        assert entry3.meta.get("review_notes") == "Amount verified"


def test_delete_metadata(app_in_tmp_dir: Flask) -> None:
    """Test delete_metadata removes metadata correctly."""
    with app_in_tmp_dir.test_request_context("/edit-example/"):
        app_in_tmp_dir.preprocess_request()
        from fava.context import g

        entry = _find_entry_by_type(g.ledger, "Transaction")
        assert entry is not None
        entry_date = entry.date
        entry_hash = hash_entry(entry)

        g.ledger.file.set_metadata(entry_hash, "review_status", "pending")
        g.ledger.load_file()

        entry2 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry2 is not None
        entry_hash2 = hash_entry(entry2)

        g.ledger.file.set_metadata(
            entry_hash2, "reviewed_at", "2024-01-01T00:00:00"
        )
        g.ledger.load_file()

        entry3 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry3 is not None
        assert "review_status" in entry3.meta
        assert "reviewed_at" in entry3.meta

        entry_hash3 = hash_entry(entry3)
        result = g.ledger.file.delete_metadata(
            entry_hash3, "review_status"
        )
        assert result is True

        g.ledger.load_file()
        entry4 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry4 is not None
        assert "review_status" not in entry4.meta
        assert "reviewed_at" in entry4.meta

        entry_hash4 = hash_entry(entry4)
        g.ledger.file.delete_metadata(entry_hash4, "reviewed_at")
        g.ledger.load_file()
        entry5 = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert entry5 is not None
        assert "reviewed_at" not in entry5.meta


def test_delete_nonexistent_metadata(app_in_tmp_dir: Flask) -> None:
    """Test delete_metadata on nonexistent key returns False."""
    with app_in_tmp_dir.test_request_context("/edit-example/"):
        app_in_tmp_dir.preprocess_request()
        from fava.context import g

        entry = _find_entry_by_type(g.ledger, "Transaction")
        assert entry is not None
        entry_hash = hash_entry(entry)

        result = g.ledger.file.delete_metadata(
            entry_hash, "nonexistent_key_12345"
        )
        assert result is False


def test_api_update_review_status(
    app: Flask, test_client: FlaskClient
) -> None:
    """Test PUT /api/update_review_status endpoint."""
    entry_date = None
    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g
        from fava.beans.funcs import hash_entry as hash_entry_local

        entry = _find_entry_by_type(g.ledger, "Transaction")
        if entry is None:
            pytest.skip("No Transaction entry found in example ledger")
        entry_date = entry.date
        entry_hash = hash_entry_local(entry)

    response = test_client.put(
        "/example/api/update_review_status",
        json={
            "entry_hash": entry_hash,
            "status": "approved",
            "notes": "Looks good",
        },
    )
    from tests.test_json_api import assert_api_success

    result = assert_api_success(response)
    assert "approved" in result

    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g

        g.ledger.load_file()
        updated = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert updated is not None
        assert updated.meta.get("review_status") == "approved"
        assert updated.meta.get("review_notes") == "Looks good"
        assert "reviewed_at" in updated.meta


def test_api_update_review_status_invalid_status(
    app: Flask, test_client: FlaskClient
) -> None:
    """Test PUT /api/update_review_status with invalid status."""
    response = test_client.put(
        "/example/api/update_review_status",
        json={
            "entry_hash": "invalid_hash",
            "status": "invalid_status",
            "notes": "",
        },
    )
    from tests.test_json_api import assert_api_error

    assert_api_error(response, "Invalid review status: invalid_status")


def test_api_update_review_status_pending(
    app: Flask, test_client: FlaskClient
) -> None:
    """Test PUT /api/update_review_status with pending status."""
    entry_date = None
    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g
        from fava.beans.funcs import hash_entry as hash_entry_local

        entry = _find_entry_by_type(g.ledger, "Transaction")
        if entry is None:
            pytest.skip("No Transaction entry found in example ledger")
        entry_date = entry.date
        entry_hash = hash_entry_local(entry)

    response = test_client.put(
        "/example/api/update_review_status",
        json={
            "entry_hash": entry_hash,
            "status": "pending",
            "notes": "",
        },
    )
    from tests.test_json_api import assert_api_success

    result = assert_api_success(response)
    assert "pending" in result

    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g

        g.ledger.load_file()
        updated = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert updated is not None
        assert updated.meta.get("review_status") == "pending"
        assert "reviewed_at" in updated.meta


def test_api_clear_review_status(
    app: Flask, test_client: FlaskClient
) -> None:
    """Test PUT /api/clear_review_status endpoint."""
    entry_date = None
    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g
        from fava.beans.funcs import hash_entry as hash_entry_local

        entry = _find_entry_by_type(g.ledger, "Transaction")
        if entry is None:
            pytest.skip("No Transaction entry found in example ledger")
        entry_date = entry.date
        entry_hash = hash_entry_local(entry)

    response1 = test_client.put(
        "/example/api/update_review_status",
        json={
            "entry_hash": entry_hash,
            "status": "rejected",
            "notes": "Wrong amount",
        },
    )
    from tests.test_json_api import assert_api_success

    assert_api_success(response1)

    entry_hash2 = None
    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g
        from fava.beans.funcs import hash_entry as hash_entry_local2

        g.ledger.load_file()
        before = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert before is not None
        assert before.meta.get("review_status") == "rejected"
        entry_hash2 = hash_entry_local2(before)

    response = test_client.put(
        "/example/api/clear_review_status",
        json={"entry_hash": entry_hash2},
    )

    result = assert_api_success(response)
    assert "cleared" in result

    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g

        g.ledger.load_file()
        after = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert after is not None
        assert "review_status" not in after.meta
        assert "review_notes" not in after.meta
        assert "reviewed_at" not in after.meta


def test_api_update_review_status_clears_notes_when_empty(
    app: Flask, test_client: FlaskClient
) -> None:
    """Test that empty notes are cleared on update."""
    entry_date = None
    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g
        from fava.beans.funcs import hash_entry as hash_entry_local

        entry = _find_entry_by_type(g.ledger, "Transaction")
        if entry is None:
            pytest.skip("No Transaction entry found in example ledger")
        entry_date = entry.date
        entry_hash = hash_entry_local(entry)

    response1 = test_client.put(
        "/example/api/update_review_status",
        json={
            "entry_hash": entry_hash,
            "status": "pending",
            "notes": "Initial note",
        },
    )
    from tests.test_json_api import assert_api_success

    assert_api_success(response1)

    entry_hash2 = None
    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g
        from fava.beans.funcs import hash_entry as hash_entry_local2

        g.ledger.load_file()
        before = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert before is not None
        assert before.meta.get("review_notes") == "Initial note"
        entry_hash2 = hash_entry_local2(before)

    response2 = test_client.put(
        "/example/api/update_review_status",
        json={
            "entry_hash": entry_hash2,
            "status": "approved",
            "notes": "",
        },
    )
    assert_api_success(response2)

    with app.test_request_context("/example/"):
        app.preprocess_request()
        from fava.context import g

        g.ledger.load_file()
        after = _find_entry_by_date_and_type(
            g.ledger, entry_date, "Transaction"
        )
        assert after is not None
        assert after.meta.get("review_status") == "approved"
        assert "review_notes" not in after.meta


def test_serialization_includes_review_meta(
    get_ledger: GetFavaLedger
) -> None:
    """Test that Document serialization includes review metadata."""
    from fava.serialisation import serialise

    ledger = get_ledger("example")
    entry = _find_entry_by_type(ledger, "Document")
    if entry is None:
        pytest.skip("No Document entry found in example ledger")

    entry_with_meta = entry._replace(
        meta={
            **entry.meta,
            "review_status": "approved",
            "review_notes": "Test note",
            "reviewed_at": "2024-01-01T00:00:00",
        }
    )

    serialized = serialise(entry_with_meta)
    assert "review_status" in serialized["meta"]
    assert serialized["meta"]["review_status"] == "approved"
    assert serialized["meta"]["review_notes"] == "Test note"
    assert serialized["meta"]["reviewed_at"] == "2024-01-01T00:00:00"
    assert serialized["t"] == "Document"
