"""Shared fixtures for snapshot tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fava.core.snapshots import SnapshotStore


@pytest.fixture
def mock_ledger(tmp_path: Path) -> MagicMock:
    """Create a mock FavaLedger with a temp beancount file."""
    ledger = MagicMock()
    beancount_file = tmp_path / "test.beancount"
    beancount_file.touch()
    ledger.beancount_file_path = str(beancount_file)
    return ledger


@pytest.fixture
def snapshot_store(mock_ledger: MagicMock) -> SnapshotStore:
    """Create a SnapshotStore instance."""
    store = SnapshotStore(mock_ledger)
    store.load_file()
    return store
