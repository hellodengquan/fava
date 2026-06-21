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
from fava.beans.abc import Transaction
from fava.beans.funcs import hash_entry
from fava.helpers import FavaAPIError

from .module_base import FavaModule

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from fava.beans.abc import Directive
    from fava.beans.abc import Posting
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

REFERENCE_META_KEYS = frozenset(
    {
        "document",
        "documents",
        "attachment",
        "attachments",
        "file",
        "files",
        "receipt",
        "invoice",
        "附件",
        "凭证",
        "发票",
    }
)

REFERENCE_QUERY_PATH = (
    "To find all references to a document, query metadata keys that start with "
    "'document' or match known attachment keys (document, documents, "
    "attachment, attachments, file, files, receipt, invoice, 附件, 凭证, 发票) "
    "across all entries in the filtered ledger. Both the document's full path "
    "and its basename are matched. From the journal page, you can navigate to "
    "individual entries by entry_hash: /<entry_hash> or use the context page "
    "/context/<entry_hash>."
)


@dataclass(frozen=True)
class ReferenceSource:
    """A single reference to a document from another entry.

    The ``entry_hash`` field can be used to navigate to the entry via the
    URL path ``/<entry_hash>`` or to the context view via
    ``/context/<entry_hash>``.
    """

    entry_hash: str
    entry_type: str
    date: str
    account: str
    payee: str
    narration: str
    query_path: str


@dataclass(frozen=True)
class ReferenceStats:
    """Statistics for document references across transactions."""

    total_references: int
    total_documents_referenced: int
    document_reference_counts: dict[str, int]
    top_referenced: list[tuple[str, int]]
    metadata_keys_found: list[str]


@dataclass(frozen=True)
class SizeContext:
    """Context for a size anomaly detection."""

    size_bytes: int
    size_kb: float
    criterion: str
    median_size_kb: float | None
    min_threshold_kb: int
    max_threshold_kb: int
    median_ratio_low_pct: int
    median_ratio_high_pct: int


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
    reference_stats: ReferenceStats


def _query_path_for_entry(entry_hash: str) -> str:
    """Return the URL query path to an entry.

    Args:
        entry_hash: The hash of the entry.

    Returns:
        A string describing how to navigate to the entry.
    """
    return f"/{entry_hash} (context: /context/{entry_hash})"


def _metadata_for_posting(posting: Posting) -> dict[str, str]:
    """Extract document references from a posting's metadata.

    Args:
        posting: A Transaction posting.

    Returns:
        A dictionary of metadata keys and values that reference documents.
    """
    result: dict[str, str] = {}
    if posting.meta is None:
        return result
    for key, value in posting.meta.items():
        if isinstance(value, str) and (
            key.startswith("document") or key.lower() in REFERENCE_META_KEYS
        ):
            result[key] = value
    return result


def _build_reference_source(
    entry: Directive,
    *,
    account: str = "",
    meta_key: str | None = None,
) -> ReferenceSource:
    """Build a ReferenceSource from a referring entry.

    Args:
        entry: The entry that references a document.
        account: The account associated with the reference (for Transaction
            postings, this is the posting's account).
        meta_key: The metadata key that contained the document reference.

    Returns:
        A ReferenceSource with identifying information and query path.

    The query_path field documents how to navigate to this entry:
        - Direct entry view: ``/<entry_hash>``
        - Context view: ``/context/<entry_hash>``
    """
    entry_hash = hash_entry(entry)
    entry_type = type(entry).__name__
    date_str = str(entry.date)
    payee = getattr(entry, "payee", "") or ""
    narration = getattr(entry, "narration", "") or ""

    if account:
        source_account = account
    else:
        source_account = getattr(entry, "account", "")

    if meta_key:
        narration = f"[{meta_key}] {narration}".strip()

    return ReferenceSource(
        entry_hash=entry_hash,
        entry_type=entry_type,
        date=date_str,
        account=source_account,
        payee=payee,
        narration=narration,
        query_path=_query_path_for_entry(entry_hash),
    )


def _detect_size_anomaly(
    size_bytes: int,
    median_size_kb: float | None,
    *,
    min_threshold_kb: int,
    max_threshold_kb: int,
    median_ratio_low_pct: int,
    median_ratio_high_pct: int,
) -> tuple[str, str, SizeContext] | None:
    """Detect if a file size is anomalous.

    Uses a two-layer detection strategy with user-configurable thresholds:

    1. **Absolute thresholds**:
       - Files of 0 bytes → always flagged
       - Files smaller than ``min_threshold_kb`` (default: 1 KB)
       - Files larger than ``max_threshold_kb`` (default: 51200 KB / 50 MB)

    2. **Relative-to-median thresholds** (when population median available):
       - Files smaller than ``median_ratio_low_pct`` % of median
         (default: 10% → 0.1x)
       - Files larger than ``median_ratio_high_pct`` % of median
         (default: 1000% → 10x)

    Args:
        size_bytes: The file size in bytes.
        median_size_kb: The median file size in KB for the document
            population, or None if unavailable.
        min_threshold_kb: Minimum acceptable file size in KB (absolute).
        max_threshold_kb: Maximum acceptable file size in KB (absolute).
        median_ratio_low_pct: Lower threshold as percentage of median.
        median_ratio_high_pct: Upper threshold as percentage of median.

    Returns:
        A tuple of (problem_type, problem_detail, SizeContext) if anomalous,
        or None if the size is normal.
    """
    size_kb = size_bytes / 1024
    median_ratio_low = median_ratio_low_pct / 100.0
    median_ratio_high = median_ratio_high_pct / 100.0

    size_context = SizeContext(
        size_bytes=size_bytes,
        size_kb=round(size_kb, 2),
        criterion="",
        median_size_kb=(
            round(median_size_kb, 2) if median_size_kb is not None else None
        ),
        min_threshold_kb=min_threshold_kb,
        max_threshold_kb=max_threshold_kb,
        median_ratio_low_pct=median_ratio_low_pct,
        median_ratio_high_pct=median_ratio_high_pct,
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
                min_threshold_kb=min_threshold_kb,
                max_threshold_kb=max_threshold_kb,
                median_ratio_low_pct=median_ratio_low_pct,
                median_ratio_high_pct=median_ratio_high_pct,
            ),
        )

    if size_kb < min_threshold_kb:
        return (
            "size_anomaly_small_absolute",
            f"文件过小: {size_bytes} 字节 < {min_threshold_kb} KB (绝对阈值)",
            SizeContext(
                size_bytes=size_context.size_bytes,
                size_kb=size_context.size_kb,
                criterion="absolute_min",
                median_size_kb=size_context.median_size_kb,
                min_threshold_kb=min_threshold_kb,
                max_threshold_kb=max_threshold_kb,
                median_ratio_low_pct=median_ratio_low_pct,
                median_ratio_high_pct=median_ratio_high_pct,
            ),
        )

    if size_kb > max_threshold_kb:
        return (
            "size_anomaly_large_absolute",
            f"文件过大: {size_kb / 1024:.1f} MB > {max_threshold_kb / 1024:.0f} MB (绝对阈值)",
            SizeContext(
                size_bytes=size_context.size_bytes,
                size_kb=size_context.size_kb,
                criterion="absolute_max",
                median_size_kb=size_context.median_size_kb,
                min_threshold_kb=min_threshold_kb,
                max_threshold_kb=max_threshold_kb,
                median_ratio_low_pct=median_ratio_low_pct,
                median_ratio_high_pct=median_ratio_high_pct,
            ),
        )

    if median_size_kb is not None and median_size_kb > 0:
        ratio = size_kb / median_size_kb
        if ratio < median_ratio_low:
            return (
                "size_anomaly_small_relative",
                f"文件偏小: {size_kb:.1f} KB < 中位数 {median_size_kb:.1f} KB 的 {median_ratio_low_pct}% (相对中位数)",
                SizeContext(
                    size_bytes=size_context.size_bytes,
                    size_kb=size_context.size_kb,
                    criterion="relative_median_low",
                    median_size_kb=size_context.median_size_kb,
                    min_threshold_kb=min_threshold_kb,
                    max_threshold_kb=max_threshold_kb,
                    median_ratio_low_pct=median_ratio_low_pct,
                    median_ratio_high_pct=median_ratio_high_pct,
                ),
            )
        if ratio > median_ratio_high:
            return (
                "size_anomaly_large_relative",
                f"文件偏大: {size_kb:.1f} KB > 中位数 {median_size_kb:.1f} KB 的 {median_ratio_high_pct / 100:.0f}x (相对中位数)",
                SizeContext(
                    size_bytes=size_context.size_bytes,
                    size_kb=size_context.size_kb,
                    criterion="relative_median_high",
                    median_size_kb=size_context.median_size_kb,
                    min_threshold_kb=min_threshold_kb,
                    max_threshold_kb=max_threshold_kb,
                    median_ratio_low_pct=median_ratio_low_pct,
                    median_ratio_high_pct=median_ratio_high_pct,
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

        This method scans all documents and performs four checks:
        1. Missing narration/description metadata
        2. Duplicate filenames
        3. Size anomalies (configurable absolute + relative-to-median)
        4. Multiple references from transactions (including metadata
           reverse-lookup and posting-level references)

        Reference detection scans:
        - Entry-level metadata keys starting with 'document' or matching
          known attachment keys (document, attachment, file, receipt, etc.)
        - Transaction posting-level metadata (postings can also reference
          documents via the same keys)
        - Both the document's full path and its basename are matched

        Args:
            filtered: The filtered ledger.

        Returns:
            Document review data with categorized problem documents and
            reference statistics.
        """
        opts = self.ledger.fava_options
        min_threshold_kb = opts.document_review_min_size_kb
        max_threshold_kb = opts.document_review_max_size_kb
        median_ratio_low_pct = opts.document_review_median_ratio_low
        median_ratio_high_pct = opts.document_review_median_ratio_high

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
                result = _detect_size_anomaly(
                    size_bytes,
                    median_size_kb,
                    min_threshold_kb=min_threshold_kb,
                    max_threshold_kb=max_threshold_kb,
                    median_ratio_low_pct=median_ratio_low_pct,
                    median_ratio_high_pct=median_ratio_high_pct,
                )
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
        ref_counts: dict[str, int] = defaultdict(int)
        metadata_keys_found: set[str] = set()

        for entry in filtered.entries:
            if entry.meta is None:
                if isinstance(entry, Transaction) and entry.postings:
                    for posting in entry.postings:
                        post_meta = _metadata_for_posting(posting)
                        for meta_key, meta_value in post_meta.items():
                            metadata_keys_found.add(meta_key)
                            ref_counts[meta_value] += 1
                            ref_map[meta_value].append(
                                _build_reference_source(
                                    entry,
                                    account=posting.account,
                                    meta_key=meta_key,
                                )
                            )
                continue

            for key, value in entry.meta.items():
                if not isinstance(value, str):
                    continue
                if not (
                    key.startswith("document")
                    or key.lower() in REFERENCE_META_KEYS
                ):
                    continue
                metadata_keys_found.add(key)
                ref_counts[value] += 1
                if isinstance(entry, Transaction) and entry.postings:
                    for posting in entry.postings:
                        ref_map[value].append(
                            _build_reference_source(
                                entry,
                                account=posting.account,
                                meta_key=key,
                            )
                        )
                else:
                    ref_map[value].append(
                        _build_reference_source(entry, meta_key=key)
                    )

            if isinstance(entry, Transaction) and entry.postings:
                for posting in entry.postings:
                    post_meta = _metadata_for_posting(posting)
                    for meta_key, meta_value in post_meta.items():
                        metadata_keys_found.add(meta_key)
                        ref_counts[meta_value] += 1
                        ref_map[meta_value].append(
                            _build_reference_source(
                                entry,
                                account=posting.account,
                                meta_key=meta_key,
                            )
                        )

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

        total_references = sum(ref_counts.values())
        total_documents_referenced = len(ref_counts)
        sorted_refs = sorted(
            ref_counts.items(), key=lambda x: x[1], reverse=True
        )
        top_referenced = sorted_refs[:5]

        reference_stats = ReferenceStats(
            total_references=total_references,
            total_documents_referenced=total_documents_referenced,
            document_reference_counts=dict(ref_counts),
            top_referenced=top_referenced,
            metadata_keys_found=sorted(metadata_keys_found),
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
            reference_stats=reference_stats,
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
