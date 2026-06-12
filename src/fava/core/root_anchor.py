"""Root anchor tracking for ledger base directory.

Detects when the ledger's root directory is moved, renamed, deleted,
or replaced (inode change) so that cached path resolutions are
invalidated and cannot be used for path-traversal attacks against a
replaced directory.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable


log = logging.getLogger(__name__)

try:  # pragma: no cover - import-time feature detection
    from watchfiles import Change
    from watchfiles import watch

    _WATCHFILES_AVAILABLE = True
except ImportError:  # pragma: no cover
    _WATCHFILES_AVAILABLE = False


class RootAnchorChangedError(RuntimeError):
    """Raised when the root anchor's inode or path has changed."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"Root anchor directory '{path}' has been moved, renamed, "
            "deleted, or replaced (inode changed). Path resolution is "
            "disabled until the ledger is reloaded."
        )
        self.path = path


class _RootWatchThread(threading.Thread):
    """Watchfiles thread that watches the parent of the root directory.

    We watch the *parent* directory (non-recursively) because that is
    where rename/delete events for the root directory itself will
    surface.  When any change is detected, we re-stat the root to
    verify whether its inode has changed.
    """

    def __init__(self, root_path: Path, on_detected: Callable[[], None]) -> None:
        super().__init__(daemon=True)
        self._root_path = root_path
        self._root_name = root_path.name
        self._parent = root_path.parent
        self._on_detected = on_detected
        self._stop_event = threading.Event()
        self._started = threading.Event()

    def stop(self) -> None:
        """Stop the watcher thread."""
        self._stop_event.set()
        if self._started.is_set():
            self.join(timeout=2)

    def wait_started(self, timeout: float = 2.0) -> bool:
        """Wait until the watcher thread has started watching."""
        return self._started.wait(timeout=timeout)

    def run(self) -> None:  # pragma: no cover - exercised in tests
        """Watch for changes to the root directory."""
        atexit.register(self.stop)
        # Do a quick initial stat before starting the watcher so that
        # the first iteration of watch() has something to compare to.
        try:
            self._root_path.stat()
        except OSError:
            pass
        self._started.set()
        try:
            for _changes in watch(
                self._parent,
                recursive=False,
                stop_event=self._stop_event,
                ignore_permission_denied=True,
            ):
                # Any change to the parent directory could mean our
                # root was renamed/deleted/replaced.  Rather than
                # trying to parse event types (which vary by OS and
                # filesystem), we simply re-stat the root path and
                # compare inodes.
                log.debug("Parent directory change detected, checking root anchor")
                self._on_detected()
        except Exception:
            log.exception("Root anchor watcher thread failed")


class RootAnchor:
    """Tracks the ledger's root directory via its inode.

    The "root anchor" is the directory containing the beancount file.
    Because relative paths are resolved against this directory, an
    attacker who can replace the directory (e.g. rename it and create
    a new one with the same name) could bypass path-containment checks.

    This class guards against that by:

    1. Remembering the directory's inode at construction time.
    2. Verifying the inode on every path resolution (with a short
       cooldown / "lazy check" interval to avoid excessive ``stat``
       calls).
    3. Optionally using ``watchfiles`` to receive instant notification
       when the directory is renamed, deleted, or replaced.

    When a change is detected, the anchor is marked as "invalid" and
    further path-resolution attempts raise
    :class:`RootAnchorChangedError` until :meth:`refresh` is called.
    """

    def __init__(
        self,
        root_path: Path,
        *,
        check_interval: float = 2.0,
        use_watcher: bool = True,
    ) -> None:
        self._check_interval = check_interval
        self._root_path = Path(root_path).resolve()
        self._inode: int = self._stat_inode()
        self._last_check: float = time.monotonic()
        self._invalid: bool = False
        self._watcher: _RootWatchThread | None = None
        self._watcher_lock = threading.Lock()

        if use_watcher and _WATCHFILES_AVAILABLE:
            self._start_watcher()

    def _stat_inode(self) -> int:
        return self._root_path.stat().st_ino

    def _verify_inode(self) -> bool:
        """Verify the root directory's inode matches the cached one.

        Thread-safe: acquires no locks because it only reads immutable
        state and ``_invalid`` is a simple bool.
        """
        try:
            current_inode = self._stat_inode()
        except (FileNotFoundError, NotADirectoryError, OSError):
            self._invalid = True
            self._last_check = 0
            return False

        if current_inode != self._inode:
            self._invalid = True
            self._last_check = 0
            return False

        self._last_check = time.monotonic()
        return True

    def _start_watcher(self) -> None:  # pragma: no cover - trivial threading
        with self._watcher_lock:
            if self._watcher is not None:
                return

            self._watcher = _RootWatchThread(
                self._root_path, self._verify_inode
            )
            self._watcher.start()

    def wait_watcher_started(self, timeout: float = 2.0) -> bool:
        """Wait until the watcher thread has started.

        For testing and for code that wants to ensure the watcher is
        fully armed before proceeding.
        """
        if self._watcher is None:
            return False
        return self._watcher.wait_started(timeout=timeout)

    def _stop_watcher(self) -> None:
        with self._watcher_lock:
            if self._watcher is not None:
                self._watcher.stop()
                self._watcher = None

    def close(self) -> None:
        """Stop the watcher thread and release resources."""
        self._stop_watcher()

    def __del__(self) -> None:
        self.close()

    @property
    def root_path(self) -> Path:
        """The resolved root path (as of the last refresh)."""
        return self._root_path

    @property
    def inode(self) -> int:
        """The inode of the root directory (as of the last refresh)."""
        return self._inode

    @property
    def invalid(self) -> bool:
        """Whether the anchor has been detected as changed/deleted."""
        return self._invalid

    def mark_invalid(self) -> None:
        """Explicitly mark the anchor as invalid.

        Can be called by external code that knows the root has changed
        (e.g. the main ledger file watcher).
        """
        self._invalid = True
        self._last_check = 0

    def refresh(self) -> None:
        """Re-resolve the root directory and re-base the anchor.

        Re-reads the inode of :attr:`root_path` and clears the invalid
        flag.  If a watcher is running, it is restarted so that it
        watches the (possibly new) directory.

        Raises:
            FileNotFoundError: If the root path no longer exists.
        """
        self._root_path = Path(self._root_path).resolve()
        self._inode = self._stat_inode()
        self._invalid = False
        self._last_check = time.monotonic()

        if self._watcher is not None:
            self._stop_watcher()
            self._start_watcher()

    def check(self) -> bool:
        """Check whether the root anchor is still valid.

        Uses lazy evaluation: if the last check was within
        ``check_interval`` seconds, this returns immediately with the
        cached result.  Otherwise, it stats the root directory and
        compares inodes.

        Returns:
            ``True`` if the anchor is still valid (same inode and path
            exists), ``False`` otherwise.
        """
        if self._invalid:
            return False

        now = time.monotonic()
        if now - self._last_check < self._check_interval:
            return True

        self._last_check = now
        try:
            current_inode = self._stat_inode()
        except (FileNotFoundError, NotADirectoryError, OSError):
            self._invalid = True
            return False

        if current_inode != self._inode:
            self._invalid = True
            return False

        return True

    def ensure_valid(self) -> None:
        """Ensure the root anchor is still valid.

        Raises:
            RootAnchorChangedError: If the root directory has been
                moved, renamed, deleted, or replaced.
        """
        if not self.check():
            raise RootAnchorChangedError(self._root_path)

    def resolve(self, filename: str | Path) -> Path:
        """Resolve a filename against the root directory.

        If *filename* is relative, it is resolved against
        :attr:`root_path`.  Absolute paths are resolved as-is (but the
        root anchor is still validated).

        Args:
            filename: A filename that may be absolute or relative.

        Returns:
            The resolved absolute :class:`Path`.

        Raises:
            RootAnchorChangedError: If the root anchor is invalid.
        """
        self.ensure_valid()
        path = Path(filename)
        if not path.is_absolute():
            path = self._root_path / path
        return path.resolve()

    def join(self, *args: str) -> Path:
        """Join path components to the root directory and resolve.

        Args:
            *args: Path components to join to the root.

        Returns:
            The resolved absolute :class:`Path`.

        Raises:
            RootAnchorChangedError: If the root anchor is invalid.
        """
        self.ensure_valid()
        return self._root_path.joinpath(*args).resolve()
