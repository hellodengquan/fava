"""Tests for the root anchor module."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from fava.core.root_anchor import RootAnchor
from fava.core.root_anchor import RootAnchorChangedError


def test_root_anchor_basic(tmp_path: Path) -> None:
    """Basic functionality: resolve and join paths correctly."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)

    assert anchor.root_path == root.resolve()
    assert anchor.inode == root.stat().st_ino
    assert anchor.check() is True
    assert anchor.invalid is False

    assert anchor.join("sub", "file.txt") == (root / "sub" / "file.txt").resolve()
    assert anchor.resolve("file.txt") == (root / "file.txt").resolve()
    assert anchor.resolve(str(root / "abs.txt")) == (root / "abs.txt").resolve()


def test_root_anchor_renamed_directory(tmp_path: Path) -> None:
    """Root directory renamed -> check() returns False, path resolution raises."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)
    assert anchor.check() is True

    root.rename(tmp_path / "ledger_old")

    anchor._last_check = 0
    assert anchor.check() is False
    assert anchor.invalid is True

    with pytest.raises(RootAnchorChangedError):
        anchor.resolve("file.txt")

    with pytest.raises(RootAnchorChangedError):
        anchor.join("sub", "file.txt")

    with pytest.raises(RootAnchorChangedError):
        anchor.ensure_valid()


def test_root_anchor_deleted_directory(tmp_path: Path) -> None:
    """Root directory deleted -> check() returns False."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)
    assert anchor.check() is True

    import shutil
    shutil.rmtree(root)

    anchor._last_check = 0
    assert anchor.check() is False
    assert anchor.invalid is True

    with pytest.raises(RootAnchorChangedError):
        anchor.ensure_valid()


def test_root_anchor_replaced_directory(tmp_path: Path) -> None:
    """Root directory deleted and recreated (inode changed) -> check() returns False."""
    root = tmp_path / "ledger"
    root.mkdir()
    original_inode = root.stat().st_ino

    anchor = RootAnchor(root, use_watcher=False)
    assert anchor.check() is True

    import shutil
    shutil.rmtree(root)
    root.mkdir()

    new_inode = root.stat().st_ino
    assert original_inode != new_inode

    anchor._last_check = 0
    assert anchor.check() is False
    assert anchor.invalid is True
    assert anchor.inode == original_inode


def test_root_anchor_refresh_after_recreate(tmp_path: Path) -> None:
    """After refresh(), the anchor picks up the new inode."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)
    original_inode = anchor.inode

    import shutil
    shutil.rmtree(root)
    root.mkdir()

    anchor._last_check = 0
    assert anchor.check() is False

    anchor.refresh()

    assert anchor.check() is True
    assert anchor.invalid is False
    assert anchor.inode != original_inode
    assert anchor.inode == root.stat().st_ino

    assert anchor.resolve("file.txt") == (root / "file.txt").resolve()


def test_root_anchor_lazy_check_interval(tmp_path: Path) -> None:
    """check() is lazy: within check_interval, it doesn't re-stat."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, check_interval=10.0, use_watcher=False)
    assert anchor.check() is True

    root.rename(tmp_path / "ledger_old")

    assert anchor.check() is True
    assert anchor.invalid is False

    anchor._last_check = 0

    assert anchor.check() is False
    assert anchor.invalid is True


def test_root_anchor_mark_invalid(tmp_path: Path) -> None:
    """mark_invalid() forces invalid state."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)
    assert anchor.check() is True

    anchor.mark_invalid()
    assert anchor.invalid is True
    assert anchor.check() is False

    anchor.refresh()
    assert anchor.invalid is False
    assert anchor.check() is True


def test_root_anchor_refresh_missing_dir(tmp_path: Path) -> None:
    """refresh() on a missing directory raises FileNotFoundError."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)

    import shutil
    shutil.rmtree(root)

    with pytest.raises(FileNotFoundError):
        anchor.refresh()


def test_root_anchor_close(tmp_path: Path) -> None:
    """close() can be called safely even without a watcher."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)
    anchor.close()
    anchor.close()


def test_root_anchor_with_watcher(tmp_path: Path) -> None:
    """RootAnchor with watcher enabled detects directory rename."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, check_interval=60.0, use_watcher=True)
    assert anchor.wait_watcher_started(timeout=3.0), "watcher failed to start"
    assert anchor.check() is True

    root.rename(tmp_path / "ledger_old")

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if anchor.invalid:
            break
        time.sleep(0.05)

    assert anchor.invalid is True, "watcher should have detected the rename"
    assert anchor.check() is False

    anchor.close()


def test_root_anchor_watcher_recreate(tmp_path: Path) -> None:
    """After refresh(), watcher is restarted for the new directory."""
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, check_interval=60.0, use_watcher=True)
    assert anchor.wait_watcher_started(timeout=3.0)

    root.rename(tmp_path / "ledger_old")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if anchor.invalid:
            break
        time.sleep(0.05)
    assert anchor.invalid is True

    (tmp_path / "ledger").mkdir()
    anchor.refresh()
    assert anchor.invalid is False
    assert anchor.wait_watcher_started(timeout=3.0)

    (tmp_path / "ledger").rename(tmp_path / "ledger_again")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if anchor.invalid:
            break
        time.sleep(0.05)
    assert anchor.invalid is True, "restarted watcher should detect second rename"

    anchor.close()


def test_root_anchor_relative_path_input(tmp_path: Path) -> None:
    """RootAnchor resolves relative root paths."""
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        Path("ledger").mkdir()
        anchor = RootAnchor(Path("ledger"), use_watcher=False)
        assert anchor.root_path.is_absolute()
        assert anchor.root_path == (tmp_path / "ledger").resolve()
    finally:
        os.chdir(original_cwd)
