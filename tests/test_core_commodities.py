from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from fava.beans.abc import Price
from fava.beans.prices import FavaPriceMap
from fava.core.inventory import CounterInventory
from fava.core.inventory import _Amount
from fava.core.inventory import _Cost
from fava.core.inventory import _Position

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from fava.beans.abc import Directive


def test_commodity_names(example_ledger: FavaLedger) -> None:
    assert example_ledger.commodities.name("USD") == "US Dollar"
    assert example_ledger.commodities.name("NOCOMMODITY") == "NOCOMMODITY"
    assert example_ledger.commodities.name("VMMXX") == "VMMXX"


def test_commodity_precision(example_ledger: FavaLedger) -> None:
    assert example_ledger.commodities.precisions == {
        "USD": 2,
        "VMMXX": 4,
        "VACHR": 0,
    }


def _create_test_commodities_module(
    load_doc_entries: Sequence[Directive],
):
    """Create a CommoditiesModule from test entries."""
    from unittest.mock import MagicMock

    from fava.core.commodities import CommoditiesModule

    ledger = MagicMock()
    ledger.all_entries_by_type = MagicMock()
    ledger.all_entries_by_type.Commodity = [
        e for e in load_doc_entries if e.__class__.__name__ == "Commodity"
    ]

    commodities = CommoditiesModule(ledger)
    commodities.load_file()
    return commodities


def test_commodity_alias_canonicalization(
    load_doc_entries: Sequence[Directive],
) -> None:
    """
    2020-01-01 commodity BTC
      alias: "BITCOIN,btc"

    2020-01-01 commodity ETH
      alias: "ETHEREUM"
    """
    commodities = _create_test_commodities_module(load_doc_entries)
    canonical = commodities.canonical

    assert canonical("BTC") == "BTC"
    assert canonical("BITCOIN") == "BTC"
    assert canonical("btc") == "BTC"
    assert canonical("ETH") == "ETH"
    assert canonical("ETHEREUM") == "ETH"
    assert canonical("UNKNOWN") == "UNKNOWN"


def test_commodity_case_insensitive_matching(
    load_doc_entries: Sequence[Directive],
) -> None:
    """
    2020-01-01 commodity USD
      alias: "usdollar"

    2020-01-01 commodity EUR
    """
    commodities = _create_test_commodities_module(load_doc_entries)
    canonical = commodities.canonical

    assert canonical("USD") == "USD"
    assert canonical("usd") == "USD"
    assert canonical("Usd") == "USD"
    assert canonical("uSd") == "USD"
    assert canonical("USDOLLAR") == "USD"
    assert canonical("usdollar") == "USD"
    assert canonical("eur") == "EUR"
    assert canonical("Eur") == "EUR"


def test_commodity_is_alias(
    load_doc_entries: Sequence[Directive],
) -> None:
    """
    2020-01-01 commodity GOLD
      alias: "AU,gold"
    """
    commodities = _create_test_commodities_module(load_doc_entries)
    is_alias = commodities.is_alias

    assert is_alias("AU", "GOLD") is True
    assert is_alias("gold", "GOLD") is True
    assert is_alias("GOLD", "GOLD") is True
    assert is_alias("SILVER", "GOLD") is False
    assert is_alias("au", "GOLD") is True


def test_inventory_canonicalization_with_aliases(
    load_doc_entries: Sequence[Directive],
) -> None:
    """
    2020-01-01 commodity BTC
      alias: "BITCOIN,btc"

    2020-01-01 price BTC 50000 USD
    2020-01-01 price BITCOIN 50000 USD
    """
    commodities = _create_test_commodities_module(load_doc_entries)
    canonicalizer = commodities.canonical

    inv = CounterInventory()
    inv.add(("BTC", None), Decimal("1.5"))
    inv.add(("BITCOIN", None), Decimal("0.5"))
    inv.add(("btc", None), Decimal("0.3"))

    canonical_inv = inv.canonicalized(canonicalizer)
    assert ("BTC", None) in canonical_inv
    assert canonical_inv[("BTC", None)] == Decimal("2.3")
    assert ("BITCOIN", None) not in canonical_inv
    assert ("btc", None) not in canonical_inv


def test_multi_currency_conversion_with_aliases(
    load_doc_entries: Sequence[Directive],
) -> None:
    """
    2020-01-01 commodity BTC
      alias: "BITCOIN"

    2020-01-01 commodity USD

    2020-01-02 price BTC 50000 USD
    2020-01-02 price BITCOIN 50000 USD
    """
    commodities = _create_test_commodities_module(load_doc_entries)
    canonicalizer = commodities.canonical

    prices = FavaPriceMap(
        (e for e in load_doc_entries if isinstance(e, Price)),
    )

    pos1 = _Position(
        _Amount(Decimal("1"), "BTC"),
        _Cost(Decimal("40000"), "USD", None, None),
    )
    pos2 = _Position(
        _Amount(Decimal("0.5"), "BITCOIN"),
        _Cost(Decimal("45000"), "USD", None, None),
    )

    from fava.core.conversion import get_market_value
    from fava.core.conversion import convert_position

    value1 = get_market_value(pos1, prices, None, canonicalizer=canonicalizer)
    value2 = get_market_value(pos2, prices, None, canonicalizer=canonicalizer)

    assert value1.currency == "USD"
    assert value1.number == Decimal("50000")
    assert value2.currency == "USD"
    assert value2.number == Decimal("25000")

    converted1 = convert_position(
        pos1, "USD", prices, None, canonicalizer=canonicalizer
    )
    converted2 = convert_position(
        pos2, "USD", prices, None, canonicalizer=canonicalizer
    )

    assert converted1.currency == "USD"
    assert converted1.number == Decimal("50000")
    assert converted2.currency == "USD"
    assert converted2.number == Decimal("25000")


def test_inventory_reduce_with_canonicalizer(
    load_doc_entries: Sequence[Directive],
) -> None:
    """
    2020-01-01 commodity USD
    2020-01-01 commodity BTC
      alias: "BITCOIN"

    2020-01-02 price BTC 50000 USD
    """
    commodities = _create_test_commodities_module(load_doc_entries)
    canonicalizer = commodities.canonical

    prices = FavaPriceMap(
        (e for e in load_doc_entries if isinstance(e, Price)),
    )

    inv = CounterInventory()
    cost = _Cost(Decimal("40000"), "USD", None, None)
    inv.add(("BTC", cost), Decimal("1"))
    inv.add(("BITCOIN", cost), Decimal("1"))

    from fava.core.conversion import AT_VALUE

    result = AT_VALUE.apply(inv, prices, None, canonicalizer=canonicalizer)

    assert "USD" in result
    assert result["USD"] == Decimal("100000")
    assert "BTC" not in result
    assert "BITCOIN" not in result


def test_case_insensitive_price_lookup(
    load_doc_entries: Sequence[Directive],
) -> None:
    """
    2020-01-01 commodity USD
    2020-01-01 commodity EUR

    2020-01-02 price EUR 1.10 USD
    """
    commodities = _create_test_commodities_module(load_doc_entries)
    canonicalizer = commodities.canonical

    prices = FavaPriceMap(
        (e for e in load_doc_entries if isinstance(e, Price)),
    )

    pos = _Position(
        _Amount(Decimal("100"), "eur"),
        None,
    )

    from fava.core.conversion import convert_position

    converted = convert_position(
        pos, "usd", prices, None, canonicalizer=canonicalizer
    )

    assert converted.currency == "USD"
    assert converted.number == Decimal("110")
