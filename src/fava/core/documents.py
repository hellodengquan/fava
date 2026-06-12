"""Document path related helpers."""

from __future__ import annotations

from os import altsep
from os import sep
from pathlib import Path
from typing import TYPE_CHECKING

from fava.helpers import FavaAPIError

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger


class NotADocumentsFolderError(FavaAPIError):
    """Not a documents folder."""

    def __init__(self, folder: str) -> None:
        super().__init__(f"Not a documents folder: {folder}.")


class NotAValidAccountError(FavaAPIError):
    """Not a valid account."""

    def __init__(self, account: str) -> None:
        super().__init__(f"Not a valid account: '{account}'")


class PathTraversalError(FavaAPIError):
    """The resolved path escapes its allowed directory."""

    def __init__(self, path: Path, allowed: Path) -> None:
        super().__init__(
            f"Path '{path}' is outside the allowed directory '{allowed}'."
        )


def _is_path_within(path: Path, directory: Path) -> bool:
    """Check whether *path* is located inside *directory*.

    Both arguments **must** be resolved (absolute) paths.
    Uses :meth:`Path.relative_to` instead of a plain string prefix
    check to avoid false positives such as ``/imports_evil`` matching
    ``/imports``.
    """
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def is_document_or_import_file(filename: str, ledger: FavaLedger) -> bool:
    """Check whether the filename is a document or in an import directory.

    Args:
        filename: The filename to check.
        ledger: The FavaLedger.

    Returns:
        Whether this is one of the documents or a path in an import dir.
    """
    file_path = ledger.resolve_path(filename)

    if any(
        file_path == Path(d.filename).resolve()
        for d in ledger.all_entries_by_type.Document
    ):
        return True

    return any(
        _is_path_within(file_path, ledger.join_path(d))
        for d in ledger.fava_options.import_dirs
    )


def filepath_in_document_folder(
    documents_folder: str,
    account: str,
    filename: str,
    ledger: FavaLedger,
) -> Path:
    """File path for a document in the folder for an account.

    Args:
        documents_folder: The documents folder.
        account: The account to choose the subfolder for.
        filename: The filename of the document.
        ledger: The FavaLedger.

    Returns:
        The path that the document should be saved at.

    Raises:
        NotADocumentsFolderError: If *documents_folder* is not a declared
            documents directory.
        NotAValidAccountError: If *account* is not a known account.
        PathTraversalError: If the resolved path escapes the documents
            folder (path-traversal attempt).
    """
    if documents_folder not in ledger.options["documents"]:
        raise NotADocumentsFolderError(documents_folder)

    if account not in ledger.attributes.accounts:
        raise NotAValidAccountError(account)

    filename = filename.replace(sep, " ")
    if altsep:  # pragma: no cover
        filename = filename.replace(altsep, " ")

    result = ledger.join_path(
        documents_folder,
        *account.split(":"),
        filename,
    )

    base_dir = ledger.join_path(documents_folder)
    if not _is_path_within(result, base_dir):
        raise PathTraversalError(result, base_dir)

    return result
