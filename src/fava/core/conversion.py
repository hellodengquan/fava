"""Commodity conversion helpers for Fava.

All functions in this module will be automatically added as template filters.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Callable
from typing import TYPE_CHECKING

from fava.core.inventory import _Amount
from fava.core.inventory import SimpleCounterInventory

try:
    from typing import override
except ImportError:  # pragma: no cover
    from typing_extensions import override

if TYPE_CHECKING:  # pragma: no cover
    import datetime

    from beancount.core.inventory import Inventory

    from fava.beans.prices import FavaPriceMap
    from fava.beans.protocols import Amount
    from fava.beans.protocols import Position
    from fava.core.inventory import CounterInventory


def get_cost(
    pos: Position,
    canonicalizer: Callable[[str], str] | None = None,
) -> Amount:
    """Return the total cost of a Position.

    Args:
        pos: The position to get the cost of.
        canonicalizer: Optional function to canonicalize commodity names.
            When provided, the cost currency will be canonicalized, ensuring
            consistent cost aggregation across aliases.
    """
    cost_ = pos.cost
    if cost_ is not None:
        currency = cost_.currency
        if canonicalizer is not None:
            currency = canonicalizer(currency)
        return _Amount(cost_.number * pos.units.number, currency)
    if canonicalizer is not None:
        canonical_units_currency = canonicalizer(pos.units.currency)
        if canonical_units_currency != pos.units.currency:
            return _Amount(pos.units.number, canonical_units_currency)
    return pos.units


def get_market_value(
    pos: Position,
    prices: FavaPriceMap,
    date: datetime.date | None = None,
    canonicalizer: Callable[[str], str] | None = None,
) -> Amount:
    """Get the market value of a Position.

    This differs from the convert.get_value function in Beancount by returning
    the cost value if no price can be found.

    Args:
        pos: A Position.
        prices: A FavaPriceMap
        date: A datetime.date instance to evaluate the value at, or None.
        canonicalizer: Optional function to canonicalize commodity names
            for price lookup. This ensures that commodity aliases resolve
            to the correct price data.

    Returns:
        An Amount, with value converted or if the conversion failed just the
        cost value (or the units if the position has no cost).
    """
    units_ = pos.units
    cost_ = pos.cost

    if cost_ is not None:
        value_currency = cost_.currency
        base_currency = units_.currency
        quote_currency = value_currency

        if canonicalizer is not None:
            base_currency = canonicalizer(base_currency)
            quote_currency = canonicalizer(quote_currency)

        base_quote = (base_currency, quote_currency)
        price_number = prices.get_price(base_quote, date)
        if price_number is not None:
            canonical_value_currency = (
                canonicalizer(value_currency)
                if canonicalizer is not None
                else value_currency
            )
            return _Amount(
                units_.number * price_number,
                canonical_value_currency,
            )
        return _Amount(
            units_.number * cost_.number,
            canonicalizer(value_currency)
            if canonicalizer is not None
            else value_currency,
        )
    if canonicalizer is not None:
        canonical_units_currency = canonicalizer(units_.currency)
        if canonical_units_currency != units_.currency:
            return _Amount(units_.number, canonical_units_currency)
    return units_


def convert_position(
    pos: Position,
    target_currency: str,
    prices: FavaPriceMap,
    date: datetime.date | None = None,
    canonicalizer: Callable[[str], str] | None = None,
) -> Amount:
    """Get the value of a Position in a particular currency.

    Args:
        pos: A Position.
        target_currency: The target currency to convert to.
        prices: A FavaPriceMap
        date: A datetime.date instance to evaluate the value at, or None.
        canonicalizer: Optional function to canonicalize commodity names
            for price lookup. This ensures that commodity aliases resolve
            to the correct price data.

    Returns:
        An Amount, with value converted or if the conversion failed just the
        cost value (or the units if the position has no cost).
    """
    units_ = pos.units
    canonical_target = (
        canonicalizer(target_currency)
        if canonicalizer is not None
        else target_currency
    )

    base_currency = units_.currency
    if canonicalizer is not None:
        base_currency = canonicalizer(base_currency)

    # try the direct conversion
    base_quote = (base_currency, canonical_target)
    price_number = prices.get_price(base_quote, date)
    if price_number is not None:
        return _Amount(units_.number * price_number, canonical_target)

    cost_ = pos.cost
    if cost_ is not None:
        cost_currency = cost_.currency
        if canonicalizer is not None:
            cost_currency = canonicalizer(cost_currency)
        if cost_currency != canonical_target:
            base_quote1 = (base_currency, cost_currency)
            rate1 = prices.get_price(base_quote1, date)
            if rate1 is not None:
                base_quote2 = (cost_currency, canonical_target)
                rate2 = prices.get_price(base_quote2, date)
                if rate2 is not None:
                    return _Amount(
                        units_.number * rate1 * rate2,
                        canonical_target,
                    )
    if canonicalizer is not None:
        canonical_units_currency = canonicalizer(units_.currency)
        if canonical_units_currency != units_.currency:
            return _Amount(units_.number, canonical_units_currency)
    return units_


class Conversion(ABC):
    """A conversion."""

    @abstractmethod
    def apply(
        self,
        inventory: CounterInventory,
        prices: FavaPriceMap,
        date: datetime.date | None = None,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SimpleCounterInventory:
        """Apply the conversion to an inventory (CounterInventory).

        Args:
            inventory: The inventory to convert.
            prices: The price map to use for conversions.
            date: The date to use for price lookup.
            canonicalizer: Optional function to canonicalize commodity names.
                When provided, ensures consistent commodity handling across
                aliases and different name variations.
        """


class _AtCostConversion(Conversion):
    @override
    def apply(
        self,
        inventory: CounterInventory,
        prices: FavaPriceMap | None = None,
        date: datetime.date | None = None,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SimpleCounterInventory:
        return inventory.reduce(get_cost, canonicalizer)


class _AtValueConversion(Conversion):
    @override
    def apply(
        self,
        inventory: CounterInventory,
        prices: FavaPriceMap,
        date: datetime.date | None = None,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SimpleCounterInventory:
        return inventory.reduce(
            get_market_value, prices, date, canonicalizer
        )


class _UnitsConversion(Conversion):
    @override
    def apply(
        self,
        inventory: CounterInventory,
        prices: FavaPriceMap | None = None,
        date: datetime.date | None = None,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SimpleCounterInventory:
        counter = SimpleCounterInventory()
        for (currency, _cost), number in inventory.items():
            key = canonicalizer(currency) if canonicalizer else currency
            counter.add(key, number)
        return counter

    def apply_inventory(
        self,
        inventory: Inventory,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SimpleCounterInventory:
        """Apply the conversion to an Beancount Inventory."""
        counter = SimpleCounterInventory()
        for pos in inventory:
            currency = (
                canonicalizer(pos.units.currency)
                if canonicalizer
                else pos.units.currency
            )
            counter.add(currency, pos.units.number)
        return counter


class _CurrencyConversion(Conversion):
    """Conversion to a list of currencies."""

    def __init__(self, value: str) -> None:
        self._currencies = tuple(value.split(","))

    @override
    def apply(
        self,
        inventory: CounterInventory,
        prices: FavaPriceMap,
        date: datetime.date | None = None,
        *,
        canonicalizer: Callable[[str], str] | None = None,
    ) -> SimpleCounterInventory:
        currencies = iter(self._currencies)
        currency = next(currencies)
        res = inventory.reduce(
            convert_position, currency, prices, date, canonicalizer
        )
        for currency in currencies:
            res = res.reduce(
                convert_position, currency, prices, date, canonicalizer
            )
        return res


#: Convert position to its total cost.
AT_COST = _AtCostConversion()
#: Convert position to its market value.
AT_VALUE = _AtValueConversion()
#: Convert position to its units.
UNITS = _UnitsConversion()


def conversion_from_str(value: str | Conversion) -> Conversion:
    """Parse a conversion string."""
    if not isinstance(value, str):
        return value
    if value == "at_cost":
        return AT_COST
    if value == "at_value":
        return AT_VALUE
    if value == "units":
        return UNITS

    return _CurrencyConversion(value)


def cost_or_value(
    inventory: CounterInventory,
    conversion: str | Conversion,
    prices: FavaPriceMap,
    date: datetime.date | None = None,
    *,
    canonicalizer: Callable[[str], str] | None = None,
) -> SimpleCounterInventory:
    """Get the cost or value of an inventory.

    Args:
        inventory: The inventory to convert.
        conversion: The conversion to apply.
        prices: The price map to use.
        date: The date to use for price lookup.
        canonicalizer: Optional function to canonicalize commodity names.
            When provided, ensures consistent commodity handling across
            aliases and different name variations.

    Returns:
        The converted inventory.
    """
    conversion = conversion_from_str(conversion)
    return conversion.apply(inventory, prices, date, canonicalizer=canonicalizer)
