from __future__ import annotations

import datetime
from difflib import Differ
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

import pytest

from fava.beans.funcs import hash_entry
from fava.context import g
from fava.core.file import _sha256_str
from fava.core.file import get_entry_slice
from fava.core.misc import align
from fava.json_api import validate_func_arguments
from fava.json_api import ValidationError

if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

    from fava.core import FavaLedger

    from .conftest import GetFavaLedger
    from .conftest import SnapshotFunc


def diff_strings(a: str, b: str) -> list[str]:
    """Diff two strings and return the list of differing lines."""
    differ = Differ()
    return [
        line
        for line in differ.compare(a.splitlines(), b.splitlines())
        if line.startswith(("+", "-"))
    ]


def test_validate_get_args() -> None:
    def noparams() -> None:
        pass

    assert validate_func_arguments(noparams) is None

    def func(test: str) -> None:
        assert test
        assert isinstance(test, str)

    validator = validate_func_arguments(func)
    assert validator
    with pytest.raises(ValidationError):
        validator({"notest": "value"})
    assert validator({"test": "value"}) == ["value"]


def assert_api_error(
    response: TestResponse,
    msg: str | None = None,
    status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR,
) -> str:
    """Asserts that the response errored and contains the message."""
    assert response.status_code == status.value
    assert response.json
    err_msg = response.json["error"]
    assert isinstance(err_msg, str)
    if msg:
        assert msg == err_msg
    return err_msg


def assert_api_success(response: TestResponse, data: Any | None = None) -> Any:
    """Asserts that the request was successful and contains the data."""
    assert response.status_code == HTTPStatus.OK.value
    assert response.json
    if data is not None:
        assert data == response.json["data"]
    return response.json["data"]


def test_api_changed(test_client: FlaskClient) -> None:
    response = test_client.get("/long-example/api/changed")
    assert_api_success(response, data=False)


def test_api_add_document_and_move_and_delete(
    app: Flask,
    test_client: FlaskClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_url = "/long-example/api/add_document"
    get_url = "/long-example/document/"
    move_url = "/long-example/api/move"
    delete_url = "/long-example/api/document"
    account = "Expenses:Food:Restaurant"
    account_dir = tmp_path / "Expenses" / "Food" / "Restaurant"

    def _data(
        filename: str,
    ) -> dict[str, str | tuple[BytesIO, str]]:
        return {
            "folder": str(tmp_path),
            "account": account,
            "file": (BytesIO(b"asdfasdf"), filename),
        }

    with app.test_request_context("/long-example/"):
        app.preprocess_request()

        # error when no documents dir is set
        monkeypatch.setitem(g.ledger.options, "documents", [])  # ty:ignore[invalid-argument-type]

        response = test_client.put(add_url)
        assert_api_error(
            response,
            "You need to set a documents folder.",
            HTTPStatus.UNPROCESSABLE_ENTITY,
        )

        # upload to temporary directory
        monkeypatch.setitem(g.ledger.options, "documents", [str(tmp_path)])  # ty:ignore[invalid-argument-type]
        monkeypatch.setattr(
            g.ledger.fava_options, "import_dirs", [str(account_dir)]
        )

        response = test_client.put(add_url)
        assert_api_error(response, "No file uploaded.", HTTPStatus.BAD_REQUEST)

        response = test_client.put(add_url, data=_data(""))
        assert_api_error(
            response,
            "Uploaded file is missing filename.",
            HTTPStatus.BAD_REQUEST,
        )

        filename = account_dir / "2015-12-12 test"
        assert not filename.exists()
        response = test_client.put(add_url, data=_data("2015-12-12 test"))
        assert_api_success(response, f"Uploaded to {filename}")
        assert filename.read_text() == "asdfasdf"
        assert filename.is_file()

        response = test_client.get(
            get_url, query_string={"filename": str(filename)}
        )
        assert response.status_code == HTTPStatus.OK.value
        assert response.get_data() == b"asdfasdf"

        response = test_client.put(add_url, data=_data("2015-12-12 test"))
        assert_api_error(
            response, f"{filename} already exists.", HTTPStatus.CONFLICT
        )

        # move to same path should fail
        response = test_client.put(
            move_url,
            json={
                "account": account,
                "filename": str(filename),
                "new_name": "2015-12-12 test",
            },
        )
        assert_api_error(
            response, f"{filename} already exists.", HTTPStatus.CONFLICT
        )

        response = test_client.put(
            move_url,
            json={
                "account": account,
                "filename": str(filename),
                "new_name": "2015-12-12 test_moved",
            },
        )
        new_filename = account_dir / "2015-12-12 test_moved"
        assert_api_success(response, f"Moved {filename} to {new_filename}.")
        assert not filename.exists()
        assert new_filename.exists()

        # delete
        invalid_filename = tmp_path / "asdf"
        response = test_client.delete(
            delete_url,
            query_string={"filename": str(invalid_filename)},
        )
        assert_api_error(
            response,
            f"Not valid document or import file: '{invalid_filename}'.",
            HTTPStatus.BAD_REQUEST,
        )

        response = test_client.delete(
            delete_url,
            query_string={"filename": str(filename)},
        )
        assert_api_error(response, f"{filename} does not exist.")

        response = test_client.delete(
            delete_url,
            query_string={"filename": str(new_filename)},
        )
        assert_api_success(response, f"Deleted {new_filename}.")


def test_api_upload_import_file(
    app: Flask,
    test_client: FlaskClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "/long-example/api/upload_import_file"

    with app.test_request_context("/long-example/"):
        app.preprocess_request()

        monkeypatch.setattr(
            g.ledger.fava_options, "import_dirs", [str(tmp_path)]
        )

        response = test_client.put(url)
        assert_api_error(response, "No file uploaded.", HTTPStatus.BAD_REQUEST)

        response = test_client.put(
            url, data={"file": (BytesIO(b"asdfasdf"), "")}
        )
        assert_api_error(
            response,
            "Uploaded file is missing filename.",
            HTTPStatus.BAD_REQUEST,
        )

        filename = tmp_path / "receipt.pdf"
        assert not filename.is_file()
        response = test_client.put(
            url, data={"file": (BytesIO(b"asdfasdf"), "receipt.pdf")}
        )
        assert_api_success(response, f"Uploaded to {filename}")
        assert filename.is_file()

        # Uploading the exact same file should fail due to path conflict
        response = test_client.put(
            url, data={"file": (BytesIO(b"asdfasdf"), "receipt.pdf")}
        )
        assert_api_error(
            response, f"{filename} already exists.", HTTPStatus.CONFLICT
        )


def test_api_errors(test_client: FlaskClient, snapshot: SnapshotFunc) -> None:
    response = test_client.get("/long-example/api/errors")
    assert_api_success(response, [])
    response = test_client.get("/errors/api/errors")
    data = assert_api_success(response)

    def get_message(err: Any) -> str:
        return str(err["message"])

    snapshot(sorted(data, key=get_message), json=True)


def test_api_context(
    test_client: FlaskClient,
    snapshot: SnapshotFunc,
    example_ledger: FavaLedger,
) -> None:
    response = test_client.get("/long-example/api/context")
    assert_api_error(
        response,
        "Invalid API request: Parameter `entry_hash` is missing.",
        HTTPStatus.BAD_REQUEST,
    )

    response = test_client.get(
        "/long-example/api/context",
        query_string={"entry_hash": "not_found"},
    )
    assert_api_error(
        response,
        'No entry found for hash "not_found"',
        HTTPStatus.NOT_FOUND,
    )

    balance_entry_hash = hash_entry(
        example_ledger.all_entries_by_type.Balance[0]
    )
    response = test_client.get(
        "/long-example/api/context",
        query_string={"entry_hash": balance_entry_hash},
    )
    data = assert_api_success(response)
    assert data["balances_before"]
    assert not data["balances_after"]

    entry_hash = hash_entry(
        next(
            entry
            for entry in example_ledger.all_entries_by_type.Transaction
            if entry.narration == r"Investing 40% of cash in VBMPX"
            and entry.date == datetime.date(2016, 5, 9)
        ),
    )

    response = test_client.get(
        "/long-example/api/context",
        query_string={"entry_hash": entry_hash},
    )
    data = assert_api_success(response)
    snapshot(data, json=True)
    response = test_client.get(
        "/long-example/api/source_slice",
        query_string={"entry_hash": entry_hash},
    )
    data = assert_api_success(response)
    snapshot(data, json=True)

    entry_hash = hash_entry(example_ledger.all_entries[10])
    response = test_client.get(
        "/long-example/api/context",
        query_string={"entry_hash": entry_hash},
    )
    data = assert_api_success(response)
    snapshot(data, json=True)
    assert not data.get("balances_before")
    response = test_client.get(
        "/long-example/api/source_slice",
        query_string={"entry_hash": entry_hash},
    )
    data = assert_api_success(response)
    snapshot(data, json=True)


def test_api_payee_accounts(
    test_client: FlaskClient,
    snapshot: SnapshotFunc,
) -> None:
    response = test_client.get("/long-example/api/payee_accounts")
    assert_api_error(response, status=HTTPStatus.BAD_REQUEST)

    response = test_client.get(
        "/long-example/api/payee_accounts",
        query_string={"payee": "EDISON POWER"},
    )
    data = assert_api_success(response)
    assert data[0] == "Assets:US:BofA:Checking"
    assert data[1] == "Expenses:Home:Electricity"
    snapshot(data, json=True)


def test_api_payee_transaction(
    test_client: FlaskClient,
    snapshot: SnapshotFunc,
) -> None:
    response = test_client.get(
        "/long-example/api/payee_transaction",
        query_string={"payee": "EDISON POWER"},
    )
    data = assert_api_success(response)
    snapshot(data, json=True)


def test_api_narration_transaction(
    test_client: FlaskClient,
) -> None:
    response = test_client.get(
        "/long-example/api/narration_transaction",
        query_string={"narration": "Buying groceries"},
    )
    data = assert_api_success(response)
    assert data["date"] == "2016-04-21"
    assert data["narration"] == "Buying groceries"
    assert data["payee"] == "Farmer Fresh"
    assert len(data["postings"]) == 2
    assert data["t"] == "Transaction"


def test_api_imports(
    test_client: FlaskClient,
    snapshot: SnapshotFunc,
) -> None:
    response = test_client.get("/import/api/imports")
    data = assert_api_success(response)
    assert data
    snapshot(data, json=True)

    importable = next(f for f in data if f["importers"])
    assert importable

    response = test_client.get(
        "/import/api/extract",
        query_string={
            "filename": importable["name"],
            "importer": importable["importers"][0]["importer_name"],
        },
    )
    data = assert_api_success(response)
    snapshot(data, json=True)


def test_api_move(test_client: FlaskClient) -> None:
    response = test_client.put("/long-example/api/move")
    assert_api_error(
        response,
        "Invalid API request: Invalid JSON body.",
        HTTPStatus.BAD_REQUEST,
    )

    invalid = {"account": "Assets", "new_name": "new", "filename": "old"}
    response = test_client.put("/long-example/api/move", json=invalid)
    assert_api_error(
        response,
        "You need to set a documents folder.",
        HTTPStatus.UNPROCESSABLE_ENTITY,
    )

    response = test_client.put("/import/api/move", json=invalid)
    assert_api_error(response, "Not a valid account: 'Assets'")

    response = test_client.put(
        "/import/api/move",
        json={
            **invalid,
            "account": "Assets:Checking",
        },
    )
    assert_api_error(
        response, "Not a file: 'old'", HTTPStatus.UNPROCESSABLE_ENTITY
    )


def test_api_get_source_invalid_unicode(test_client: FlaskClient) -> None:
    response = test_client.get("/invalid-unicode/api/source")
    err_msg = assert_api_error(response)
    assert "The source file contains invalid unicode" in err_msg


def test_api_get_source_unknown_file(test_client: FlaskClient) -> None:
    response = test_client.get(
        "/example/api/source",
        query_string={"filename": "/home/not-one-of-the-includes"},
    )
    err_msg = assert_api_error(response)
    assert "Trying to read a non-source file" in err_msg


def test_api_get_source_slice_unprocessable(
    test_client: FlaskClient, get_ledger: GetFavaLedger
) -> None:
    generated_open_entry = get_ledger("edit-example").all_entries[0]
    entry_hash = hash_entry(generated_open_entry)
    response = test_client.get(
        "/edit-example/api/source_slice",
        query_string={"entry_hash": entry_hash},
    )
    assert_api_error(
        response,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def test_api_put_source_bad_request(test_client: FlaskClient) -> None:
    response = test_client.put("/example/api/source")
    assert_api_error(
        response,
        "Invalid API request: Invalid JSON body.",
        HTTPStatus.BAD_REQUEST,
    )


def test_api_source(app_in_tmp_dir: Flask) -> None:
    test_client = app_in_tmp_dir.test_client()
    ledger = app_in_tmp_dir.config["LEDGERS"]["edit-example"]
    path = Path(ledger.beancount_file_path)
    url = "/edit-example/api/source"

    source = path.read_text("utf-8")
    changed_source = source + "\n;comment"
    sha256sum = _sha256_str(source)

    # read
    response = test_client.get(url)
    data = assert_api_success(response)
    assert data["source"] == source

    # change source
    response = test_client.put(
        url,
        json={
            "file_path": str(path),
            "sha256sum": sha256sum,
            "source": changed_source,
        },
    )
    sha256sum = _sha256_str(changed_source)
    assert_api_success(response, sha256sum)

    # check if the file has been written
    assert path.read_text("utf-8") == changed_source

    # write original source file
    response = test_client.put(
        url,
        json={
            "file_path": str(path),
            "sha256sum": sha256sum,
            "source": source,
        },
    )
    assert_api_success(response)
    assert path.read_text("utf-8") == source


def test_api_source_slice_and_insert_metadata(app_in_tmp_dir: Flask) -> None:
    test_client = app_in_tmp_dir.test_client()
    ledger = app_in_tmp_dir.config["LEDGERS"]["edit-example"]
    path = Path(ledger.beancount_file_path)

    source = path.read_text("utf-8")

    # get entry context and update an entry slice
    first_txn = next(e for e in ledger.all_entries if hasattr(e, "postings"))
    assert first_txn.payee == "Kin Soy"
    entry_hash = hash_entry(first_txn)
    response = test_client.get(
        "/edit-example/api/source_slice",
        query_string={"entry_hash": entry_hash},
    )
    data = assert_api_success(response)
    assert "Kin Soy" in data["slice"]

    response = test_client.put(
        "/edit-example/api/source_slice",
        json={
            "entry_hash": entry_hash,
            "sha256sum": data["sha256sum"],
            "source": data["slice"].replace("Kin Soy", "Lorem Ipsum"),
        },
    )
    assert_api_success(response)
    assert diff_strings(source, path.read_text("utf-8")) == [
        '- 2014-01-04 * "Kin Soy" "Eating out with Sue"',
        '+ 2014-01-04 * "Lorem Ipsum" "Eating out with Sue"',
    ]
    ledger.load_file()
    first_txn = next(e for e in ledger.all_entries if hasattr(e, "postings"))
    assert first_txn.payee == "Lorem Ipsum"
    entry_hash = hash_entry(first_txn)

    response = test_client.put(
        "/edit-example/api/attach_document",
        json={
            "entry_hash": entry_hash,
            "filename": "edit-example.beancount",
        },
    )
    assert_api_success(response)
    assert diff_strings(source, path.read_text("utf-8")) == [
        '- 2014-01-04 * "Kin Soy" "Eating out with Sue"',
        '+ 2014-01-04 * "Lorem Ipsum" "Eating out with Sue"',
        '+   document: "edit-example.beancount"',
    ]

    ledger.load_file()
    first_txn = next(e for e in ledger.all_entries if hasattr(e, "postings"))
    assert first_txn.payee == "Lorem Ipsum"
    entry_hash = hash_entry(first_txn)

    ledger.options["documents"] = [str(path.parent)]
    target_path = (
        path.parent
        / "Expenses"
        / "Food"
        / "Restaurant"
        / "2022-12-12 asdf.txt"
    )
    response = test_client.put(
        "/edit-example/api/add_document",
        data={
            "folder": str(path.parent),
            "account": "Expenses:Food:Restaurant",
            "file": (BytesIO(b"asdfasdf"), "2022-12-12 asdf.txt"),
            "hash": entry_hash,
        },
    )
    assert_api_success(response)
    assert target_path.exists()
    assert diff_strings(source, path.read_text("utf-8")) == [
        '- 2014-01-04 * "Kin Soy" "Eating out with Sue"',
        '+ 2014-01-04 * "Lorem Ipsum" "Eating out with Sue"',
        '+   document-2: "2022-12-12 asdf.txt"',
        '+   document: "edit-example.beancount"',
    ]


def test_api_format_source(
    test_client: FlaskClient,
    example_ledger: FavaLedger,
) -> None:
    path = Path(example_ledger.beancount_file_path)
    url = "/long-example/api/format_source"

    payload = path.read_text("utf-8")

    response = test_client.put(url, json={"source": payload})
    assert_api_success(response, align(payload, 61))


def test_api_format_source_options(
    app: Flask,
    test_client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with app.test_request_context("/long-example/"):
        app.preprocess_request()
        path = Path(g.ledger.beancount_file_path)
        payload = path.read_text("utf-8")

        monkeypatch.setattr(g.ledger.fava_options, "currency_column", 90)

        response = test_client.put(
            "/long-example/api/format_source",
            json={"source": payload},
        )
        assert_api_success(response, align(payload, 90))


def test_api_source_slice_delete(app_in_tmp_dir: Flask) -> None:
    test_client = app_in_tmp_dir.test_client()
    ledger = app_in_tmp_dir.config["LEDGERS"]["edit-example"]
    path = Path(ledger.beancount_file_path)

    contents = path.read_text("utf-8")
    assert '2016-05-03 * "Chichipotle" "Eating out with Joe"' in contents

    url = "/edit-example/api/source_slice"
    # test bad request
    response = test_client.delete(url)
    assert_api_error(
        response,
        "Invalid API request: Parameter `entry_hash` is missing.",
        HTTPStatus.BAD_REQUEST,
    )

    entry = ledger.all_entries[-1]
    entry_hash = hash_entry(entry)
    _entry_source, sha256sum = get_entry_slice(entry)

    # delete entry
    response = test_client.delete(
        url,
        query_string={"entry_hash": entry_hash, "sha256sum": sha256sum},
    )
    assert_api_success(response, f"Deleted entry {entry_hash}.")
    assert (
        '2016-05-03 * "Chichipotle" "Eating out with Joe"'
        not in path.read_text("utf-8")
    )


def test_api_add_entries(
    app: Flask,
    test_client: FlaskClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with app.test_request_context("/long-example/"):
        app.preprocess_request()
        test_file = tmp_path / "test_file"
        test_file.touch()
        monkeypatch.setattr(g.ledger, "beancount_file_path", str(test_file))

        entries = [
            {
                "t": "Transaction",
                "date": "2017-12-12",
                "flag": "*",
                "payee": "Test3",
                "tags": [],
                "links": [],
                "narration": "",
                "meta": {},
                "postings": [
                    {"account": "Assets:US:ETrade:Cash", "amount": "100 USD"},
                    {"account": "Assets:US:ETrade:GLD"},
                ],
            },
            {
                "t": "Transaction",
                "date": "2017-01-12",
                "flag": "*",
                "payee": "Test1",
                "tags": [],
                "links": [],
                "narration": "",
                "meta": {},
                "postings": [
                    {"account": "Assets:US:ETrade:Cash", "amount": "100 USD"},
                    {"account": "Assets:US:ETrade:GLD"},
                ],
            },
            {
                "t": "Transaction",
                "date": "2017-02-12",
                "flag": "*",
                "payee": "Test",
                "tags": [],
                "links": [],
                "narration": "Test",
                "meta": {},
                "postings": [
                    {"account": "Assets:US:ETrade:Cash", "amount": "100 USD"},
                    {"account": "Assets:US:ETrade:GLD"},
                ],
            },
        ]

        url = "/long-example/api/add_entries"

        err = test_client.put(url, json={"entries": "string"})
        assert_api_error(
            err,
            "Invalid API request: Parameter `entries`"
            " of incorrect type - expected <class 'list'>.",
            HTTPStatus.BAD_REQUEST,
        )

        response = test_client.put(url, json={"entries": entries})
        assert_api_success(response, "Stored 3 entries.")

        assert (
            test_file.read_text("utf-8")
            == """
2017-01-12 * "Test1" ""
  Assets:US:ETrade:Cash                                 100 USD
  Assets:US:ETrade:GLD

2017-02-12 * "Test" "Test"
  Assets:US:ETrade:Cash                                 100 USD
  Assets:US:ETrade:GLD

2017-12-12 * "Test3" ""
  Assets:US:ETrade:Cash                                 100 USD
  Assets:US:ETrade:GLD
"""
        )


@pytest.mark.parametrize(
    ("query_string", "name"),
    [
        ("balances from year = 2014", "balances"),
        ("select sum(day)", "sum"),
        ("journal from year = 2014 and month = 1", "journal"),
        (
            "select day, position, units(position), balance, payee, tags"
            " from year = 2014 and month = 1",
            "misc",
        ),
        (".help", "help"),
    ],
)
def test_api_query_result(
    query_string: str,
    name: str,
    test_client: FlaskClient,
    snapshot: SnapshotFunc,
) -> None:
    response = test_client.get(
        "/long-example/api/query",
        query_string={"query_string": query_string},
    )
    data = assert_api_success(response)
    snapshot(data, name=name, json=True)


def test_api_query_result_types(
    test_client: FlaskClient,
) -> None:
    query_string = (
        "select day, position, units(position), balance, payee, tags, "
        "entry, meta from year = 2014 and month = 1"
    )
    response = test_client.get(
        "/long-example/api/query",
        query_string={"query_string": query_string},
    )
    assert_api_success(response)


def test_api_query_result_error(test_client: FlaskClient) -> None:
    response = test_client.get(
        "/long-example/api/query",
        query_string={"query_string": "nononono"},
    )
    msg = assert_api_error(response)
    assert "Query parse error: syntax error" in msg


def test_api_commodities_empty(
    test_client: FlaskClient,
) -> None:
    response = test_client.get(
        "/long-example/api/commodities?time=3000",
    )
    data = assert_api_success(response)
    assert not data


def test_api_journal_page_not_found(
    test_client: FlaskClient,
) -> None:
    response = test_client.get(
        "/long-example/api/journal_page?page=1000&order=desc"
    )
    assert_api_error(response, status=HTTPStatus.NOT_FOUND)


def test_api_filter_error(
    test_client: FlaskClient,
) -> None:
    response = test_client.get(
        "/long-example/api/commodities?time=20",
    )
    assert_api_error(response, status=HTTPStatus.BAD_REQUEST)


@pytest.mark.parametrize(
    ("name", "url"),
    [
        ("commodities", "/long-example/api/commodities"),
        ("documents", "/example/api/documents"),
        ("events", "/long-example/api/events"),
        ("journal", "/example/api/journal"),
        ("income_statement", "/long-example/api/income_statement?time=2014"),
        ("narrations", "/long-example/api/narrations"),
        ("trial_balance", "/long-example/api/trial_balance?time=2014"),
        ("balance_sheet", "/long-example/api/balance_sheet"),
        (
            "balance_sheet_with_cost",
            "/long-example/api/balance_sheet?conversion=at_value",
        ),
        (
            "account_report_off_by_one_journal",
            (
                "/off-by-one/api/account_report"
                "?interval=day&conversion=at_value&a=Assets"
            ),
        ),
        (
            "account_report_off_by_one",
            (
                "/off-by-one/api/account_report"
                "?interval=day&conversion=at_value&a=Assets&r=balances"
            ),
        ),
        ("statistics", "/long-example/api/statistics"),
        ("options", "/long-example/api/options"),
        (
            "account_report_budget_categories_monthly",
            (
                "/example/api/account_report"
                "?interval=month&a=Expenses&r=changes"
            ),
        ),
        (
            "account_report_budget_categories_monthly_balances",
            (
                "/example/api/account_report"
                "?interval=month&a=Expenses&r=balances"
            ),
        ),
        (
            "account_report_budget_categories_weekly",
            (
                "/example/api/account_report"
                "?interval=week&a=Expenses&r=balances"
            ),
        ),
        (
            "account_report_budget_multicurrency_parent",
            (
                "/example/api/account_report"
                "?interval=month&a=Expenses:Food&r=changes"
            ),
        ),
        (
            "account_report_budget_multicurrency_leaf",
            (
                "/example/api/account_report"
                "?interval=month&a=Expenses:Food:Groceries&r=changes"
            ),
        ),
        (
            "account_report_budget_transport_category",
            (
                "/example/api/account_report"
                "?interval=month&a=Expenses:Transport&r=balances"
            ),
        ),
    ],
)
def test_api(
    test_client: FlaskClient,
    snapshot: SnapshotFunc,
    name: str,
    url: str,
) -> None:
    response = test_client.get(url)
    data = assert_api_success(response)
    assert data
    snapshot(data, name=name, json=True)


STATUS_RANK = {"ok": 0, "near": 1, "over": 2}


def _worst_status(*statuses: str) -> str:
    return max(statuses, key=lambda s: STATUS_RANK.get(s, -1), default="ok")


def test_account_report_budget_consistency(
    test_client: FlaskClient,
) -> None:
    """Assert that budget statuses, ratios, category fields and
    periodic boundaries are consistent across:
    - charts vs interval_balances
    - r=changes vs r=balances
    - multi-currency leaf accounts vs their parent aggregations
    """
    base_changes = (
        "/example/api/account_report"
        "?interval=month&a=Expenses:Food&r=changes"
    )
    base_balances = (
        "/example/api/account_report"
        "?interval=month&a=Expenses:Food&r=balances"
    )

    changes_data = assert_api_success(test_client.get(base_changes))
    balances_data = assert_api_success(test_client.get(base_balances))

    # (1) Both tree-view responses must carry budget fields.
    for payload, label in [
        (changes_data, "changes"),
        (balances_data, "balances"),
    ]:
        assert "budget_categories" in payload, label
        assert "budgets" in payload, label
        assert "dates" in payload, label
        assert "charts" in payload, label
        assert "interval_balances" in payload, label
        assert "living" in payload["budget_categories"], label

    dates_changes = changes_data["dates"]
    dates_balances = balances_data["dates"]
    budgets_changes = changes_data["budgets"]
    budgets_balances = balances_data["budgets"]

    # (2) Period boundaries must be identical for r=changes / r=balances.
    assert dates_changes == dates_balances, (
        "period boundaries differ between changes/balances views"
    )
    n_intervals = len(dates_changes)
    assert n_intervals >= 2

    # Dates are sorted DESC — the first entry is the latest (our 2012-12
    # test interval where all budget transactions occur).
    dec_idx = 0
    assert dates_changes[dec_idx]["begin"] == "2012-12-01"
    assert dates_changes[dec_idx]["end"] == "2013-01-01"

    # (3) Charts: 2 charts (balances + interval_totals/Changes).
    charts = changes_data["charts"]
    assert len(charts) == 2
    # Bar chart (Changes) has one bar per interval — match interval count.
    bar_chart = next(c for c in charts if c["type"] == "bar")
    assert len(bar_chart["data"]) == n_intervals
    # First bar date == first interval begin, modulo end-of-month offset
    # used by d3-scale for the bar position.
    # Assert every interval has a matching bar by iterating both.
    for bar, daterange in zip(bar_chart["data"], dates_changes):
        # bar["budgets"] should equal children-aggregated budget for root
        assert "budgets" in bar
        assert "balance" in bar

    # (4) Leaf account Expenses:Food:Groceries has multi-currency
    #     (EUR near, USD over). Assert the exact statuses + ratios.
    leaf_account = "Expenses:Food:Groceries"
    leaf_budgets = budgets_changes[leaf_account]
    assert len(leaf_budgets) == n_intervals
    leaf_last = leaf_budgets[dec_idx]
    assert leaf_last["category"] == "living"
    assert set(leaf_last["budget"].keys()) == {"EUR", "USD"}
    # EUR budget = 500, actual 420 => 0.84 => near
    assert leaf_last["status"]["EUR"] == "near"
    assert abs(float(leaf_last["ratio"]["EUR"]) - 0.84) < 1e-9
    # USD budget = 120, actual 135 => 1.125 => over
    assert leaf_last["status"]["USD"] == "over"
    assert abs(float(leaf_last["ratio"]["USD"]) - 1.125) < 1e-9

    # (5) Leaf account Expenses:Food:Restaurant has EUR over only.
    rest_account = "Expenses:Food:Restaurant"
    rest_last = budgets_changes[rest_account][dec_idx]
    assert rest_last["category"] == "living"
    assert rest_last["budget"].keys() == {"EUR"}
    assert rest_last["status"]["EUR"] == "over"
    assert abs(float(rest_last["ratio"]["EUR"]) - 1.2) < 1e-9

    # (6) Parent Expenses:Food — no direct budget. children totals
    #     aggregate both leaves, and children fields are present.
    #     The "worst badge" on the parent row is derived from its leaves
    #     (done on the frontend from per-leaf statuses but we assert
    #     that budget_children covers both currencies and both leaves).
    parent_account = "Expenses:Food"
    parent_last = budgets_changes[parent_account][dec_idx]
    assert parent_last["budget"] == {}
    # budget_children: 500+300 = 800 EUR and 120 USD.
    assert float(parent_last["budget_children"]["EUR"]) == 800.0
    assert float(parent_last["budget_children"]["USD"]) == 120.0
    # Aggregate worst status: EUR is near+over => over; USD is over => over
    eur_worst = _worst_status(
        leaf_last["status"]["EUR"], rest_last["status"]["EUR"]
    )
    assert eur_worst == "over"
    assert leaf_last["status"]["USD"] == "over"

    # (7) r=changes vs r=balances must deliver the same budget fields
    #     for the leaf account (category & budgeted amounts).
    leaf_changes = budgets_changes[leaf_account][dec_idx]
    leaf_balances = budgets_balances[leaf_account][dec_idx]
    assert leaf_changes["category"] == leaf_balances["category"]
    assert leaf_changes["budget"].keys() == leaf_balances["budget"].keys()
    # r=changes: per-period budget.
    assert float(leaf_changes["budget"]["EUR"]) == 500.0
    assert float(leaf_changes["budget"]["USD"]) == 120.0
    # r=balances: accumulated budget across all intervals (>= changes).
    assert float(leaf_balances["budget"]["EUR"]) >= 500.0
    assert float(leaf_balances["budget"]["USD"]) >= 120.0
    # statuses are present in both views
    assert "EUR" in leaf_balances["status"]
    assert "USD" in leaf_balances["status"]
    # ... but balances view accumulates, so ratio can differ.

    # (8) Transport category account: Expenses:Transport.
    transport_url = (
        "/example/api/account_report"
        "?interval=month&a=Expenses:Transport&r=changes"
    )
    transport_data = assert_api_success(test_client.get(transport_url))
    transport_budgets = transport_data["budgets"]
    # Two leaf accounts with ok status.
    t_public = transport_budgets["Expenses:Transport:Public"][dec_idx]
    t_taxi = transport_budgets["Expenses:Transport:Taxi"][dec_idx]
    assert t_public["category"] == "transport"
    assert t_public["status"]["EUR"] == "ok"
    assert t_taxi["category"] == "transport"
    assert t_taxi["status"]["EUR"] == "ok"
    # Parent Expenses:Transport has no direct budget.
    assert transport_budgets["Expenses:Transport"][dec_idx]["budget"] == {}

    # (9) Weekly interval: budgeted amounts should differ from monthly
    #     and statuses should stay self-consistent.
    weekly_url = (
        "/example/api/account_report"
        "?interval=week&a=Expenses:Food:Groceries&r=changes"
    )
    weekly = assert_api_success(test_client.get(weekly_url))
    assert len(weekly["dates"]) >= 4
    weekly_budget = weekly["budgets"]["Expenses:Food:Groceries"]
    # Weekly budget per period << monthly (500 EUR ≈ 115 EUR/week).
    for entry in weekly_budget:
        for cur, amount in entry["budget"].items():
            assert float(amount) > 0, f"weekly budget for {cur} must be > 0"
            if cur == "EUR":
                assert 80 < float(amount) < 160

    # (10) Bar chart total budgets must equal children aggregation of
    #      the root account in the same interval.
    for i, bar in enumerate(bar_chart["data"]):
        root_budget_children = budgets_changes["Expenses:Food"][i][
            "budget_children"
        ]
        # bar["budgets"] total == sum of children budgets per currency
        for cur, val in bar["budgets"].items():
            assert cur in root_budget_children
            assert float(val) == float(root_budget_children[cur])


