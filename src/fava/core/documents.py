"""Document path related helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from os import altsep
from os import sep
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING

from fava.beans.abc import Document
from fava.beans.funcs import hash_entry
from fava.helpers import FavaAPIError

from .module_base import FavaModule

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from fava.beans.abc import Directive
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


SIZE_ZERO_BYTES = 0
SIZE_ABSOLUTE_MIN_KB = 1
SIZE_ABSOLUTE_MAX_KB = 10240
SIZE_MEDIAN_RATIO_LOW = 0.1
SIZE_MEDIAN_RATIO_HIGH = 10.0

NARRATION_META_KEYS = frozenset(
    {
        "narration",
        "description",
        "note",
        "备注",
        "说明",
        "描述",
    }
)


@dataclass(frozen=True)
class ReferenceSource:
    """A single reference to a document from another entry."""

    entry_hash: str
    entry_type: str
    date: str
    account: str
    payee: str
    narration: str


@dataclass(frozen=True)
class SizeContext:
    """Context for a size anomaly detection."""

    size_bytes: int
    size_kb: float
    criterion: str
    median_size_kb: float | None


@dataclass(frozen=True)
class ProblemDocument:
    """A document with a problem."""

    document: Document
    problem_type: str
    problem_detail: str
    reference_sources: list[ReferenceSource]
    size_context: SizeContext | None


@dataclass(frozen=True)
class DocumentReviewData:
    """Document review data with problem documents."""

    missing_narration: list[ProblemDocument]
    duplicate_names: list[ProblemDocument]
    size_anomalies: list[ProblemDocument]
    multiple_references: list[ProblemDocument]
    total_documents: int
    total_problems: int


def _build_reference_source(entry: Directive) -> ReferenceSource:
    """Build a ReferenceSource from a referring entry.

    Args:
        entry: The entry that references a document.

    Returns:
        A ReferenceSource with identifying information and query path.
    """
    entry_hash = hash_entry(entry)
    entry_type = type(entry).__name__
    date_str = str(entry.date)
    account = getattr(entry, "account", "")
    payee = getattr(entry, "payee", "") or ""
    narration = getattr(entry, "narration", "") or ""
    return ReferenceSource(
        entry_hash=entry_hash,
        entry_type=entry_type,
        date=date_str,
        account=account,
        payee=payee,
        narration=narration,
    )


def _detect_size_anomaly(
    size_bytes: int,
    median_size_kb: float | None,
) -> tuple[str, str, SizeContext] | None:
    """Detect if a file size is anomalous.

    Uses a two-layer detection strategy:
    1. Absolute thresholds: files of 0 bytes, smaller than 1 KB, or larger
       than 10 MB are always flagged.
    2. Relative-to-median thresholds: when a population median is available,
       files smaller than 10% of the median or larger than 10x the median
       are also flagged.

    Args:
        size_bytes: The file size in bytes.
        median_size_kb: The median file size in KB for the document
            population, or None if unavailable.

    Returns:
        A tuple of (problem_type, problem_detail, SizeContext) if anomalous,
        or None if the size is normal.
    """
    size_kb = size_bytes / 1024
    size_context = SizeContext(
        size_bytes=size_bytes,
        size_kb=round(size_kb, 2),
        criterion="",
        median_size_kb=(
            round(median_size_kb, 2) if median_size_kb is not None else None
        ),
    )

    if size_bytes == SIZE_ZERO_BYTES:
        return (
            "size_anomaly_zero",
            "文件大小为 0 字节 (绝对阈值)",
            SizeContext(
                size_bytes=size_context.size_bytes,
                size_kb=size_context.size_kb,
                criterion="absolute_zero",
                median_size_kb=size_context.median_size_kb,
            ),
        )

    if size_kb < SIZE_ABSOLUTE_MIN_KB:
        return (
            "size_anomaly_small_absolute",
            f"文件过小: {size_bytes} 字节 < {SIZE_ABSOLUTE_MIN_KB} KB (绝对阈值)",
            SizeContext(
                size_bytes=size_context.size_bytes,
                size_kb=size_context.size_kb,
                criterion="absolute_min",
                median_size_kb=size_context.median_size_kb,
            ),
        )

    if size_kb > SIZE_ABSOLUTE_MAX_KB:
        return (
            "size_anomaly_large_absolute",
            f"文件过大: {size_kb / 1024:.1f} MB > {SIZE_ABSOLUTE_MAX_KB / 1024:.0f} MB (绝对阈值)",
            SizeContext(
                size_bytes=size_context.size_bytes,
                size_kb=size_context.size_kb,
                criterion="absolute_max",
                median_size_kb=size_context.median_size_kb,
            ),
        )

    if median_size_kb is not None and median_size_kb > 0:
        ratio = size_kb / median_size_kb
        if ratio < SIZE_MEDIAN_RATIO_LOW:
            return (
                "size_anomaly_small_relative",
                f"文件偏小: {size_kb:.1f} KB < 中位数 {median_size_kb:.1f} KB 的 {SIZE_MEDIAN_RATIO_LOW * 100:.0f}% (相对中位数)",
                SizeContext(
                    size_bytes=size_context.size_bytes,
                    size_kb=size_context.size_kb,
                    criterion="relative_median_low",
                    median_size_kb=size_context.median_size_kb,
                ),
            )
        if ratio > SIZE_MEDIAN_RATIO_HIGH:
            return (
                "size_anomaly_large_relative",
                f"文件偏大: {size_kb:.1f} KB > 中位数 {median_size_kb:.1f} KB 的 {SIZE_MEDIAN_RATIO_HIGH:.0f}x (相对中位数)",
                SizeContext(
                    size_bytes=size_context.size_bytes,
                    size_kb=size_context.size_kb,
                    criterion="relative_median_high",
                    median_size_kb=size_context.median_size_kb,
                ),
            )

    return None


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

        file_sizes: list[float] = []
        for doc in all_documents:
            file_path = Path(doc.filename)
            if file_path.exists() and file_path.is_file():
                file_sizes.append(file_path.stat().st_size / 1024)

        median_size_kb: float | None = None
        if len(file_sizes) >= 3:
            median_size_kb = float(median(file_sizes))

        for doc in all_documents:
            basename = Path(doc.filename).name
            name_counts[basename].append(doc)

            has_narration = bool(NARRATION_META_KEYS & doc.meta.keys())
            if not has_narration:
                missing_narration.append(
                    ProblemDocument(
                        doc,
                        "missing_narration",
                        "缺少备注说明",
                        [],
                        None,
                    )
                )

            file_path = Path(doc.filename)
            if file_path.exists() and file_path.is_file():
                size_bytes = file_path.stat().st_size
                result = _detect_size_anomaly(size_bytes, median_size_kb)
                if result is not None:
                    problem_type, problem_detail, size_context = result
                    size_anomalies.append(
                        ProblemDocument(
                            doc,
                            problem_type,
                            problem_detail,
                            [],
                            size_context,
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
                            [],
                            None,
                        )
                    )

        ref_map: dict[str, list[ReferenceSource]] = defaultdict(list)
        for entry in filtered.entries:
            disk_docs = [
                value
                for key, value in entry.meta.items()
                if key.startswith("document") and isinstance(value, str)
            ]
            for disk_doc in disk_docs:
                ref_map[disk_doc].append(_build_reference_source(entry))

        for doc in all_documents:
            basename = Path(doc.filename).name
            fullname = doc.filename
            sources = ref_map.get(basename, []) + ref_map.get(fullname, [])
            if len(sources) > 1:
                multiple_references.append(
                    ProblemDocument(
                        doc,
                        "multiple_references",
                        f"被引用 {len(sources)} 次",
                        sources,
                        None,
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
