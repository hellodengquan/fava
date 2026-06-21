"""Document path related helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from os import altsep
from os import sep
from pathlib import Path
from typing import TYPE_CHECKING

from fava.beans.abc import Document
from fava.helpers import FavaAPIError

from .module_base import FavaModule

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from fava.core import FavaLedger
    from fava.core import FilteredLedger


class NotADocumentsFolderError(FavaAPIError):
    """Not a documents folder."""

    def __init__(self, folder: str) -> None:
        super().__init__(f"Not a documents folder: {folder}.")


class NotAValidAccountError(FavaAPIError):
    """Not a valid account."""

    def __init__(self, account: str) -> None:
        super().__init__(f"Not a valid account: '{account}'")


@dataclass(frozen=True)
class ProblemDocument:
    """A document with a problem."""

    document: Document
    problem_type: str
    problem_detail: str


@dataclass(frozen=True)
class DocumentReviewData:
    """Document review data with problem documents."""

    missing_narration: list[ProblemDocument]
    duplicate_names: list[ProblemDocument]
    size_anomalies: list[ProblemDocument]
    multiple_references: list[ProblemDocument]
    total_documents: int
    total_problems: int


class DocumentsModule(FavaModule):
    """Functions related to documents."""

    def is_document_or_import_file(self, filename: str) -> bool:
        """Check whether the filename is a document or in an import directory.

        Args:
            filename: The filename to check.

        Returns:
            Whether this is one of the documents or a path in an import dir.
        """
        if any(
            filename == d.filename
            for d in self.ledger.all_entries_by_type.Document
        ):
            return True
        file_path = Path(filename).resolve()
        return any(
            str(file_path).startswith(str(self.ledger.join_path(d)))
            for d in self.ledger.fava_options.import_dirs
        )

    def filepath_in_document_folder(
        self,
        documents_folder: str,
        account: str,
        filename: str,
    ) -> Path:
        """File path for a document in the folder for an account.

        Args:
            documents_folder: The documents folder.
            account: The account to choose the subfolder for.
            filename: The filename of the document.

        Returns:
            The path that the document should be saved at.
        """
        if documents_folder not in self.ledger.options["documents"]:
            raise NotADocumentsFolderError(documents_folder)

        if account not in self.ledger.attributes.accounts:
            raise NotAValidAccountError(account)

        filename = filename.replace(sep, " ")
        if altsep:  # pragma: no cover
            filename = filename.replace(altsep, " ")

        return self.ledger.join_path(
            documents_folder,
            *account.split(":"),
            filename,
        )

    def review(self, filtered: FilteredLedger) -> DocumentReviewData:
        """Get document review data with problem documents.

        Args:
            filtered: The filtered ledger.

        Returns:
            Document review data with categorized problem documents.
        """
        all_documents = [
            e for e in filtered.entries if isinstance(e, Document)
        ]
        total_documents = len(all_documents)

        missing_narration: list[ProblemDocument] = []
        duplicate_names: list[ProblemDocument] = []
        size_anomalies: list[ProblemDocument] = []
        multiple_references: list[ProblemDocument] = []

        name_counts: dict[str, list[Document]] = defaultdict(list)

        narration_keys = {
            "narration",
            "description",
            "note",
            "备注",
            "说明",
            "描述",
        }

        for doc in all_documents:
            basename = Path(doc.filename).name
            name_counts[basename].append(doc)

            has_narration = bool(narration_keys & doc.meta.keys())
            if not has_narration:
                missing_narration.append(
                    ProblemDocument(
                        doc,
                        "missing_narration",
                        "缺少备注说明",
                    )
                )

            file_path = Path(doc.filename)
            if file_path.exists() and file_path.is_file():
                size_bytes = file_path.stat().st_size
                size_kb = size_bytes / 1024
                if size_bytes == 0:
                    size_anomalies.append(
                        ProblemDocument(
                            doc,
                            "size_anomaly",
                            "文件大小为 0 字节",
                        )
                    )
                elif size_kb < 1:
                    size_anomalies.append(
                        ProblemDocument(
                            doc,
                            "size_anomaly",
                            f"文件过小: {size_bytes} 字节",
                        )
                    )
                elif size_kb > 10240:
                    size_anomalies.append(
                        ProblemDocument(
                            doc,
                            "size_anomaly",
                            f"文件过大: {size_kb / 1024:.1f} MB",
                        )
                    )

        for name, docs in name_counts.items():
            if len(docs) > 1:
                for doc in docs:
                    duplicate_names.append(
                        ProblemDocument(
                            doc,
                            "duplicate_name",
                            f"命名重复: {name} (共 {len(docs)} 个)",
                        )
                    )

        ref_counts: dict[str, list[object]] = defaultdict(list)
        for entry in filtered.entries:
            disk_docs = [
                value
                for key, value in entry.meta.items()
                if key.startswith("document") and isinstance(value, str)
            ]
            for disk_doc in disk_docs:
                ref_counts[disk_doc].append(entry)

        for doc in all_documents:
            basename = Path(doc.filename).name
            fullname = doc.filename
            refs = ref_counts.get(basename, []) + ref_counts.get(fullname, [])
            if len(refs) > 1:
                multiple_references.append(
                    ProblemDocument(
                        doc,
                        "multiple_references",
                        f"被引用 {len(refs)} 次",
                    )
                )

        total_problems = (
            len(missing_narration)
            + len(duplicate_names)
            + len(size_anomalies)
            + len(multiple_references)
        )

        return DocumentReviewData(
            missing_narration=missing_narration,
            duplicate_names=duplicate_names,
            size_anomalies=size_anomalies,
            multiple_references=multiple_references,
            total_documents=total_documents,
            total_problems=total_problems,
        )


def is_document_or_import_file(filename: str, ledger: FavaLedger) -> bool:
    """Check whether the filename is a document or in an import directory.

    Args:
        filename: The filename to check.
        ledger: The FavaLedger.

    Returns:
        Whether this is one of the documents or a path in an import dir.

    .. deprecated::
        Use :meth:`DocumentsModule.is_document_or_import_file` instead.
    """
    return ledger.documents.is_document_or_import_file(filename)


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

    .. deprecated::
        Use :meth:`DocumentsModule.filepath_in_document_folder` instead.
    """
    return ledger.documents.filepath_in_document_folder(
        documents_folder, account, filename
    )
