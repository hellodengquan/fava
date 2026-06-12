from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fava.beans import create
from fava.core.documents import _is_path_within
from fava.core.documents import filepath_in_document_folder
from fava.core.documents import is_document_or_import_file
from fava.core.documents import PathTraversalError
from fava.core.group_entries import group_entries_by_type
from fava.helpers import FavaAPIError

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger


def test_is_path_within() -> None:
    assert _is_path_within(Path("/test/err"), Path("/test"))
    assert _is_path_within(Path("/test/sub/file.txt"), Path("/test"))
    assert not _is_path_within(Path("/test_evil/file.txt"), Path("/test"))
    assert not _is_path_within(Path("/err"), Path("/test"))


def test_is_document_or_import_file(
    example_ledger: FavaLedger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = str(Path(__file__))
    monkeypatch.setattr(example_ledger.fava_options, "import_dirs", ["/test/"])
    monkeypatch.setattr(
        example_ledger,
        "all_entries_by_type",
        group_entries_by_type(
            [create.document({}, datetime.date(2022, 1, 1), "Assets", path)]
        ),
    )
    assert not is_document_or_import_file("/asdfasdf", example_ledger)
    assert not is_document_or_import_file("/test/../../err", example_ledger)
    assert is_document_or_import_file(path, example_ledger)
    assert is_document_or_import_file("/test/err/../err", example_ledger)
    assert is_document_or_import_file("/test/err/../err", example_ledger)
    assert not is_document_or_import_file("/test_evil/file", example_ledger)


def test_resolve_path_cwd_independent(
    example_ledger: FavaLedger,
    tmp_path: Path,
) -> None:
    ledger_dir = Path(example_ledger.beancount_file_path).parent
    rel = "documents/receipt.pdf"

    results = []
    for cwd in (tmp_path, ledger_dir, Path.home()):
        original_cwd = os.getcwd()
        try:
            os.chdir(cwd)
            results.append(example_ledger.resolve_path(rel))
        finally:
            os.chdir(original_cwd)

    assert results[0] == results[1] == results[2]
    assert results[0] == (ledger_dir / rel).resolve()


def test_filepath_in_documents_folder(
    example_ledger: FavaLedger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(example_ledger.options, "documents", ["/test"])  # ty:ignore[invalid-argument-type]

    def _join(start: str, *args: str) -> Path:
        return Path(start).joinpath(*args).resolve()

    assert filepath_in_document_folder(
        "/test",
        "Assets:US:BofA:Checking",
        "filename",
        example_ledger,
    ) == _join("/test", "Assets", "US", "BofA", "Checking", "filename")
    assert filepath_in_document_folder(
        "/test",
        "Assets:US:BofA:Checking",
        "file/name",
        example_ledger,
    ) == _join("/test", "Assets", "US", "BofA", "Checking", "file name")
    assert filepath_in_document_folder(
        "/test",
        "Assets:US:BofA:Checking",
        "/../file/name",
        example_ledger,
    ) == _join("/test", "Assets", "US", "BofA", "Checking", " .. file name")
    with pytest.raises(FavaAPIError):
        filepath_in_document_folder(
            "/test",
            "notanaccount",
            "filename",
            example_ledger,
        )
    with pytest.raises(FavaAPIError):
        filepath_in_document_folder(
            "/notadocumentsfolder",
            "Assets:US:BofA:Checking",
            "filename",
            example_ledger,
        )
