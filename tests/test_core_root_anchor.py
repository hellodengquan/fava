"""Tests for the root anchor module."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from fava.core.root_anchor import DEFAULT_LAZY_POLL_INTERVAL
from fava.core.root_anchor import FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL
from fava.core.root_anchor import get_root_anchor_check_interval
from fava.core.root_anchor import InvalidRootAnchorConfigError
from fava.core.root_anchor import RootAnchor
from fava.core.root_anchor import RootAnchorChangedError


def test_get_root_anchor_check_interval_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL unset -> DEFAULT_LAZY_POLL_INTERVAL."""
    monkeypatch.delenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, raising=False)
    assert get_root_anchor_check_interval() == DEFAULT_LAZY_POLL_INTERVAL


def test_get_root_anchor_check_interval_valid_custom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL set to valid positive number."""
    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "0.1")
    assert get_root_anchor_check_interval() == 0.1

    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "10")
    assert get_root_anchor_check_interval() == 10.0

    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "3.14")
    assert get_root_anchor_check_interval() == 3.14


def test_get_root_anchor_check_interval_invalid_non_numeric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric value -> InvalidRootAnchorConfigError."""
    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "abc")
    with pytest.raises(InvalidRootAnchorConfigError, match="not a valid number"):
        get_root_anchor_check_interval()

    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "")
    with pytest.raises(InvalidRootAnchorConfigError, match="not a valid number"):
        get_root_anchor_check_interval()


def test_get_root_anchor_check_interval_invalid_non_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero or negative value -> InvalidRootAnchorConfigError."""
    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "0")
    with pytest.raises(
        InvalidRootAnchorConfigError,
        match="must be greater than 0",
    ):
        get_root_anchor_check_interval()

    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "-1")
    with pytest.raises(
        InvalidRootAnchorConfigError,
        match="must be greater than 0",
    ):
        get_root_anchor_check_interval()


def test_root_anchor_uses_env_interval_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without env, RootAnchor defaults to DEFAULT_LAZY_POLL_INTERVAL."""
    monkeypatch.delenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, raising=False)
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)
    assert anchor._check_interval == DEFAULT_LAZY_POLL_INTERVAL


def test_root_anchor_uses_env_interval_custom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """RootAnchor reads custom interval from env and applies it to lazy checks."""
    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "60")
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, use_watcher=False)
    assert anchor._check_interval == 60.0

    # With a 60-second interval, rename should NOT be detected
    # immediately (within the interval window) unless _last_check is 0.
    root.rename(tmp_path / "ledger_old")
    assert anchor.check() is True
    assert anchor.invalid is False

    # Force the check to bypass the lazy cooldown: should detect.
    anchor._last_check = 0
    assert anchor.check() is False


def test_root_anchor_uses_env_interval_illegal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Illegal config causes RootAnchor() / FavaLedger() startup to fail."""
    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "0")
    root = tmp_path / "ledger"
    root.mkdir()

    with pytest.raises(
        InvalidRootAnchorConfigError,
        match="must be greater than 0",
    ):
        RootAnchor(root, use_watcher=False)

    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "not_a_number")
    with pytest.raises(
        InvalidRootAnchorConfigError,
        match="not a valid number",
    ):
        RootAnchor(root, use_watcher=False)


def test_root_anchor_explicit_interval_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An explicitly-passed check_interval takes precedence over env."""
    monkeypatch.setenv(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL, "99")
    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, check_interval=0.25, use_watcher=False)
    assert anchor._check_interval == 0.25


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

    time.sleep(0.2)

    root.rename(tmp_path / "ledger_old")

    deadline = time.monotonic() + 8.0
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
