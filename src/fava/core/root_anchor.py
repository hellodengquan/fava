"""Root anchor tracking for ledger base directory.

Detects when the ledger's root directory is moved, renamed, deleted,
or replaced (inode change) so that cached path resolutions are
invalidated and cannot be used for path-traversal attacks against a
replaced directory.

The lazy-check interval is configurable via the environment variable
:envvar:`FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL` (in seconds,
default ``5``).
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fava.helpers import FavaAPIError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    if _PROMETHEUS_IMPORT_AVAILABLE := False:  # noqa: F841 - placeholder for type-hints only
        from prometheus_client import Counter as Counter_t
        from prometheus_client import Histogram as Histogram_t


log = logging.getLogger(__name__)

try:  # pragma: no cover - import-time feature detection
    from watchfiles import Change
    from watchfiles import watch

    _WATCHFILES_AVAILABLE = True
except ImportError:  # pragma: no cover
    _WATCHFILES_AVAILABLE = False

try:  # pragma: no cover - optional observability dependency
    from prometheus_client import Counter
    from prometheus_client import Histogram

    _PROMETHEUS_AVAILABLE = True

    _ROOT_ANCHOR_WATCHDOG_START_FAILURES = Counter(
        "fava_root_anchor_watchdog_start_failures_total",
        "Number of times the root-anchor watchfiles watchdog thread failed to start.",
    )
    _ROOT_ANCHOR_LAZY_FALLBACK = Counter(
        "fava_root_anchor_lazy_fallback_total",
        "Number of times a RootAnchor fell back to pure lazy-poll mode "
        "(watchfiles unavailable, disabled, or watchdog start failed).",
    )
    _ROOT_ANCHOR_LAZY_DETECTION = Counter(
        "fava_root_anchor_lazy_detection_total",
        "Number of inode changes detected via the lazy-poll path "
        "(not via the watchdog callback).",
    )
    _ROOT_ANCHOR_DETECTION_LATENCY = Histogram(
        "fava_root_anchor_detection_latency_seconds",
        "Histogram of elapsed time (seconds) between the last successful "
        "validation and the detection of an inode change or missing "
        "directory.  Samples are recorded regardless of detection path "
        "(watchdog callback or lazy poll).",
        buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0),
    )

except ImportError:  # pragma: no cover - optional dependency absent
    _PROMETHEUS_AVAILABLE = False
    _ROOT_ANCHOR_WATCHDOG_START_FAILURES = None
    _ROOT_ANCHOR_LAZY_FALLBACK = None
    _ROOT_ANCHOR_LAZY_DETECTION = None
    _ROOT_ANCHOR_DETECTION_LATENCY = None


def _metric_counter_inc(counter: object | None) -> None:
    """Safely increment a Counter if prometheus_client is available."""
    if counter is not None:
        counter.inc()  # type: ignore[attr-defined]


def _metric_histogram_observe(histogram: object | None, value: float) -> None:
    """Safely observe a Histogram value if prometheus_client is available."""
    if histogram is not None:
        histogram.observe(value)  # type: ignore[attr-defined]


FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL = "FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL"
DEFAULT_LAZY_POLL_INTERVAL: float = 5.0


class InvalidRootAnchorConfigError(FavaAPIError):
    """Raised when the root anchor environment configuration is invalid."""

    def __init__(self, value: str, *, reason: str) -> None:
        super().__init__(
            f"Invalid value for {FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL}="
            f"{value!r}: {reason}."
        )


def get_root_anchor_check_interval() -> float:
    """Read the lazy-poll interval from the environment.

    Returns:
        The parsed interval in seconds.

    Raises:
        InvalidRootAnchorConfigError: If the env var is set but has an
            invalid value (non-numeric, zero, or negative).
    """
    raw = os.environ.get(FAVA_ROOT_ANCHOR_LAZY_POLL_INTERVAL)
    if raw is None:
        return DEFAULT_LAZY_POLL_INTERVAL

    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise InvalidRootAnchorConfigError(
            raw, reason="not a valid number"
        ) from None

    if value <= 0:
        raise InvalidRootAnchorConfigError(
            raw, reason="must be greater than 0 seconds"
        )

    return value


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
        check_interval: float | None = None,
        use_watcher: bool = True,
    ) -> None:
        self._watcher: _RootWatchThread | None = None
        self._watcher_lock = threading.Lock()
        self._invalid: bool = False

        if check_interval is None:
            check_interval = get_root_anchor_check_interval()
        self._check_interval = check_interval
        self._root_path = Path(root_path).resolve()
        self._inode: int = self._stat_inode()
        self._last_check: float = time.monotonic()

        if use_watcher and _WATCHFILES_AVAILABLE:
            try:
                self._start_watcher()
            except Exception:
                log.exception("Root anchor watcher failed to start, falling back to lazy poll")
                _metric_counter_inc(_ROOT_ANCHOR_WATCHDOG_START_FAILURES)
                _metric_counter_inc(_ROOT_ANCHOR_LAZY_FALLBACK)
                self._watcher = None
        else:
            if use_watcher:
                log.debug(
                    "watchfiles not available, root anchor falling back to lazy poll"
                )
            _metric_counter_inc(_ROOT_ANCHOR_LAZY_FALLBACK)

    def _stat_inode(self) -> int:
        return self._root_path.stat().st_ino

    def _verify_inode(self) -> bool:
        """Verify the root directory's inode matches the cached one.

        Thread-safe: acquires no locks because it only reads immutable
        state and ``_invalid`` is a simple bool.
        """
        now = time.monotonic()
        try:
            current_inode = self._stat_inode()
        except (FileNotFoundError, NotADirectoryError, OSError):
            _metric_histogram_observe(
                _ROOT_ANCHOR_DETECTION_LATENCY, now - self._last_check
            )
            self._invalid = True
            self._last_check = 0
            return False

        if current_inode != self._inode:
            _metric_histogram_observe(
                _ROOT_ANCHOR_DETECTION_LATENCY, now - self._last_check
            )
            self._invalid = True
            self._last_check = 0
            return False

        self._last_check = now
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
        """Stop the watcher thread and release resources.

        Safe to call multiple times and also safe even when
        ``__init__`` failed partway through (before all attributes
        were set).
        """
        try:
            self._stop_watcher()
        except AttributeError:
            pass

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

        prev_check = self._last_check
        self._last_check = now
        try:
            current_inode = self._stat_inode()
        except (FileNotFoundError, NotADirectoryError, OSError):
            _metric_counter_inc(_ROOT_ANCHOR_LAZY_DETECTION)
            _metric_histogram_observe(
                _ROOT_ANCHOR_DETECTION_LATENCY, now - prev_check
            )
            self._invalid = True
            return False

        if current_inode != self._inode:
            _metric_counter_inc(_ROOT_ANCHOR_LAZY_DETECTION)
            _metric_histogram_observe(
                _ROOT_ANCHOR_DETECTION_LATENCY, now - prev_check
            )
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
