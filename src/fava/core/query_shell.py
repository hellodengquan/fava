"""For using the Beancount shell from Fava."""

from __future__ import annotations

import io
import shlex
import textwrap
from typing import TYPE_CHECKING

from beancount.core.amount import Amount
from beancount.core.display_context import DisplayContext
from beancount.core.inventory import Inventory
from beancount.core.position import Position
from beanquery import CompilationError
from beanquery import connect
from beanquery import Cursor
from beanquery import ParseError
from beanquery.numberify import numberify_results
from beanquery.shell import BQLShell

from fava.core.module_base import FavaModule
from fava.core.query import COLUMNS
from fava.core.query import ObjectColumn
from fava.core.query import QueryResultTable
from fava.core.query import QueryResultText
from fava.helpers import FavaAPIError
from fava.util.excel import HAVE_EXCEL
from fava.util.excel import to_csv
from fava.util.excel import to_excel

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from collections.abc import Sequence
    from typing import TypeVar

    from fava.beans.abc import Directive
    from fava.core import FavaLedger

    T = TypeVar("T")


class FavaShellError(FavaAPIError):
    """An error in the Fava BQL shell, will be turned into a string."""


class QueryNotFoundError(FavaShellError):
    """Query '{name}' not found."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Query '{name}' not found.")


class TooManyRunArgsError(FavaShellError):
    """Too many args to run: '{args}'."""

    def __init__(self, args: str) -> None:
        super().__init__(f"Too many args to run: '{args}'.")


class QueryCompilationError(FavaShellError):
    """Query compilation error."""

    def __init__(self, err: CompilationError) -> None:
        super().__init__(f"Query compilation error: {err!s}.")


class QueryParseError(FavaShellError):
    """Query parse error."""

    def __init__(self, err: ParseError) -> None:
        super().__init__(f"Query parse error: {err!s}.")


class NonExportableQueryError(FavaShellError):
    """Only queries that return a table can be printed to a file."""

    def __init__(self) -> None:
        super().__init__(
            "Only queries that return a table can be printed to a file."
        )


class FavaBQLShell(BQLShell):
    """A light wrapper around Beancount's shell."""

    outfile: io.StringIO

    def __init__(self, ledger: FavaLedger) -> None:
        super().__init__("", io.StringIO(), interactive=False)  # type: ignore[no-untyped-call]
        self.ledger = ledger
        self.stdout = self.outfile

    def run(self, entries: Sequence[Directive], query: str) -> Cursor | str:
        """Run a query, capturing output as string or returning the result."""
        self.context = connect(
            "beancount:",
            entries=entries,
            errors=self.ledger.errors,
            options=self.ledger.options,
        )
        try:
            result = self.onecmd(query)  # type: ignore[no-untyped-call]
        except ParseError as exc:
            raise QueryParseError(exc) from exc
        except CompilationError as exc:
            raise QueryCompilationError(exc) from exc

        if isinstance(result, Cursor):
            return result
        contents = self.outfile.getvalue().strip()
        self.outfile.truncate(0)
        return contents.strip().strip("\x00")

    def add_help(self) -> None:
        """Attach help functions for each of the parsed token handlers."""
        for attrname, func in BQLShell.__dict__.items():
            if attrname[:3] != "on_":
                continue
            command_name = attrname[3:]
            setattr(
                self.__class__,
                f"help_{command_name.lower()}",
                lambda _, fun=func: print(
                    textwrap.dedent(fun.__doc__).strip(),
                    file=self.outfile,
                ),
            )

    def noop(self, _: T) -> None:
        """Doesn't do anything in Fava's query shell."""
        print(self.noop.__doc__, file=self.outfile)

    on_Reload = noop  # noqa: N815
    do_exit = noop  # ty:ignore[invalid-method-override]
    do_quit = noop  # ty:ignore[invalid-method-override]
    do_EOF = noop  # noqa: N815  # ty:ignore[invalid-method-override]

    def on_Select(self, statement: str) -> Cursor:  # noqa: D102, N802
        return self.context.execute(statement)

    def do_run(self, arg: str) -> Cursor | None:
        """Run a custom query."""
        queries = self.ledger.all_entries_by_type.Query
        stripped_arg = arg.rstrip("; \t")
        if not stripped_arg:
            # List the available queries.
            for q in queries:
                print(q.name, file=self.outfile)
            return None

        name, *more = shlex.split(stripped_arg)
        if more:
            raise TooManyRunArgsError(stripped_arg)

        query = next((q for q in queries if q.name == name), None)
        if query is None:
            raise QueryNotFoundError(name)
        return self.execute(query.query_string)  # type: ignore[no-any-return,no-untyped-call]


FavaBQLShell.on_Select.__doc__ = BQLShell.on_Select.__doc__


class QueryShell(FavaModule):
    """A Fava module to run BQL queries."""

    def __init__(self, ledger: FavaLedger) -> None:
        super().__init__(ledger)
        self.shell = FavaBQLShell(ledger)

    def execute_query_serialised(
        self,
        entries: Sequence[Directive],
        query: str,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> QueryResultTable | QueryResultText:
        """Run a query and returns its serialised result.

        Arguments:
            entries: The entries to run the query on.
            query: A query string.
            canonicalizer: Optional function to canonicalize commodity names.
                When provided, ensures consistent handling of aliases across
                holdings, charts, and exports.

        Returns:
            Either a table or a text result (depending on the query).

        Raises:
            FavaAPIError: If the query response is an error.
        """
        res = self.shell.run(entries, query)
        return (
            QueryResultText(res)
            if isinstance(res, str)
            else _serialise(res, canonicalizer=canonicalizer)
        )

    def query_to_file(
        self,
        entries: Sequence[Directive],
        query_string: str,
        result_format: str,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> tuple[str, io.BytesIO]:
        """Get query result as file.

        Arguments:
            entries: The entries to run the query on.
            query_string: A string, the query to run.
            result_format: The file format to save to.
            canonicalizer: Optional function to canonicalize commodity names.
                When provided, ensures consistent handling of aliases across
                holdings, charts, and exports.

        Returns:
            A tuple (name, data), where name is either 'query_result' or the
            name of a custom query if the query string is 'run name_of_query'.
            ``data`` contains the file contents.

        Raises:
            FavaAPIError: If the result format is not supported or the
            query failed.
        """
        name = "query_result"

        if query_string.startswith((".run", "run")):
            _run, name, *more = shlex.split(query_string)
            if more:
                raise TooManyRunArgsError(query_string)
            queries = self.ledger.all_entries_by_type.Query
            query = next((q for q in queries if q.name == name), None)
            if query is None:
                raise QueryNotFoundError(name)
            query_string = query.query_string

        res = self.shell.run(entries, query_string)
        if isinstance(res, str):
            raise NonExportableQueryError

        rrows = res.fetchall()
        rtypes = res.description
        dcontext = self.ledger.options["dcontext"]
        assert isinstance(dcontext, DisplayContext)  # noqa: S101
        dformat = dcontext.build()

        if canonicalizer is not None:
            rrows = [
                tuple(
                    self._canonicalize_raw_value(val, canonicalizer)
                    for val in row
                )
                for row in rrows
            ]

        types, rows = numberify_results(rtypes, rrows, dformat)

        if result_format == "csv":
            data = to_csv(types, rows)
        else:
            if not HAVE_EXCEL:  # pragma: no cover
                msg = "Result format not supported."
                raise FavaAPIError(msg)
            data = to_excel(types, rows, result_format, query_string)
        return name, data

    @staticmethod
    def _canonicalize_raw_value(
        val: Any, canonicalizer: Callable[[str], str]
    ) -> Any:
        """Canonicalize commodity names in a raw query result value.

        This is applied BEFORE numberify_results, so it handles the raw
        Beancount types (Amount, Position, Inventory) directly, preserving
        the structure while normalizing commodity names.

        Args:
            val: The raw value to canonicalize.
            canonicalizer: Function to canonicalize commodity names.

        Returns:
            The value with commodity names canonicalized if applicable.
            String values are NOT modified (to avoid corrupting account
            names, dates, etc.).
        """
        if isinstance(val, Amount):
            canonical_currency = canonicalizer(val.currency)
            if canonical_currency != val.currency:
                return Amount(val.number, canonical_currency)
            return val
        if isinstance(val, Inventory):
            result = Inventory()
            for pos in val:
                canonical_currency = canonicalizer(pos.units.currency)
                if canonical_currency != pos.units.currency:
                    canonical_cost = None
                    if pos.cost is not None:
                        canonical_cost_currency = canonicalizer(
                            pos.cost.currency
                        )
                        if canonical_cost_currency != pos.cost.currency:
                            from beancount.core.position import Cost

                            canonical_cost = Cost(
                                pos.cost.number,
                                canonical_cost_currency,
                                pos.cost.date,
                                pos.cost.label,
                            )
                        else:
                            canonical_cost = pos.cost
                    new_pos = Position(
                        Amount(pos.units.number, canonical_currency),
                        canonical_cost,
                    )
                    result.add_position(new_pos)
                else:
                    result.add_position(pos)
            return result
        if isinstance(val, Position):
            canonical_currency = canonicalizer(val.units.currency)
            if canonical_currency != val.units.currency:
                canonical_cost = None
                if val.cost is not None:
                    canonical_cost_currency = canonicalizer(val.cost.currency)
                    if canonical_cost_currency != val.cost.currency:
                        from beancount.core.position import Cost

                        canonical_cost = Cost(
                            val.cost.number,
                            canonical_cost_currency,
                            val.cost.date,
                            val.cost.label,
                        )
                    else:
                        canonical_cost = val.cost
                return Position(
                    Amount(val.units.number, canonical_currency),
                    canonical_cost,
                )
            return val
        return val


def _serialise(
    cursor: Cursor,
    *,
    canonicalizer: Callable[[str], str] | None = None,
) -> QueryResultTable:
    """Serialise the query result.

    Args:
        cursor: The query cursor to serialise.
        canonicalizer: Optional function to canonicalize commodity names.
            When provided, ensures consistent handling of aliases across
            holdings, charts, and exports.
    """
    dtypes = [
        COLUMNS.get(c.datatype, ObjectColumn)(c.name)
        for c in cursor.description
    ]
    mappers = [d.serialise for d in dtypes]
    mapped_rows = [
        tuple(
            mapper(row[i], canonicalizer=canonicalizer)
            for i, mapper in enumerate(mappers)
        )
        for row in cursor
    ]
    return QueryResultTable(dtypes, mapped_rows)  # ty:ignore[invalid-argument-type]
