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


# ---------------------------------------------------------------------------
# Prometheus metrics tests
# ---------------------------------------------------------------------------

pytestmark_metrics = pytest.mark.skipif(
    not hasattr(__import__("fava.core.root_anchor", fromlist=["_PROMETHEUS_AVAILABLE"]),
                 "_PROMETHEUS_AVAILABLE")
    or __import__("fava.core.root_anchor", fromlist=["_PROMETHEUS_AVAILABLE"])._PROMETHEUS_AVAILABLE is False,
    reason="prometheus_client not installed",
)


def _counter_value(counter: object) -> float:
    """Read the current numeric value of a prometheus_client Counter."""
    return float(counter._value.get())  # type: ignore[attr-defined]


def _histogram_stats(histogram: object) -> tuple[float, int]:
    """Return (sum, count) of a prometheus_client Histogram.

    Uses ``collect()`` so that we don't depend on internal attribute
    names which vary between prometheus_client versions.
    """
    sum_val = 0.0
    count_val = 0
    for metric in histogram.collect():  # type: ignore[attr-defined]
        for sample in metric.samples:
            if sample.name.endswith("_sum"):
                sum_val += float(sample.value)
            elif sample.name.endswith("_count"):
                count_val += int(sample.value)
    return sum_val, count_val


def test_metric_lazy_fallback_counter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """use_watcher=False / watchfiles unavailable -> increments lazy_fallback counter."""
    from fava.core import root_anchor as ra_mod

    if not ra_mod._PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    before = _counter_value(ra_mod._ROOT_ANCHOR_LAZY_FALLBACK)

    root = tmp_path / "ledger"
    root.mkdir()

    RootAnchor(root, use_watcher=False)
    assert _counter_value(ra_mod._ROOT_ANCHOR_LAZY_FALLBACK) == before + 1

    RootAnchor(root, use_watcher=False)
    assert _counter_value(ra_mod._ROOT_ANCHOR_LAZY_FALLBACK) == before + 2


def test_metric_lazy_detection_counter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Multiple inode changes detected via lazy poll -> counter increments for each."""
    from fava.core import root_anchor as ra_mod

    if not ra_mod._PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    before_detect = _counter_value(ra_mod._ROOT_ANCHOR_LAZY_DETECTION)
    before_latency_sum, before_latency_count = _histogram_stats(
        ra_mod._ROOT_ANCHOR_DETECTION_LATENCY
    )

    root = tmp_path / "ledger"
    root.mkdir()

    # 1st change: rename
    anchor = RootAnchor(root, check_interval=0.0, use_watcher=False)
    anchor._last_check = 0
    root.rename(tmp_path / "ledger_1")
    assert anchor.check() is False
    detect_after_1 = _counter_value(ra_mod._ROOT_ANCHOR_LAZY_DETECTION)
    assert detect_after_1 == before_detect + 1

    # 2nd change: rebuild root dir with same path (new inode), then refresh, delete + recreate.
    root.mkdir()  # same name but different inode
    anchor.refresh()
    anchor._last_check = 0
    import shutil
    shutil.rmtree(tmp_path / "ledger")
    (tmp_path / "ledger").mkdir()  # yet another new inode
    assert anchor.check() is False
    detect_after_2 = _counter_value(ra_mod._ROOT_ANCHOR_LAZY_DETECTION)
    assert detect_after_2 == before_detect + 2

    # 3rd change: refresh then delete (inode missing).
    anchor.refresh()
    anchor._last_check = 0
    shutil.rmtree(tmp_path / "ledger")
    assert anchor.check() is False
    detect_after_3 = _counter_value(ra_mod._ROOT_ANCHOR_LAZY_DETECTION)
    assert detect_after_3 == before_detect + 3

    # Histogram should have recorded exactly 3 samples.
    after_sum, after_count = _histogram_stats(
        ra_mod._ROOT_ANCHOR_DETECTION_LATENCY
    )
    assert after_count == before_latency_count + 3
    assert after_sum > before_latency_sum


def test_metric_watchdog_start_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_start_watcher raises exception -> watchdog_start_failures + lazy_fallback counters."""
    from fava.core import root_anchor as ra_mod

    if not ra_mod._PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    before_fail = _counter_value(ra_mod._ROOT_ANCHOR_WATCHDOG_START_FAILURES)
    before_fb = _counter_value(ra_mod._ROOT_ANCHOR_LAZY_FALLBACK)

    def _exploding_start(self) -> None:  # noqa: ANN001
        raise RuntimeError("simulated start failure")

    monkeypatch.setattr(
        ra_mod._RootWatchThread, "start", _exploding_start
    )

    root = tmp_path / "ledger"
    root.mkdir()
    anchor = RootAnchor(root, use_watcher=True)

    after_fail = _counter_value(ra_mod._ROOT_ANCHOR_WATCHDOG_START_FAILURES)
    after_fb = _counter_value(ra_mod._ROOT_ANCHOR_LAZY_FALLBACK)

    assert after_fail == before_fail + 1
    assert after_fb == before_fb + 1
    # Even though use_watcher=True, watcher is None due to start failure.
    assert anchor._watcher is None
    # Lazy path should still work.
    anchor._last_check = 0
    root.rename(tmp_path / "ledger_old")
    assert anchor.check() is False


def test_metric_detection_latency_histogram_watcher(
    tmp_path: Path,
) -> None:
    """Watchdog-callback path -> latency histogram samples recorded."""
    from fava.core import root_anchor as ra_mod

    if not ra_mod._PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")
    if not ra_mod._WATCHFILES_AVAILABLE:
        pytest.skip("watchfiles not available")

    before_sum, before_count = _histogram_stats(
        ra_mod._ROOT_ANCHOR_DETECTION_LATENCY
    )

    root = tmp_path / "ledger"
    root.mkdir()

    anchor = RootAnchor(root, check_interval=60.0, use_watcher=True)
    assert anchor.wait_watcher_started(timeout=3.0)
    time.sleep(0.15)  # arm the watcher

    # First rename.
    root.rename(tmp_path / "ledger_old")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and not anchor.invalid:
        time.sleep(0.05)
    assert anchor.invalid is True

    # Refresh and do a second rename for multi-sample check.
    (tmp_path / "ledger").mkdir()
    anchor.refresh()
    assert anchor.wait_watcher_started(timeout=3.0)
    time.sleep(0.15)

    (tmp_path / "ledger").rename(tmp_path / "ledger_2")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and not anchor.invalid:
        time.sleep(0.05)
    assert anchor.invalid is True

    after_sum, after_count = _histogram_stats(
        ra_mod._ROOT_ANCHOR_DETECTION_LATENCY
    )
    assert after_count >= before_count + 2
    assert after_sum > before_sum

    anchor.close()


def test_prometheus_client_missing_regression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """prometheus_client effectively unavailable -> no errors; RootAnchor still works.

    We do not actually reload the module (which is fragile due to the
    prometheus_client global registry).  Instead, we temporarily
    monkey-patch the module-level flags and helpers into the same
    state they would be in when the optional dependency is absent,
    then exercise every public code path that touches metrics.
    """
    import fava.core.root_anchor as ra_mod

    saved_available = ra_mod._PROMETHEUS_AVAILABLE
    saved_watchdog = ra_mod._ROOT_ANCHOR_WATCHDOG_START_FAILURES
    saved_lazy_fb = ra_mod._ROOT_ANCHOR_LAZY_FALLBACK
    saved_lazy_det = ra_mod._ROOT_ANCHOR_LAZY_DETECTION
    saved_latency = ra_mod._ROOT_ANCHOR_DETECTION_LATENCY

    try:
        # Simulate post-import state when prometheus_client is missing.
        ra_mod._PROMETHEUS_AVAILABLE = False
        ra_mod._ROOT_ANCHOR_WATCHDOG_START_FAILURES = None
        ra_mod._ROOT_ANCHOR_LAZY_FALLBACK = None
        ra_mod._ROOT_ANCHOR_LAZY_DETECTION = None
        ra_mod._ROOT_ANCHOR_DETECTION_LATENCY = None

        # Safe helpers should be no-ops, no exceptions.
        ra_mod._metric_counter_inc(None)
        ra_mod._metric_histogram_observe(None, 1.23)
        # Safe helpers with non-None fake objects:
        class _Fake:
            def inc(self):  # noqa: ANN202
                pass

            def observe(self, _v):  # noqa: ANN001, ANN202
                pass

        ra_mod._metric_counter_inc(_Fake())
        ra_mod._metric_histogram_observe(_Fake(), 1.23)

        # Full RootAnchor construction + operation must not raise
        # through any metrics touch point.
        root = tmp_path / "ledger_no_prom"
        root.mkdir()
        anchor = ra_mod.RootAnchor(root, check_interval=0.0, use_watcher=False)
        assert anchor.check() is True
        # Force a lazy-poll detection path.
        root.rename(tmp_path / "ledger_no_prom_old")
        assert anchor.check() is False
        assert anchor.invalid is True

        # Force a verification-from-watcher callback path too.
        (tmp_path / "ledger_no_prom").mkdir()
        anchor.refresh()
        # Direct call to _verify_inode (the watcher callback).
        root_dir_again = tmp_path / "ledger_no_prom"
        root_dir_again.rename(tmp_path / "ledger_no_prom_v2")
        assert anchor._verify_inode() is False

        # Simulate _start_watcher exception path with metrics=None.
        class _ExplodingThread:
            def start(self) -> None:
                raise RuntimeError("boom")

        def _fake_start_watcher() -> None:
            with anchor._watcher_lock:
                anchor._watcher = _ExplodingThread()
                anchor._watcher.start()

        anchor._start_watcher = _fake_start_watcher  # type: ignore[method-assign]
        # Re-run __init__'s watcher branch manually via a fresh
        # construction with an already-failing start; however since
        # start is only called inside __init__ we use use_watcher=True
        # and make _start_watcher fail via the class-level patch.
        monkeypatch.setattr(
            ra_mod._RootWatchThread,
            "start",
            lambda self_: (_ for _ in ()).throw(RuntimeError("simulated")),
        )
        # Should not raise -- the exception is swallowed internally.
        root2 = tmp_path / "ledger_no_prom_2"
        root2.mkdir()
        anchor2 = ra_mod.RootAnchor(root2, use_watcher=True)
        assert anchor2._watcher is None  # cleared after failure.
    finally:
        ra_mod._PROMETHEUS_AVAILABLE = saved_available
        ra_mod._ROOT_ANCHOR_WATCHDOG_START_FAILURES = saved_watchdog
        ra_mod._ROOT_ANCHOR_LAZY_FALLBACK = saved_lazy_fb
        ra_mod._ROOT_ANCHOR_LAZY_DETECTION = saved_lazy_det
        ra_mod._ROOT_ANCHOR_DETECTION_LATENCY = saved_latency

    # After restoration: instantiate once more (live prom) to make sure
    # we didn't break the real metric objects.
    root3 = tmp_path / "ledger_after_restore"
    root3.mkdir()
    anchor3 = ra_mod.RootAnchor(root3, check_interval=0.0, use_watcher=False)
    assert anchor3.check() is True
    root3.rename(tmp_path / "ledger_after_restore_old")
    assert anchor3.check() is False
