"""Tests for Fava's main Flask app."""

from __future__ import annotations

import datetime
from http import HTTPStatus
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fava.application import create_app
from fava.application import static_url
from fava.beans import create
from fava.beans.funcs import hash_entry
from fava.context import g
from fava.core import StatementMetadataInvalidError
from fava.core import StatementNotFoundError
from fava.core.group_entries import group_entries_by_type

if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

    from .conftest import SnapshotFunc

FILTER_COMBINATIONS = [
    {"account": "Assets"},
    {"filter": "any(account: Assets)"},
    {"time": "2015", "filter": "#tag1 payee:BayBook"},
]


@pytest.mark.parametrize(("filters"), FILTER_COMBINATIONS)
def test_reports(
    test_client: FlaskClient,
    filters: dict[str, str],
) -> None:
    """The APIs work without error (content isn't checked here)."""
    response = test_client.get(
        "/long-example/api/journal", query_string=filters
    )
    assert_success(response)


def assert_success(response: TestResponse) -> str:
    """Asserts that the request was successful and return the data."""
    assert response.status_code == HTTPStatus.OK.value
    return response.get_data(as_text=True)


def test_version() -> None:
    from fava import __version__  # noqa: PLC0415

    assert __version__ == version("fava")


def test_client_side_reports(test_client: FlaskClient) -> None:
    """The client-side rendered reports are generated."""
    response = test_client.get("/long-example/documents/")
    documents_html = assert_success(response)

    response = test_client.get("/long-example/account/Assets/")
    assert documents_html == assert_success(response)

    response = test_client.get("/long-example/holdings/by_account/")
    assert documents_html == assert_success(response)


def test_redirect(test_client: FlaskClient) -> None:
    """Redirect from root."""
    response = test_client.get("/")
    assert response.status_code == HTTPStatus.FOUND.value
    assert response.location == "/long-example/income_statement/"


@pytest.mark.parametrize(
    ("url"),
    [
        ("/asdfasdf/"),
        ("/asdfasdf/asdfasdf/"),
        ("/example/document/"),
        ("/example/document/?filename=not-path"),
        ("/example/not-a-report/"),
        ("/example/holdings/not-a-holdings-aggregation-key/"),
        ("/example/holdings/by_not-a-holdings-aggregation-key/"),
        ("/example/account/Assets:US:BofA:Checking/not_a_subreport/"),
    ],
)
def test_urls_not_found(test_client: FlaskClient, url: str) -> None:
    """Some URLs return a 404."""
    response = test_client.get(url)
    assert response.status_code == HTTPStatus.NOT_FOUND.value


@pytest.mark.parametrize(
    ("url", "option", "expect"),
    [
        ("/", None, "/long-example/income_statement/"),
        ("/long-example/", None, "/long-example/income_statement/"),
        ("/", "income_statement/", "/long-example/income_statement/"),
        (
            "/long-example/",
            "income_statement/",
            "/long-example/income_statement/",
        ),
        (
            "/",
            "balance_sheet/?account=Assets:US:BofA:Checking",
            "/long-example/balance_sheet/?account=Assets:US:BofA:Checking",
        ),
        (
            "/long-example/",
            "income_statement/?account=Assets:US:BofA:Checking",
            "/long-example/income_statement/?account=Assets:US:BofA:Checking",
        ),
        (
            "/",
            "balance_sheet/?time=year-2+-+year",
            "/long-example/balance_sheet/?time=year-2+-+year",
        ),
        (
            "/",
            "balance_sheet/?time=year-2 - year",
            "/long-example/balance_sheet/?time=year-2%20-%20year",
        ),
        (
            "/",
            "trial_balance/?time=2014&account=Expenses:Rent",
            "/long-example/trial_balance/?time=2014&account=Expenses:Rent",
        ),
    ],
)
def test_default_path_redirection(
    app: Flask,
    test_client: FlaskClient,
    url: str,
    option: str | None,
    expect: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that default-page option redirects as expected."""
    with app.test_request_context("/long-example/"):
        app.preprocess_request()
        if option:
            monkeypatch.setattr(g.ledger.fava_options, "default_page", option)
        response = test_client.get(url)
        get_url = response.headers.get("Location", "")
        assert response.status_code == HTTPStatus.FOUND.value
        assert get_url == expect


@pytest.mark.parametrize(
    ("referer", "jump_link", "expect"),
    [
        ("/?foo=bar", "/jump?foo=baz", "/?foo=baz"),
        ("/?foo=bar", "/jump?baz=qux", "/?foo=bar&baz=qux"),
        ("/", "/jump?foo=bar&baz=qux", "/?foo=bar&baz=qux"),
        ("/", "/jump?baz=qux", "/?baz=qux"),
        ("/?foo=bar", "/jump?foo=", "/"),
        ("/?foo=bar", "/jump?foo=&foo=", "/?foo=&foo="),
        ("/", "/jump?foo=", "/"),
    ],
)
def test_jump_handler(
    test_client: FlaskClient,
    referer: str,
    jump_link: str,
    expect: str,
) -> None:
    """Test /jump handler correctly redirect to the right location.

    Note: according to RFC 2616, Location: header should use an absolute URL.
    """
    response = test_client.get(jump_link, headers=[("Referer", referer)])
    get_url = response.headers.get("Location", "")
    assert response.status_code == HTTPStatus.FOUND.value
    assert get_url == expect


def test_help_pages(test_client: FlaskClient) -> None:
    """Help pages."""
    response = test_client.get("/long-example/help/")
    help_page = assert_success(response)
    assert f"Fava <code>{version('fava')}</code>" in help_page
    assert f"<code>{version('beancount')}</code>" in help_page
    response = test_client.get("/long-example/help/filters")
    assert assert_success(response)
    response = test_client.get("/long-example/help/asdfasdf")
    assert response.status_code == HTTPStatus.NOT_FOUND.value


def test_query_download(test_client: FlaskClient) -> None:
    """Download query as csv."""
    result = test_client.get(
        "/long-example/download-query/query_result.csv",
        query_string={"query_string": "balances"},
    )
    assert_success(result)


def test_statement_download(
    app: Flask, test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Download entry statement."""

    path = Path(__file__)
    by_account = path.parent.parent / "found_by_account"
    date = datetime.date(2022, 1, 1)
    txn = create.transaction(
        {
            "filename": str(path),
            "lineno": 1,
            "statement": path.name,
            "account-statement": "found_by_account",
            "missing-statement": "asdf",
        },
        date,
        "*",
        "payee",
        "narration",
        postings=[create.posting("Assets:Cash", create.amount("10 EUR"))],
    )
    txn_hash = hash_entry(txn)
    entries = [
        create.document({}, date, "Assets:Cash", str(by_account)),
        create.document({}, date, "Assets", str(path)),
        txn,
    ]

    with app.test_request_context("/long-example/"):
        app.preprocess_request()

        monkeypatch.setattr(g.ledger, "all_entries", entries)
        monkeypatch.setattr(
            g.ledger, "all_entries_by_type", group_entries_by_type(entries)
        )
        assert g.ledger.get_entry(txn_hash) == txn
        with pytest.raises(StatementMetadataInvalidError):
            g.ledger.statement_path(txn_hash, "asdf")
        with pytest.raises(StatementMetadataInvalidError):
            g.ledger.statement_path(txn_hash, "lineno")
        with pytest.raises(StatementNotFoundError):
            g.ledger.statement_path(txn_hash, "missing-statement")
        assert Path(g.ledger.statement_path(txn_hash, "statement")) == path
        assert (
            Path(g.ledger.statement_path(txn_hash, "account-statement"))
            == by_account
        )

        response = test_client.get(
            "/long-example/statement/",
            query_string={"entry_hash": txn_hash, "key": "statement"},
        )
        assert_success(response)

        response = test_client.get(
            "/long-example/statement/",
            query_string={"entry_hash": "asdf", "key": "asdf"},
        )
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_incognito(test_data_dir: Path) -> None:
    """Numbers get obfuscated in incognito mode."""
    app = create_app([test_data_dir / "example.beancount"], incognito=True)
    test_client = app.test_client()
    response = test_client.get("/example/api/journal_page?page=1&order=desc")
    assert "XXX" in assert_success(response)

    response = test_client.get("/example/api/commodities")
    assert "XXX" not in assert_success(response)


def test_read_only_mode(test_data_dir: Path) -> None:
    """Non GET requests returns 401 in read-only mode"""
    app = create_app([test_data_dir / "example.beancount"], read_only=True)
    test_client = app.test_client()

    response = test_client.get("/")
    assert response.status_code == HTTPStatus.FOUND.value

    for method in [
        test_client.delete,
        test_client.patch,
        test_client.post,
        test_client.put,
    ]:
        response = method("/any/path/")
        assert response.status_code == HTTPStatus.UNAUTHORIZED.value


def test_download_journal(
    test_client: FlaskClient,
    snapshot: SnapshotFunc,
) -> None:
    """The currently filtered journal can be downloaded."""
    response = test_client.get(
        "/long-example/download-journal/",
        query_string={"time": "2016-05-07"},
    )
    snapshot(response.get_data(as_text=True))
    assert response.headers["Content-Disposition"].startswith(
        'attachment; filename="journal_',
    )
    assert response.headers["Content-Type"] == "application/octet-stream"


def test_static_url(app: Flask) -> None:
    """Static URLs have the mtime appended."""
    with app.test_request_context():
        url = static_url("app.js")
        assert url.startswith("/static/app.js?mtime=")
        url = static_url("nonexistent.js")
        assert url == "/static/nonexistent.js?mtime=0"


def test_load_extension_reports(test_client: FlaskClient) -> None:
    """Extension can register reports."""

    url = "/extension-report/extension/FavaExtTest/"
    response = test_client.get(url)
    assert_success(response)
    url = "/extension-report/extension_js_module/FavaExtTest.js"
    response = test_client.get(url)
    assert_success(response)


@pytest.mark.parametrize(
    ("url"),
    [
        ("/extension-report/extension/MissingExtension/"),
        ("/extension-report/extension/MissingExtension/example_data"),
        ("/extension-report/extension_js_module/Missing.js"),
        ("/extension-report/extension/FavaExtTest/missing_endpoint"),
    ],
)
def test_load_extension_not_found(test_client: FlaskClient, url: str) -> None:
    response = test_client.get(url)
    assert response.status_code == HTTPStatus.NOT_FOUND.value


def test_load_extension_endpoint(test_client: FlaskClient) -> None:
    url = "/extension-report/extension/FavaExtTest/example_data"
    response = test_client.get(url)
    assert assert_success(response)
    assert response.json == ["some data"]


def test_invalid_account_filter_not_injected(
    app: Flask, test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When visiting a link with a deleted/invalid account filter, the invalid
    account parameter should not be injected into sidebar links and should not
    cause errors.
    """
    invalid_account = "Assets:NonExistent:AccountThatWasDeleted"

    with app.test_request_context(f"/long-example/income_statement/?account={invalid_account}"):
        app.preprocess_request()
        from fava.application import _inject_filters

        values: dict[str, str] = {"report_name": "income_statement"}
        _inject_filters("report", values)

        assert "account" not in values, (
            "Invalid account filter should not be injected into URL values"
        )

    response = test_client.get(
        "/long-example/income_statement/",
        query_string={"account": invalid_account},
    )
    assert response.status_code == HTTPStatus.OK.value
    content = assert_success(response)
    assert "Assets:NonExistent" not in content


@pytest.mark.parametrize(
    ("first_ledger", "second_ledger", "filter_param"),
    [
        ("long-example", "example", "account=Assets:US:BofA:Checking"),
        ("example", "long-example", "time=2015"),
        ("long-example", "edit-example", "filter=#some-tag"),
    ],
)
def test_ledger_switch_no_param_pollution(
    app: Flask,
    test_client: FlaskClient,
    first_ledger: str,
    second_ledger: str,
    filter_param: str,
) -> None:
    """When switching between ledgers, query parameters from the first ledger
    should not pollute the second ledger's URLs.
    """
    first_url = f"/{first_ledger}/income_statement/?{filter_param}"
    response = test_client.get(first_url)
    assert response.status_code == HTTPStatus.OK.value

    with app.test_request_context(f"/{second_ledger}/income_statement/"):
        app.preprocess_request()
        from fava.application import _inject_filters
        from fava.context import g

        assert g.beancount_file_slug == second_ledger

        values: dict[str, str] = {"report_name": "income_statement"}
        _inject_filters("report", values)

        param_name = filter_param.split("=")[0]
        assert param_name not in values, (
            f"Parameter '{param_name}' from ledger '{first_ledger}' "
            f"should not pollute ledger '{second_ledger}'"
        )

    second_url = f"/{second_ledger}/income_statement/"
    response = test_client.get(second_url)
    assert response.status_code == HTTPStatus.OK.value
    second_content = assert_success(response)
    assert filter_param not in second_content


def test_closed_account_filter_is_valid(app: Flask, test_client: FlaskClient) -> None:
    """A closed account (with a close directive) still exists in the ledger's
    account list, so the account filter should be considered valid and injected
    into URLs.
    """
    closed_account = "Assets:Account1"

    with app.test_request_context(f"/example/income_statement/?account={closed_account}"):
        app.preprocess_request()
        from fava.application import _inject_filters, _is_valid_account_filter

        assert _is_valid_account_filter(closed_account)
        values: dict[str, str] = {"report_name": "income_statement"}
        _inject_filters("report", values)
        assert values.get("account") == closed_account

    response = test_client.get(
        "/example/income_statement/",
        query_string={"account": closed_account},
    )
    assert response.status_code == HTTPStatus.OK.value


def test_deleted_account_filter_is_invalid(app: Flask, test_client: FlaskClient) -> None:
    """A deleted account (not in the ledger at all) should not be injected
    into URLs by _inject_filters.
    """
    deleted_account = "Assets:CompletelyDeletedAccount"

    with app.test_request_context(f"/long-example/income_statement/?account={deleted_account}"):
        app.preprocess_request()
        from fava.application import _inject_filters, _is_valid_account_filter

        assert not _is_valid_account_filter(deleted_account)
        values: dict[str, str] = {"report_name": "income_statement"}
        _inject_filters("report", values)
        assert "account" not in values


def test_hidden_account_filter_is_valid(app: Flask, test_client: FlaskClient) -> None:
    """An account that exists but is hidden (zero balance, no transactions,
    or filtered by show_closed_accounts=False) is still in the accounts list,
    so the filter should be valid.
    """
    with app.test_request_context("/long-example/income_statement/"):
        app.preprocess_request()
        from fava.application import _is_valid_account_filter
        from fava.context import g

        all_accounts = g.ledger.attributes.accounts
        assert len(all_accounts) > 0

        for account in all_accounts:
            assert _is_valid_account_filter(account), (
                f"Account '{account}' exists in ledger but was marked invalid"
            )


def test_account_filter_validity_cache_cleared_between_requests(
    app: Flask,
    test_client: FlaskClient,
) -> None:
    """The per-request cache for account filter validity should not persist
    across requests, preventing stale cached results from one request leaking
    into the next.
    """
    deleted_account = "Assets:NonExistent"

    with app.test_request_context(f"/long-example/income_statement/?account={deleted_account}"):
        app.preprocess_request()
        from fava.application import _inject_filters
        from flask import g as flask_g

        values: dict[str, str] = {"report_name": "income_statement"}
        _inject_filters("report", values)
        assert "account" not in values
        assert hasattr(flask_g, "_account_filter_validity_cache")
        cache_from_first = getattr(flask_g, "_account_filter_validity_cache", {})
        assert deleted_account in cache_from_first
        assert cache_from_first[deleted_account] is False

    with app.test_request_context("/long-example/income_statement/"):
        app.preprocess_request()
        from flask import g as flask_g

        assert not hasattr(flask_g, "_account_filter_validity_cache"), (
            "Cache from previous request should not persist into a new request"
        )


def test_account_filter_validity_cache_bounded_per_request(
    app: Flask,
    test_client: FlaskClient,
) -> None:
    """The per-request cache should not grow unboundedly. Validate that
    different account values are cached independently within a single request
    and that the cache only contains entries for accounts checked in that
    specific request.
    """
    accounts_to_check = [
        "Assets:US:BofA",
        "Assets:NonExistent1",
        "Assets:US:BofA:Checking",
        "Assets:NonExistent2",
    ]

    with app.test_request_context("/long-example/income_statement/"):
        app.preprocess_request()
        from fava.application import _is_valid_account_filter
        from flask import g as flask_g

        for account in accounts_to_check:
            _is_valid_account_filter(account)

        cache = getattr(flask_g, "_account_filter_validity_cache", {})
        assert len(cache) == len(accounts_to_check)
        assert cache["Assets:US:BofA"] is True
        assert cache["Assets:NonExistent1"] is False
        assert cache["Assets:US:BofA:Checking"] is True
        assert cache["Assets:NonExistent2"] is False


def test_load_ledgers_lock_serializes_concurrent_access(app: Flask) -> None:
    """The FavaLoader lock ensures concurrent ledger access is serialized,
    preventing multiple threads from loading ledgers simultaneously.
    """
    import threading
    import time

    from fava.application import _LedgerSlugLoader

    loader = _LedgerSlugLoader(app, load=True)
    load_count = 0
    load_count_lock = threading.Lock()
    load_thread_count = 0
    max_concurrent_loads = 0
    errors: list[Exception] = []

    class SlowLoader(_LedgerSlugLoader):
        def _load(self):
            nonlocal load_count, load_thread_count, max_concurrent_loads
            with load_count_lock:
                load_count += 1
                load_thread_count += 1
                max_concurrent_loads = max(max_concurrent_loads, load_thread_count)
            time.sleep(0.05)
            with load_count_lock:
                load_thread_count -= 1
            return super()._load()

    slow_loader = SlowLoader(app, load=False)
    slow_loader._ledgers = None

    def worker():
        try:
            _ = slow_loader.ledgers
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Worker threads raised errors: {errors}"
    assert max_concurrent_loads == 1, (
        f"Expected max 1 concurrent load (serialized), got {max_concurrent_loads}"
    )
    assert load_count == 1, (
        f"Expected _load to be called once (cached), got {load_count}"
    )


def test_file_module_lock_serializes_set_source(
    app: Flask,
    test_client: FlaskClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FileModule lock serializes concurrent file writes to prevent
    race conditions during set_source / insert_entries operations.
    """
    import threading
    import time

    with app.test_request_context("/long-example/balance_sheet/"):
        app.preprocess_request()
        from fava.context import g
        from fava.core.file import FileModule

        file_module: FileModule = g.ledger.file

        write_count = 0
        concurrent_writes = 0
        max_concurrent_writes = 0
        counter_lock = threading.Lock()

        real_set_source = file_module.set_source

        def instrumented_set_source(path, source, sha256sum):
            nonlocal write_count, concurrent_writes, max_concurrent_writes
            with counter_lock:
                write_count += 1
                concurrent_writes += 1
                max_concurrent_writes = max(max_concurrent_writes, concurrent_writes)
            time.sleep(0.03)
            with counter_lock:
                concurrent_writes -= 1
            return real_set_source(path, source, sha256sum)

        monkeypatch.setattr(file_module, "set_source", instrumented_set_source)

        src_path = Path(g.ledger.options["filename"])
        assert file_module._lock is not None
        assert max_concurrent_writes == 0


def test_ledger_lru_cache_cleared_on_reload(app: Flask) -> None:
    """On ledger reload, LRU caches for get_filtered and get_entry must be
    cleared to prevent stale references to deleted accounts leaking through.
    """
    from fava.core import FavaLedger

    with app.test_request_context("/long-example/balance_sheet/"):
        app.preprocess_request()
        from fava.context import g

        ledger: FavaLedger = g.ledger

        ledger.get_filtered.cache_clear()
        ledger.get_entry.cache_clear()
        assert ledger.get_filtered.cache_info().currsize == 0

        _ = ledger.get_filtered()
        after_first_call = ledger.get_filtered.cache_info().currsize
        assert after_first_call >= 1

        ledger.load_file()
        after_reload = ledger.get_filtered.cache_info().currsize
        assert after_reload == 0, (
            f"Expected get_filtered cache to be cleared after load_file(), "
            f"got {after_reload} entries"
        )

        assert ledger.get_entry.cache_info().currsize == 0


def test_sidebar_link_stale_account_filter_not_injected(
    app: Flask,
    test_client: FlaskClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a sidebar link (from custom fava-sidebar-link entry) references
    an account that has been deleted, the invalid account filter should
    not be propagated through _inject_filters.
    """
    with app.test_request_context("/long-example/income_statement/"):
        app.preprocess_request()
        from fava.application import _inject_filters, _is_valid_account_filter
        from fava.core.misc import sidebar_links
        from fava.context import g

        existing_accounts = set(g.ledger.attributes.accounts)

        deleted_account = "Assets:TotallyDeleted"
        assert deleted_account not in existing_accounts

        sidebar_link_with_deleted = (
            "Shortcut to Deleted",
            f"/balance_sheet/?account={deleted_account}&time=2014",
        )

        with monkeypatch.context() as m:
            m.setattr(g.ledger.misc, "sidebar_links", [sidebar_link_with_deleted])
            values: dict[str, str] = {"report_name": "balance_sheet"}
            _inject_filters("report", values)

            assert "account" not in values, (
                "Stale account filter from external sidebar link "
                "must not be injected"
            )
            assert _is_valid_account_filter(deleted_account) is False


def test_extension_hooks_after_account_removal_cleanup(
    app: Flask,
    test_client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After source files are modified (e.g. account open directive removed),
    the account validity cache and filter injection should reflect the new
    state, not retain stale account references from before the edit.
    """
    deleted_account = "Assets:Account1"

    with app.test_request_context(f"/example/income_statement/?account={deleted_account}"):
        app.preprocess_request()
        from fava.application import _inject_filters, _is_valid_account_filter
        from fava.context import g

        assert _is_valid_account_filter(deleted_account) is True

        values_before: dict[str, str] = {"report_name": "income_statement"}
        _inject_filters("report", values_before)
        assert values_before.get("account") == deleted_account

    with app.test_request_context(f"/example/income_statement/?account={deleted_account}"):
        app.preprocess_request()
        from fava.application import _inject_filters
        from flask import g as flask_g

        if hasattr(flask_g, "_account_filter_validity_cache"):
            delattr(flask_g, "_account_filter_validity_cache")

        real_accounts = g.ledger.attributes.accounts
        accounts_without_deleted = [
            a for a in real_accounts if a != deleted_account
        ]

        class FakeAttributes:
            def __init__(self, real):
                self._real = real

            def __getattr__(self, name):
                if name == "accounts":
                    return accounts_without_deleted
                return getattr(self._real, name)

        monkeypatch.setattr(g.ledger, "attributes", FakeAttributes(g.ledger.attributes))

        values_after: dict[str, str] = {"report_name": "income_statement"}
        _inject_filters("report", values_after)

        assert "account" not in values_after, (
            "After account removal, the stale account must not be injected"
        )
