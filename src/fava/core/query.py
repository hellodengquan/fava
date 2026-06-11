"""Query result types."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from beancount.core.amount import Amount
from beancount.core.inventory import Inventory
from beancount.core.position import Position

from fava.core.conversion import UNITS

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from typing import Any
    from typing import Literal
    from typing import TypeAlias
    from typing import TypeVar

    from fava.core.inventory import SimpleCounterInventory

    T = TypeVar("T")

    QueryRowValue = Any

    # This is not a complete enumeration of all possible column types but just
    # of the ones we pass in some specific serialisation to the frontend.
    # Everything unknown will be stringified (by ObjectColumn).
    SerialisedQueryRowValue = (
        bool
        | int
        | str
        | datetime.date
        | Decimal
        | Position
        | SimpleCounterInventory
        | None
    )


@dataclass(frozen=True)
class QueryResultTable:
    """Table query result."""

    types: list[BaseColumn]
    rows: list[tuple[SerialisedQueryRowValue, ...]]
    t: Literal["table"] = "table"


@dataclass(frozen=True)
class QueryResultText:
    """Text query result."""

    contents: str
    t: Literal["string"] = "string"


QueryResult: TypeAlias = QueryResultTable | QueryResultText


@dataclass(frozen=True)
class BaseColumn:
    """A query column."""

    name: str
    dtype: str

    @staticmethod
    def serialise(
        val: QueryRowValue,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SerialisedQueryRowValue:
        """Serialiseable version of the column value.

        Args:
            val: The value to serialise.
            canonicalizer: Optional function to canonicalize commodity names,
                ensuring consistent handling of aliases across holdings,
                charts, and exports.
        """
        return val  # type: ignore[no-any-return]


@dataclass(frozen=True)
class BoolColumn(BaseColumn):
    """A boolean query column."""

    dtype: str = "bool"


@dataclass(frozen=True)
class DecimalColumn(BaseColumn):
    """A Decimal query column."""

    dtype: str = "Decimal"


@dataclass(frozen=True)
class IntColumn(BaseColumn):
    """A int query column."""

    dtype: str = "int"


@dataclass(frozen=True)
class StrColumn(BaseColumn):
    """A str query column."""

    dtype: str = "str"


@dataclass(frozen=True)
class DateColumn(BaseColumn):
    """A date query column."""

    dtype: str = "date"


@dataclass(frozen=True)
class PositionColumn(BaseColumn):
    """A Position query column."""

    dtype: str = "Position"


@dataclass(frozen=True)
class SetColumn(BaseColumn):
    """A set query column."""

    dtype: str = "set"


@dataclass(frozen=True)
class AmountColumn(BaseColumn):
    """An amount query column."""

    dtype: str = "Amount"


@dataclass(frozen=True)
class ObjectColumn(BaseColumn):
    """An object query column."""

    dtype: str = "object"

    @staticmethod
    def serialise(
        val: object,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> str:
        """Serialise an object of unknown type to a string.

        Args:
            val: The value to serialise.
            canonicalizer: Optional function to canonicalize commodity names.
                Not used for generic object serialisation but accepted for
                interface consistency.
        """
        return str(val)


@dataclass(frozen=True)
class InventoryColumn(BaseColumn):
    """A str query column."""

    dtype: str = "Inventory"

    @staticmethod
    def serialise(
        val: Inventory | None,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SimpleCounterInventory | None:
        """Serialise an inventory.

        Args:
            val: The inventory to serialise.
            canonicalizer: Optional function to canonicalize commodity names.
                When provided, ensures that aliases of the same commodity are
                aggregated together, providing consistent totals across
                holdings, charts, and exports.
        """
        if val is None:
            return None
        result = UNITS.apply_inventory(val, canonicalizer=canonicalizer)
        return result


COLUMNS = {
    Amount: AmountColumn,
    Decimal: DecimalColumn,
    Inventory: InventoryColumn,
    Position: PositionColumn,
    bool: BoolColumn,
    datetime.date: DateColumn,
    int: IntColumn,
    set: SetColumn,
    str: StrColumn,
}
