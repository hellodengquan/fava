"""JSON API.

This module contains the url endpoints of the JSON API that is used by the web
interface for asynchronous functionality.
"""

from __future__ import annotations

import logging
import shutil
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import fields
from functools import wraps
from http import HTTPStatus
from inspect import Parameter
from inspect import signature
from pathlib import Path
from pprint import pformat
from typing import Any
from typing import TYPE_CHECKING

from flask import Blueprint
from flask import get_template_attribute
from flask import jsonify
from flask import request
from flask_babel import gettext

from fava.beans.abc import Document
from fava.beans.abc import Event
from fava.context import g
from fava.core import EntryNotFoundForHashError
from fava.core.conversion import UNITS
from fava.core.documents import filepath_in_document_folder
from fava.core.documents import is_document_or_import_file
from fava.core.file import GeneratedEntryError
from fava.core.file import get_entry_slice
from fava.core.filters import FilterError
from fava.core.group_entries import group_entries_by_type
from fava.core.ingest import filepath_in_primary_imports_folder
from fava.core.misc import align
from fava.helpers import FavaAPIError
from fava.internal_api import ChartApi
from fava.internal_api import get_errors
from fava.internal_api import get_ledger_data
from fava.serialisation import deserialise
from fava.serialisation import serialise

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from collections.abc import Mapping
    from collections.abc import Sequence
    from datetime import date
    from decimal import Decimal

    from flask.wrappers import Response

    from fava.beans.abc import Directive
    from fava.core import FavaLedger
    from fava.core.ingest import FileImporters
    from fava.core.inventory import SimpleCounterInventory
    from fava.core.query import QueryResultTable
    from fava.core.query import QueryResultText
    from fava.core.tree import SerialisedTreeNode
    from fava.internal_api import ChartData
    from fava.util.date import DateRange
    from fava.util.date import Interval


json_api = Blueprint("json_api", __name__)
log = logging.getLogger(__name__)


class ValidationError(Exception):
    """Validation of data failed."""


class MissingParameterValidationError(ValidationError):
    """Validation failed due to missing parameter."""

    def __init__(self, param: str) -> None:
        super().__init__(f"Parameter `{param}` is missing.")


class IncorrectTypeValidationError(ValidationError):
    """Validation failed due to incorrect type of parameter."""

    def __init__(self, param: str, expected: type) -> None:
        super().__init__(
            f"Parameter `{param}` of incorrect type - expected {expected}.",
        )


class InvalidJsonRequestError(ValidationError):
    """Validation failed due to invalid JSON in body."""

    def __init__(self) -> None:
        super().__init__("Invalid JSON body.")


def json_err(msg: str, status: HTTPStatus) -> Response:
    """Jsonify the error message."""
    res = jsonify({"error": msg})
    res.status = status
    return res


def json_success(data: Any) -> Response:
    """Jsonify the response."""
    return jsonify(
        {"data": data, "mtime": str(g.ledger.mtime)},
    )


class FavaJSONAPIError(FavaAPIError):
    """An error with a HTTPStatus."""

    @property
    @abstractmethod
    def status(self) -> HTTPStatus:
        """HTTP status that should be used for the response."""


class NotFoundError(FavaJSONAPIError):
    """Not found."""

    status = HTTPStatus.NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Not found.")


class TargetPathAlreadyExistsError(FavaJSONAPIError):
    """The given path already exists."""

    status = HTTPStatus.CONFLICT

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} already exists.")


class DocumentDirectoryMissingError(FavaJSONAPIError):
    """No document directory was specified."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY

    def __init__(self) -> None:
        super().__init__("You need to set a documents folder.")


class NoFileUploadedError(FavaJSONAPIError):
    """No file uploaded."""

    status = HTTPStatus.BAD_REQUEST

    def __init__(self) -> None:
        super().__init__("No file uploaded.")


class UploadedFileIsMissingFilenameError(FavaJSONAPIError):
    """Uploaded file is missing filename."""

    status = HTTPStatus.BAD_REQUEST

    def __init__(self) -> None:
        super().__init__("Uploaded file is missing filename.")


class NotAValidDocumentOrImportFileError(FavaJSONAPIError):
    """Not valid document or import file."""

    status = HTTPStatus.BAD_REQUEST

    def __init__(self, filename: str) -> None:
        super().__init__(f"Not valid document or import file: '{filename}'.")


class NotAFileError(FavaJSONAPIError):
    """Not a file."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY

    def __init__(self, filename: str) -> None:
        super().__init__(f"Not a file: '{filename}'")


@json_api.errorhandler(FavaAPIError)
def _(error: FavaAPIError) -> Response:
    log.error("Encountered FavaAPIError.", exc_info=error)
    return json_err(error.message, HTTPStatus.INTERNAL_SERVER_ERROR)


@json_api.errorhandler(FavaJSONAPIError)
def _(error: FavaJSONAPIError) -> Response:
    return json_err(error.message, error.status)


@json_api.errorhandler(FilterError)
def _(error: FilterError) -> Response:
    return json_err(error.message, HTTPStatus.BAD_REQUEST)


@json_api.errorhandler(OSError)
def _(error: OSError) -> Response:  # pragma: no cover
    log.error("Encountered OSError.", exc_info=error)
    return json_err(error.strerror or "", HTTPStatus.INTERNAL_SERVER_ERROR)


@json_api.errorhandler(ValidationError)
def _(error: ValidationError) -> Response:
    return json_err(f"Invalid API request: {error!s}", HTTPStatus.BAD_REQUEST)


@json_api.errorhandler(EntryNotFoundForHashError)
def _(error: EntryNotFoundForHashError) -> Response:
    return json_err(error.message, HTTPStatus.NOT_FOUND)


@json_api.errorhandler(GeneratedEntryError)
def _(error: GeneratedEntryError) -> Response:
    return json_err(error.message, HTTPStatus.UNPROCESSABLE_ENTITY)


def validate_func_arguments(
    func: Callable[..., Any],
) -> Callable[[Mapping[str, str]], list[str]] | None:
    """Validate arguments for a function.

    This currently only works for strings and lists (but only does a shallow
    validation for lists).

    Args:
        func: The function to check parameters for.

    Returns:
        A function, which takes a Mapping and tries to construct a list of
        positional parameters for the given function or None if the function
        has no parameters.
    """
    sig = signature(func)
    params: list[tuple[str, Any]] = []
    for param in sig.parameters.values():
        if param.annotation not in {"str", "list[Any]"}:  # pragma: no cover
            msg = (f"Type of param {param.name} needs to str or list",)
            raise ValueError(msg)
        if param.kind != Parameter.POSITIONAL_OR_KEYWORD:  # pragma: no cover
            msg2 = f"Param {param.name} should be positional"
            raise ValueError(msg2)
        params.append((param.name, str if param.annotation == "str" else list))

    if not params:
        return None

    def validator(mapping: Mapping[str, str]) -> list[str]:
        args: list[str] = []
        for param, type_ in params:
            val = mapping.get(param, None)
            if val is None:
                raise MissingParameterValidationError(param)
            if not isinstance(val, type_):
                raise IncorrectTypeValidationError(param, type_)
            args.append(val)
        return args

    return validator


def api_endpoint(func: Callable[..., Any]) -> Callable[[], Response]:
    """Register an API endpoint.

    The part of the function name up to the first underscore determines
    the accepted HTTP method. For GET and DELETE endpoints, the function
    parameters are extracted from the URL query string and passed to the
    decorated endpoint handler.
    """
    method, _, name = func.__name__.partition("_")  # ty:ignore[unresolved-attribute]
    if method not in {"get", "delete", "put"}:  # pragma: no cover
        msg = f"Invalid endpoint function name: {func.__name__}"  # ty:ignore[unresolved-attribute]
        raise ValueError(msg)
    validator = validate_func_arguments(func)

    @json_api.route(f"/{name}", methods=[method])
    @wraps(func)
    def _wrapper() -> Response:
        if validator is not None:
            if method == "put":
                request_json = request.get_json(silent=True)
                if request_json is None:
                    raise InvalidJsonRequestError
                data = request_json
            else:
                data = request.args
            res = func(*validator(data))
        else:
            res = func()
        return json_success(res)

    return _wrapper


@api_endpoint
def get_changed() -> bool:
    """Check for file changes."""
    return g.ledger.changed()


api_endpoint(get_errors)
api_endpoint(get_ledger_data)


@api_endpoint
def get_payee_accounts(payee: str) -> Sequence[str]:
    """Rank accounts for the given payee."""
    return g.ledger.attributes.payee_accounts(payee)


@api_endpoint
def get_query(query_string: str) -> QueryResultTable | QueryResultText:
    """Run a Beancount query."""
    return g.ledger.query_shell.execute_query_serialised(
        g.filtered.entries_with_all_prices, query_string
    )


@api_endpoint
def get_extract(filename: str, importer: str) -> Sequence[Any]:
    """Extract entries using the ingest framework."""
    entries = g.ledger.ingest.extract(filename, importer)
    return list(map(serialise, entries))


@dataclass(frozen=True)
class Context:
    """Context for an entry."""

    entry: Any
    balances_before: Mapping[str, Sequence[str]] | None
    balances_after: Mapping[str, Sequence[str]] | None


@api_endpoint
def get_context(entry_hash: str) -> Context:
    """Entry context."""
    entry, before, after = g.ledger.context(entry_hash)
    return Context(serialise(entry), before, after)


@dataclass(frozen=True)
class SourceSlice:
    """Source slice for an entry."""

    sha256sum: str
    slice: str


@api_endpoint
def get_source_slice(entry_hash: str) -> SourceSlice:
    """Entry slice."""
    entry = g.ledger.get_entry(entry_hash)
    source_slice, sha256sum = get_entry_slice(entry)
    return SourceSlice(sha256sum, source_slice)


@api_endpoint
def put_move(account: str, new_name: str, filename: str) -> str:
    """Move a document."""
    if not g.ledger.options["documents"]:
        raise DocumentDirectoryMissingError

    new_path = filepath_in_document_folder(
        g.ledger.options["documents"][0],
        account,
        new_name,
        g.ledger,
    )
    file_path = Path(filename)

    if not file_path.is_file():
        raise NotAFileError(filename)
    if new_path.exists():
        raise TargetPathAlreadyExistsError(new_path)

    new_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(filename, new_path)

    return f"Moved {filename} to {new_path}."


@api_endpoint
def get_payee_transaction(payee: str) -> Any:
    """Last transaction for the given payee."""
    entry = g.ledger.attributes.payee_transaction(payee)
    return serialise(entry) if entry else None


@api_endpoint
def get_narration_transaction(narration: str) -> Any:
    """Last transaction for the given narration."""
    entry = g.ledger.attributes.narration_transaction(narration)
    return serialise(entry) if entry else None


@api_endpoint
def get_narrations() -> Sequence[str]:
    """List of all narrations in the ledger."""
    return g.ledger.attributes.narrations


@dataclass(frozen=True)
class SourceFile:
    """Source slice for an entry."""

    file_path: str
    sha256sum: str
    source: str


@api_endpoint
def get_source() -> SourceFile:
    """Load one of the source files."""
    file_path = (
        request.args.get("filename", "")
        or g.ledger.fava_options.default_file
        or g.ledger.beancount_file_path
    )
    source, sha256sum = g.ledger.file.get_source(Path(file_path))
    return SourceFile(file_path=file_path, sha256sum=sha256sum, source=source)


@api_endpoint
def put_source(file_path: str, source: str, sha256sum: str) -> str:
    """Write one of the source files and return the updated sha256sum."""
    return g.ledger.file.set_source(Path(file_path), source, sha256sum)


@api_endpoint
def put_source_slice(entry_hash: str, source: str, sha256sum: str) -> str:
    """Write an entry source slice and return the updated sha256sum."""
    return g.ledger.file.save_entry_slice(entry_hash, source, sha256sum)


@api_endpoint
def delete_source_slice(entry_hash: str, sha256sum: str) -> str:
    """Delete an entry source slice."""
    g.ledger.file.delete_entry_slice(entry_hash, sha256sum)
    return f"Deleted entry {entry_hash}."


@api_endpoint
def put_format_source(source: str) -> str:
    """Format beancount file."""
    return align(source, g.ledger.fava_options.currency_column)


class FileDoesNotExistError(FavaAPIError):
    """The given file does not exist."""

    def __init__(self, filename: str) -> None:
        super().__init__(f"{filename} does not exist.")


@api_endpoint
def delete_document(filename: str) -> str:
    """Delete a document."""
    if not is_document_or_import_file(filename, g.ledger):
        raise NotAValidDocumentOrImportFileError(filename)

    file_path = Path(filename)
    if not file_path.exists():
        raise FileDoesNotExistError(filename)

    file_path.unlink()
    return f"Deleted {filename}."


@api_endpoint
def put_add_document() -> str:
    """Upload a document."""
    if not g.ledger.options["documents"]:
        raise DocumentDirectoryMissingError

    upload = request.files.get("file", None)

    if upload is None:
        raise NoFileUploadedError
    if not upload.filename:
        raise UploadedFileIsMissingFilenameError

    filepath = filepath_in_document_folder(
        request.form["folder"],
        request.form["account"],
        upload.filename,
        g.ledger,
    )

    if filepath.exists():
        raise TargetPathAlreadyExistsError(filepath)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    upload.save(filepath)

    if request.form.get("hash"):
        g.ledger.file.insert_metadata(
            request.form["hash"],
            "document",
            filepath.name,
        )
    return f"Uploaded to {filepath}"


@api_endpoint
def put_attach_document(filename: str, entry_hash: str) -> str:
    """Attach a document to an entry."""
    g.ledger.file.insert_metadata(entry_hash, "document", filename)
    return f"Attached '{filename}' to entry."


@api_endpoint
def put_add_entries(entries: list[Any]) -> str:
    """Add multiple entries."""
    try:
        entries = [deserialise(entry) for entry in entries]
    except KeyError as error:  # pragma: no cover
        msg = f"KeyError: {error}"
        raise FavaAPIError(msg) from error

    g.ledger.file.insert_entries(entries)

    return f"Stored {len(entries)} entries."


@api_endpoint
def put_upload_import_file() -> str:
    """Upload a file for importing."""
    upload = request.files.get("file", None)

    if upload is None:
        raise NoFileUploadedError
    if not upload.filename:
        raise UploadedFileIsMissingFilenameError
    filepath = filepath_in_primary_imports_folder(upload.filename, g.ledger)

    if filepath.exists():
        raise TargetPathAlreadyExistsError(filepath)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    upload.save(filepath)

    return f"Uploaded to {filepath}"


########################################################################
# Reports


@api_endpoint
def get_journal() -> Sequence[Directive]:
    """Get all (filtered) entries."""
    g.ledger.changed()
    return [serialise(e) for e in g.filtered.entries]


@dataclass(frozen=True)
class JournalPage:
    """A rendered journal page."""

    page: int
    total_pages: int
    journal: str


@api_endpoint
def get_journal_page(page: str, order: str) -> JournalPage:
    """Get the HTML contents for a Journal page."""
    page_number = int(page)
    journal_table_contents = get_template_attribute(
        "_journal_table.html", "journal_table_contents"
    )
    if page == "1":
        g.ledger.changed()
    journal_page = g.filtered.paginate_journal(
        page_number, order="asc" if order == "asc" else "desc"
    )
    if journal_page is None:
        raise NotFoundError
    return JournalPage(
        page=page_number,
        total_pages=journal_page.total_pages,
        journal=journal_table_contents(journal_page.entries),
    )


@api_endpoint
def get_events() -> Sequence[Event]:
    """Get all (filtered) events."""
    g.ledger.changed()
    return [serialise(e) for e in g.filtered.entries if isinstance(e, Event)]


@api_endpoint
def get_imports() -> Sequence[FileImporters]:
    """Get a list of the importable files."""
    g.ledger.changed()
    return g.ledger.ingest.import_data()


@api_endpoint
def get_documents() -> Sequence[Document]:
    """Get all (filtered) documents."""
    g.ledger.changed()
    return [
        serialise(e) for e in g.filtered.entries if isinstance(e, Document)
    ]


@dataclass(frozen=True)
class Options:
    """Fava and Beancount options as strings."""

    fava_options: Mapping[str, str]
    beancount_options: Mapping[str, str]


@api_endpoint
def get_options() -> Options:
    """Get all options, rendered to strings for displaying in the frontend."""
    g.ledger.changed()

    fava_options = g.ledger.fava_options
    pprinted_fava_options = {
        field.name.replace("_", "-"): pformat(
            getattr(fava_options, field.name)
        )
        for field in fields(fava_options)
    }
    return Options(
        pprinted_fava_options,
        {key: str(value) for key, value in g.ledger.options.items()},
    )


@dataclass(frozen=True)
class CommodityPairWithPrices:
    """A pair of commodities and prices for them."""

    base: str
    quote: str
    prices: Sequence[tuple[date, Decimal]]


@api_endpoint
def get_commodities() -> Sequence[CommodityPairWithPrices]:
    """Get the prices for all commodity pairs."""
    g.ledger.changed()
    ret = []
    for base, quote in g.ledger.commodity_pairs():
        prices = g.filtered.prices(base, quote)
        if prices:
            ret.append(CommodityPairWithPrices(base, quote, prices))

    return ret


@dataclass(frozen=True)
class TreeReport:
    """Data for the tree reports."""

    date_range: DateRange | None
    charts: Sequence[ChartData]
    trees: Sequence[SerialisedTreeNode]


@api_endpoint
def get_income_statement() -> TreeReport:
    """Get the data for the income statement."""
    g.ledger.changed()
    options = g.ledger.options
    invert = g.ledger.fava_options.invert_income_liabilities_equity

    charts = [
        ChartApi.interval_totals(
            g.interval,
            (options["name_income"], options["name_expenses"]),
            label=gettext("Net Profit"),
            invert=invert,
        ),
        ChartApi.interval_totals(
            g.interval,
            options["name_income"],
            label=f"{gettext('Income')} ({g.interval.label})",
            invert=invert,
        ),
        ChartApi.interval_totals(
            g.interval,
            options["name_expenses"],
            label=f"{gettext('Expenses')} ({g.interval.label})",
        ),
    ]
    root_tree = g.filtered.root_tree
    trees = [
        root_tree.get(options["name_income"]),
        root_tree.net_profit(options, gettext("Net Profit")),
        root_tree.get(options["name_expenses"]),
    ]

    return TreeReport(
        g.filtered.date_range,
        charts,
        trees=[tree.serialise_with_context() for tree in trees],
    )


@api_endpoint
def get_balance_sheet() -> TreeReport:
    """Get the data for the balance sheet."""
    g.ledger.changed()
    options = g.ledger.options

    charts = [ChartApi.net_worth()]
    root_tree_closed = g.filtered.root_tree_closed
    trees = [
        root_tree_closed.get(options["name_assets"]),
        root_tree_closed.get(options["name_liabilities"]),
        root_tree_closed.get(options["name_equity"]),
    ]

    return TreeReport(
        g.filtered.date_range,
        charts,
        trees=[tree.serialise_with_context() for tree in trees],
    )


@api_endpoint
def get_trial_balance() -> TreeReport:
    """Get the data for the trial balance."""
    g.ledger.changed()

    trees = [g.filtered.root_tree.get("")]

    return TreeReport(
        g.filtered.date_range,
        charts=[],
        trees=[tree.serialise_with_context() for tree in trees],
    )


@dataclass(frozen=True)
class AccountBudget:
    """Budgets for an account."""

    budget: Mapping[str, Decimal]
    budget_children: Mapping[str, Decimal]


@dataclass(frozen=True)
class AccountReportJournal:
    """Data for the journal account report."""

    charts: Sequence[ChartData]
    journal: str


@dataclass(frozen=True)
class AccountReportTree:
    """Data for the tree account reports."""

    charts: Sequence[ChartData]
    interval_balances: Sequence[SerialisedTreeNode]
    budgets: Mapping[str, Sequence[AccountBudget]]
    dates: Sequence[DateRange]


@api_endpoint
def get_account_report() -> AccountReportJournal | AccountReportTree:
    """Get the data for the account report."""
    g.ledger.changed()

    account_name = request.args.get("a", "")
    subreport = request.args.get("r")

    charts = [
        ChartApi.account_balance(account_name),
        ChartApi.interval_totals(
            g.interval,
            account_name,
            label=gettext("Changes"),
        ),
    ]

    if subreport in {"changes", "balances"}:
        accumulate = subreport == "balances"
        interval_balances, dates = g.ledger.interval_balances(
            g.filtered,
            g.interval,
            account_name,
            accumulate=accumulate,
        )

        all_accounts = (
            interval_balances[0].accounts if interval_balances else []
        )
        budget_accounts = [
            a for a in all_accounts if a.startswith(account_name)
        ]
        budgets_mod = g.ledger.budgets
        first_date_range = dates[-1]
        budgets = {
            account: [
                AccountBudget(
                    budgets_mod.calculate(
                        account,
                        (first_date_range if accumulate else date_range).begin,
                        date_range.end,
                    ),
                    budgets_mod.calculate_children(
                        account,
                        (first_date_range if accumulate else date_range).begin,
                        date_range.end,
                    ),
                )
                for date_range in dates
            ]
            for account in budget_accounts
        }

        return AccountReportTree(
            charts,
            interval_balances=[
                tree.get(account_name).serialise(
                    g.conv,
                    g.ledger.prices,
                    date_range.end_inclusive,
                    with_cost=False,
                )
                for tree, date_range in zip(
                    interval_balances, dates, strict=True
                )
            ],
            dates=dates,
            budgets=budgets,
        )

    journal_table_contents = get_template_attribute(
        "_journal_table.html", "journal_table_contents"
    )
    entries = reversed(
        g.ledger.account_journal(
            g.filtered,
            account_name,
            g.conv,
            with_children=g.ledger.fava_options.account_journal_include_children,
        )
    )
    return AccountReportJournal(
        charts,
        journal=journal_table_contents(entries, show_change_and_balance=True),
    )


@dataclass(frozen=True)
class BudgetBreakdownInterval:
    """Budget breakdown for one interval."""

    label: str
    budget: Mapping[str, Decimal]
    budget_children: Mapping[str, Decimal]
    actual: Mapping[str, Decimal]
    actual_children: Mapping[str, Decimal]


@dataclass(frozen=True)
class BudgetBreakdownAccount:
    """Budget breakdown for one account in the tree."""

    account: str
    intervals: Sequence[BudgetBreakdownInterval]
    children: Sequence[BudgetBreakdownAccount]


@dataclass(frozen=True)
class BudgetBreakdownReport:
    """Data for the budget breakdown report."""

    account: str
    interval: str
    dates: Sequence[DateRange]
    root: BudgetBreakdownAccount


@api_endpoint
def get_budget_breakdown() -> BudgetBreakdownReport:
    """Get the data for the budget breakdown report."""
    g.ledger.changed()

    account_name = request.args.get("a", "")
    interval = g.interval

    accumulate = False
    interval_balances, dates = g.ledger.interval_balances(
        g.filtered,
        interval,
        account_name,
        accumulate=accumulate,
    )

    if not interval_balances or not dates:
        return BudgetBreakdownReport(
            account=account_name,
            interval=interval.label.lower(),
            dates=[],
            root=BudgetBreakdownAccount(
                account=account_name,
                intervals=[],
                children=[],
            ),
        )

    root_tree = interval_balances[-1]
    root_node = root_tree.get(account_name).serialise(
        g.conv,
        g.ledger.prices,
        dates[-1].end_inclusive,
        with_cost=False,
    )

    budgets_mod = g.ledger.budgets
    first_date_range = dates[-1]

    all_accounts = interval_balances[0].accounts if interval_balances else []
    budget_accounts = [a for a in all_accounts if a.startswith(account_name)]

    budget_data: dict[str, list[dict]] = {}
    for acct in budget_accounts:
        budget_data[acct] = []
        for date_range in dates:
            begin = (first_date_range if accumulate else date_range).begin
            b = budgets_mod.calculate(acct, begin, date_range.end)
            bc = budgets_mod.calculate_children(acct, begin, date_range.end)
            budget_data[acct].append({
                "budget": b,
                "budget_children": bc,
            })

    def build_node(
        serialised_node: SerialisedTreeNode,
    ) -> BudgetBreakdownAccount:
        acct = serialised_node.account
        intervals_list: list[BudgetBreakdownInterval] = []
        for idx, date_range in enumerate(dates):
            bd = budget_data.get(acct, [None] * len(dates))[idx] if acct in budget_data else None
            budget = bd["budget"] if bd else {}
            budget_children = bd["budget_children"] if bd else {}

            interval_tree = interval_balances[idx] if idx < len(interval_balances) else None
            actual: dict[str, Decimal] = {}
            actual_children: dict[str, Decimal] = {}
            if interval_tree is not None:
                node = interval_tree.get(acct)
                if node is not None:
                    actual = dict(
                        g.conv.apply(node.balance, g.ledger.prices, date_range.end_inclusive)
                    )
                    actual_children = dict(
                        g.conv.apply(node.balance_children, g.ledger.prices, date_range.end_inclusive)
                    )

            intervals_list.append(
                BudgetBreakdownInterval(
                    label=interval.format_date(date_range.begin),
                    budget=budget,
                    budget_children=budget_children,
                    actual=actual,
                    actual_children=actual_children,
                )
            )

        children_list = [build_node(child) for child in serialised_node.children]

        return BudgetBreakdownAccount(
            account=acct,
            intervals=intervals_list,
            children=children_list,
        )

    breakdown_root = build_node(root_node)

    return BudgetBreakdownReport(
        account=account_name,
        interval=interval.label.lower(),
        dates=dates,
        root=breakdown_root,
    )


@dataclass(frozen=True)
class ConsolidatedBudgetLedgerInfo:
    """Info about one ledger in the consolidated budget report."""

    title: str
    slug: str


@dataclass(frozen=True)
class ConsolidatedBudgetInterval:
    """Consolidated budget data for one interval."""

    label: str
    budget: Mapping[str, Decimal]
    actual: Mapping[str, Decimal]


@dataclass(frozen=True)
class ConsolidatedBudgetAccount:
    """Consolidated budget data for one account across ledgers."""

    account: str
    intervals: Sequence[ConsolidatedBudgetInterval]
    children: Sequence[ConsolidatedBudgetAccount]


@dataclass(frozen=True)
class ConsolidatedBudgetReport:
    """Data for the consolidated multi-ledger budget report."""

    ledgers: Sequence[ConsolidatedBudgetLedgerInfo]
    interval: str
    dates: Sequence[DateRange]
    root: ConsolidatedBudgetAccount


def _compute_budget_breakdown_for_ledger(
    ledger: FavaLedger,
    account_name: str,
    interval: Interval,
) -> tuple[Sequence[DateRange], BudgetBreakdownAccount | None]:
    """Compute budget breakdown for a single ledger."""
    filtered = ledger.get_filtered()
    accumulate = False
    interval_balances, dates = ledger.interval_balances(
        filtered,
        interval,
        account_name,
        accumulate=accumulate,
    )

    if not interval_balances or not dates:
        return dates, None

    root_tree = interval_balances[-1]
    root_node_raw = root_tree.get(account_name)
    if root_node_raw is None:
        return dates, None
    root_node = root_node_raw.serialise(
        ledger.conv,
        ledger.prices,
        dates[-1].end_inclusive,
        with_cost=False,
    )

    budgets_mod = ledger.budgets
    first_date_range = dates[-1]

    all_accounts = interval_balances[0].accounts if interval_balances else []
    budget_accounts = [a for a in all_accounts if a.startswith(account_name)]

    budget_data: dict[str, list[dict]] = {}
    for acct in budget_accounts:
        budget_data[acct] = []
        for date_range in dates:
            begin = (first_date_range if accumulate else date_range).begin
            b = budgets_mod.calculate(acct, begin, date_range.end)
            bc = budgets_mod.calculate_children(acct, begin, date_range.end)
            budget_data[acct].append({
                "budget": b,
                "budget_children": bc,
            })

    def build_node(
        serialised_node: SerialisedTreeNode,
    ) -> BudgetBreakdownAccount:
        acct = serialised_node.account
        intervals_list: list[BudgetBreakdownInterval] = []
        for idx, date_range in enumerate(dates):
            bd = budget_data.get(acct, [None] * len(dates))[idx] if acct in budget_data else None
            budget = bd["budget"] if bd else {}
            budget_children = bd["budget_children"] if bd else {}

            interval_tree = interval_balances[idx] if idx < len(interval_balances) else None
            actual: dict[str, Decimal] = {}
            actual_children: dict[str, Decimal] = {}
            if interval_tree is not None:
                node = interval_tree.get(acct)
                if node is not None:
                    actual = dict(
                        ledger.conv.apply(node.balance, ledger.prices, date_range.end_inclusive)
                    )
                    actual_children = dict(
                        ledger.conv.apply(node.balance_children, ledger.prices, date_range.end_inclusive)
                    )

            intervals_list.append(
                BudgetBreakdownInterval(
                    label=interval.format_date(date_range.begin),
                    budget=budget,
                    budget_children=budget_children,
                    actual=actual,
                    actual_children=actual_children,
                )
            )

        children_list = [build_node(child) for child in serialised_node.children]

        return BudgetBreakdownAccount(
            account=acct,
            intervals=intervals_list,
            children=children_list,
        )

    return dates, build_node(root_node)


def _merge_accounts(
    accounts_by_ledger: list[BudgetBreakdownAccount],
) -> ConsolidatedBudgetAccount:
    """Merge budget breakdown accounts from multiple ledgers."""
    if not accounts_by_ledger:
        return ConsolidatedBudgetAccount(
            account="",
            intervals=[],
            children=[],
        )

    account_name = accounts_by_ledger[0].account

    max_intervals = max(len(a.intervals) for a in accounts_by_ledger)

    merged_intervals: list[ConsolidatedBudgetInterval] = []
    for idx in range(max_intervals):
        merged_budget: dict[str, Decimal] = {}
        merged_actual: dict[str, Decimal] = {}
        label = ""
        for acc in accounts_by_ledger:
            if idx < len(acc.intervals):
                iv = acc.intervals[idx]
                if not label:
                    label = iv.label
                for curr, val in iv.budget.items():
                    merged_budget[curr] = merged_budget.get(curr, Decimal(0)) + val
                for curr, val in iv.actual.items():
                    merged_actual[curr] = merged_actual.get(curr, Decimal(0)) + val
        merged_intervals.append(
            ConsolidatedBudgetInterval(
                label=label,
                budget=merged_budget,
                actual=merged_actual,
            )
        )

    children_by_name: dict[str, list[BudgetBreakdownAccount]] = {}
    for acc in accounts_by_ledger:
        for child in acc.children:
            children_by_name.setdefault(child.account, []).append(child)

    merged_children: list[ConsolidatedBudgetAccount] = []
    for _, child_list in children_by_name.items():
        merged_children.append(_merge_accounts(child_list))

    return ConsolidatedBudgetAccount(
        account=account_name,
        intervals=merged_intervals,
        children=merged_children,
    )


@api_endpoint
def get_consolidated_budget() -> ConsolidatedBudgetReport:
    """Get the consolidated budget breakdown across all ledgers.

    This endpoint aggregates budget and actual data from all loaded ledgers.
    Accounts are matched by name across ledgers, and amounts are summed.
    Performance note: this iterates over all ledgers and computes interval
    balances for each, so it may be slower for large or numerous ledgers.
    """
    from flask import current_app

    ledgers_loader = current_app.config.get("LEDGERS")
    if ledgers_loader is None:
        return ConsolidatedBudgetReport(
            ledgers=[],
            interval=g.interval.label.lower(),
            dates=[],
            root=ConsolidatedBudgetAccount(
                account="",
                intervals=[],
                children=[],
            ),
        )

    account_name = request.args.get("a", "")
    interval = g.interval

    ledger_infos: list[ConsolidatedBudgetLedgerInfo] = []
    all_breakdowns: list[BudgetBreakdownAccount] = []
    all_dates: list[DateRange] = []

    for slug, ledger in ledgers_loader.items():
        ledger.changed()
        ledger_infos.append(
            ConsolidatedBudgetLedgerInfo(
                title=ledger.options["title"],
                slug=slug,
            )
        )
        dates, breakdown = _compute_budget_breakdown_for_ledger(
            ledger, account_name, interval
        )
        if breakdown is not None:
            all_breakdowns.append(breakdown)
        if dates and (not all_dates or len(dates) > len(all_dates)):
            all_dates = dates

    if not all_breakdowns:
        return ConsolidatedBudgetReport(
            ledgers=ledger_infos,
            interval=interval.label.lower(),
            dates=all_dates,
            root=ConsolidatedBudgetAccount(
                account=account_name,
                intervals=[],
                children=[],
            ),
        )

    merged_root = _merge_accounts(all_breakdowns)

    return ConsolidatedBudgetReport(
        ledgers=ledger_infos,
        interval=interval.label.lower(),
        dates=all_dates,
        root=merged_root,
    )


@dataclass(frozen=True)
class Statistics:
    """Data for the statistics report."""

    all_balance_directives: str
    balances: Mapping[str, SimpleCounterInventory]
    entries_by_type: Mapping[str, int]


@api_endpoint
def get_statistics() -> Statistics:
    """Get the data for the statistics report."""
    g.ledger.changed()

    entries_by_type = {
        type_: len(entries)
        for type_, entries in group_entries_by_type(g.filtered.entries)
        ._asdict()
        .items()
    }

    balances = {
        account_name: UNITS.apply(node.balance)
        for account_name, node in g.filtered.root_tree.items()
    }

    return Statistics(
        all_balance_directives=g.ledger.accounts.all_balance_directives(),
        balances=balances,
        entries_by_type=entries_by_type,
    )
