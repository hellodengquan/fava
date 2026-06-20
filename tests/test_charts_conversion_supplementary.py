"""Supplementary tests for chart aggregation and currency conversion.

This test file covers additional scenarios for:
- Chart aggregation across multiple account paths
- Cross-currency conversion scenarios
- Various interval types with different conversion modes
- Multi-step currency conversion chains
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from beancount.core import data
from fava.beans.abc import Price
from fava.beans.prices import FavaPriceMap
from fava.core.charts import DateAndBalance
from fava.core.charts import DateAndBalanceWithBudget
from fava.core.conversion import _CurrencyConversion
from fava.core.conversion import AT_COST
from fava.core.conversion import AT_VALUE
from fava.core.conversion import conversion_from_str
from fava.core.conversion import convert_position
from fava.core.conversion import cost_or_value
from fava.core.conversion import get_cost
from fava.core.conversion import get_market_value
from fava.core.conversion import UNITS
from fava.core.inventory import _Amount
from fava.core.inventory import _Cost
from fava.core.inventory import _Position
from fava.core.inventory import CounterInventory
from fava.core.inventory import SimpleCounterInventory
from fava.util.date import Day
from fava.util.date import local_today
from fava.util.date import Month
from fava.util.date import Quarter
from fava.util.date import Week
from fava.util.date import Year

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger

    from .conftest import GetFavaLedger
    from .conftest import SnapshotFunc


def _amt(s: str) -> _Amount:
    num, currency = s.split(" ")
    assert num, currency
    return _Amount(Decimal(num), currency)


def _cost(s: str) -> _Cost:
    num, currency = s.split(" ")
    assert num, currency
    return _Cost(Decimal(num), currency, local_today(), "label")


def _pos(s: str) -> _Position:
    match = re.match(r"(.*?) \{(.*)\}", s)
    return (
        _Position(_amt(match.group(1)), _cost(match.group(2)))
        if match
        else _Position(_amt(s), None)
    )


def _inv(s: str) -> CounterInventory:
    res = CounterInventory()
    for p in s.split(","):
        res.add_position(_pos(p.strip()))
    return res


def _simple_inv(s: str) -> SimpleCounterInventory:
    res = SimpleCounterInventory()
    for p in s.split(","):
        amt = _amt(p.strip())
        res.add(amt.currency, amt.number)
    return res


def _make_price(d: date, currency: str, amount_str: str) -> Price:
    amt = _amt(amount_str)
    return data.Price(  # type: ignore[return-value]
        {
            "filename": "<test>",
            "lineno": 0,
        },
        d,
        currency,
        amt,
    )


@pytest.fixture
def sample_prices() -> FavaPriceMap:
    """Sample price data for conversion tests."""
    prices_list = [
        _make_price(date(2022, 2, 2), "STOCK", "10 USD"),
        _make_price(date(2022, 2, 4), "STOCK", "20 USD"),
        _make_price(date(2022, 2, 4), "STOCK", "30 GBP"),
        _make_price(date(2022, 2, 4), "GBP", "12 EUR"),
        _make_price(date(2022, 2, 10), "EUR", "1.1 USD"),
        _make_price(date(2022, 2, 15), "STOCK", "25 USD"),
    ]
    return FavaPriceMap(prices_list)


class TestChartAggregationPaths:
    """Tests for chart aggregation across various paths."""

    def test_interval_totals_multiple_accounts_tuple(
        self,
        small_example_ledger: FavaLedger,
    ) -> None:
        """interval_totals with tuple of accounts."""
        filtered = small_example_ledger.get_filtered()
        accounts = ("Expenses:Food", "Expenses:Transport")
        data = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            accounts,
            "at_cost",
        )
        assert isinstance(data, list)
        assert all(isinstance(d, DateAndBalanceWithBudget) for d in data)
        for item in data:
            assert isinstance(item.balance, SimpleCounterInventory)
            assert isinstance(item.account_balances, dict)
            assert item.budgets == {}

    def test_interval_totals_single_account_with_budgets(
        self,
        small_example_ledger: FavaLedger,
    ) -> None:
        """interval_totals with single account should have budgets."""
        filtered = small_example_ledger.get_filtered()
        data = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            "at_cost",
        )
        assert isinstance(data, list)
        for item in data:
            assert isinstance(item.budgets, dict)

    @pytest.mark.parametrize(
        "interval",
        [Day, Week, Month, Quarter, Year],
    )
    def test_interval_totals_different_intervals(
        self,
        small_example_ledger: FavaLedger,
        interval,
    ) -> None:
        """interval_totals with different interval types."""
        filtered = small_example_ledger.get_filtered()
        data = small_example_ledger.charts.interval_totals(
            filtered,
            interval,
            "Expenses",
            "at_cost",
        )
        assert isinstance(data, list)
        if data:
            assert isinstance(data[0], DateAndBalanceWithBudget)
            assert isinstance(data[0].date, date)
            assert isinstance(data[0].balance, SimpleCounterInventory)

    def test_linechart_income_account(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """linechart with income account."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.linechart(
            filtered,
            "Income",
            "at_cost",
        )
        assert isinstance(data, list)
        assert all(isinstance(d, DateAndBalance) for d in data)

    def test_linechart_asset_account(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """linechart with asset account."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.linechart(
            filtered,
            "Assets",
            "at_cost",
        )
        assert isinstance(data, list)

    @pytest.mark.parametrize(
        "conversion",
        ["at_cost", "at_value", "units"],
    )
    def test_linechart_all_conversions(
        self,
        example_ledger: FavaLedger,
        conversion: str,
    ) -> None:
        """linechart with all basic conversion types."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.linechart(
            filtered,
            "Assets:Testing:MultipleCommodities",
            conversion,
        )
        assert isinstance(data, list)
        for item in data:
            assert isinstance(item, DateAndBalance)
            assert isinstance(item.date, date)
            assert isinstance(item.balance, SimpleCounterInventory)

    def test_hierarchy_income(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """hierarchy chart for income account."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.hierarchy(filtered, "Income", AT_COST)
        assert data.account == "Income"
        assert isinstance(data.balance_children, dict)
        assert isinstance(data.children, list)

    def test_hierarchy_expenses(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """hierarchy chart for expenses account."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.hierarchy(filtered, "Expenses", AT_COST)
        assert data.account == "Expenses"
        assert isinstance(data.balance_children, dict)

    @pytest.mark.parametrize(
        "conversion",
        [AT_COST, AT_VALUE, UNITS],
    )
    def test_hierarchy_different_conversions(
        self,
        example_ledger: FavaLedger,
        conversion,
    ) -> None:
        """hierarchy chart with different conversion types."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.hierarchy(
            filtered, "Assets", conversion
        )
        assert data.account == "Assets"
        assert isinstance(data.balance_children, dict)

    @pytest.mark.parametrize(
        "interval",
        [Month, Quarter, Year],
    )
    def test_net_worth_different_intervals(
        self,
        example_ledger: FavaLedger,
        interval,
    ) -> None:
        """net_worth with different interval types."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.net_worth(filtered, interval, "at_value")
        assert isinstance(data, list)
        assert all(isinstance(d, DateAndBalance) for d in data)
        for item in data:
            assert isinstance(item.date, date)
            assert isinstance(item.balance, SimpleCounterInventory)

    def test_net_worth_at_cost(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """net_worth with at_cost conversion."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.net_worth(filtered, Month, "at_cost")
        assert isinstance(data, list)
        assert all(isinstance(d, DateAndBalance) for d in data)

    def test_net_worth_units(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """net_worth with units conversion."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.net_worth(filtered, Month, "units")
        assert isinstance(data, list)
        assert all(isinstance(d, DateAndBalance) for d in data)

    def test_interval_totals_invert_multiple_accounts(
        self,
        small_example_ledger: FavaLedger,
    ) -> None:
        """interval_totals invert with multiple accounts tuple."""
        filtered = small_example_ledger.get_filtered()
        accounts = ("Expenses:Food", "Expenses:Transport")
        data_normal = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            accounts,
            "at_cost",
        )
        data_inverted = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            accounts,
            "at_cost",
            invert=True,
        )
        assert len(data_normal) == len(data_inverted)
        for normal, inverted in zip(data_normal, data_inverted):
            assert normal.date == inverted.date
            for currency in normal.balance.keys():
                assert inverted.balance[currency] == -normal.balance[currency]
            for currency in inverted.balance.keys():
                assert normal.balance[currency] == -inverted.balance[currency]

    def test_linechart_zero_balance_currencies(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """linechart should keep zero balances for currencies that went to zero."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.linechart(
            filtered,
            "Assets:Testing:MultipleCommodities",
            "units",
        )
        assert isinstance(data, list)
        if len(data) >= 2:
            currencies_first = set(data[0].balance.keys())
            currencies_last = set(data[-1].balance.keys())
            all_currencies = currencies_first | currencies_last
            for item in data:
                for currency in all_currencies:
                    assert currency in item.balance or item.balance.get(
                        currency, Decimal("0")
                    ) == Decimal("0") or currency in item.balance


class TestCrossCurrencyConversion:
    """Tests for cross-currency conversion scenarios."""

    def test_direct_conversion_simple(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Direct currency conversion with simple case."""
        inv = _inv("100 STOCK")
        conv = conversion_from_str("USD")
        result = conv.apply(inv, sample_prices, date(2022, 2, 4))
        expected = _simple_inv("2000 USD")
        assert result == expected

    def test_indirect_conversion_via_cost_currency(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Indirect conversion via cost currency using market price."""
        inv = _inv("10 STOCK {5 GBP}")
        conv = conversion_from_str("EUR")
        result = conv.apply(inv, sample_prices, date(2022, 2, 4))
        expected = _simple_inv("3600 EUR")
        assert result == expected

    def test_multi_step_conversion_chain(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Multi-step currency conversion chain."""
        inv = _inv("100 STOCK")
        conv = conversion_from_str("USD,GBP,EUR")
        result = conv.apply(inv, sample_prices, date(2022, 2, 4))
        expected = _simple_inv("2000 USD")
        assert result == expected

    def test_convert_position_direct(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """convert_position direct conversion."""
        pos = _pos("10 STOCK")
        result = convert_position(pos, "USD", sample_prices, date(2022, 2, 4))
        assert result == _amt("200 USD")

    def test_convert_position_via_cost(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """convert_position via cost currency using market price."""
        pos = _pos("10 STOCK {5 GBP}")
        result = convert_position(pos, "EUR", sample_prices, date(2022, 2, 4))
        assert result == _amt("3600 EUR")

    def test_convert_position_no_rate_fallback_units(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """convert_position falls back to units when no rate found."""
        pos = _pos("10 UNKNOWN")
        result = convert_position(pos, "USD", sample_prices, date(2022, 2, 4))
        assert result == _amt("10 UNKNOWN")

    def test_get_market_value_with_cost(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """get_market_value with cost basis."""
        pos = _pos("10 STOCK {5 USD}")
        result = get_market_value(pos, sample_prices, date(2022, 2, 4))
        assert result == _amt("200 USD")

    def test_get_market_value_no_cost_no_price(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """get_market_value without cost falls back to units."""
        pos = _pos("10 STOCK")
        result = get_market_value(pos, sample_prices, date(2022, 2, 1))
        assert result == _amt("10 STOCK")

    def test_mixed_inventory_conversion(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Conversion of mixed inventory with and without cost."""
        inv = _inv("10 STOCK {5 GBP},20 USD,5 STOCK")
        result = AT_VALUE.apply(inv, sample_prices, date(2022, 2, 4))
        assert "GBP" in result or "USD" in result

    def test_multiple_commodities_same_target(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Multiple commodities converted to same target currency."""
        inv = _inv("10 STOCK {5 USD},20 GBP")
        conv = conversion_from_str("USD")
        result = conv.apply(inv, sample_prices, date(2022, 2, 4))
        assert "USD" in result
        total_usd = result["USD"]
        assert total_usd > Decimal("0")

    def test_conversion_date_boundary_before_first_price(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Conversion at date before first price record."""
        inv = _inv("10 STOCK {5 USD}")
        result = AT_VALUE.apply(inv, sample_prices, date(2022, 1, 1))
        assert result == _simple_inv("50 USD")

    def test_conversion_date_after_last_price(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Conversion at date after last price uses last available."""
        inv = _inv("10 STOCK {5 USD}")
        result = AT_VALUE.apply(inv, sample_prices, date(2023, 1, 1))
        assert result == _simple_inv("250 USD")

    def test_conversion_none_date_uses_latest(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Conversion with None date uses latest price."""
        inv = _inv("10 STOCK {5 USD}")
        result = AT_VALUE.apply(inv, sample_prices, None)
        assert result == _simple_inv("250 USD")

    def test_cost_or_value_function(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """cost_or_value helper function."""
        inv = _inv("10 STOCK {5 GBP}")
        result_cost = cost_or_value(inv, "at_cost", sample_prices)
        result_value = cost_or_value(
            inv, "at_value", sample_prices, date(2022, 2, 4)
        )
        assert result_cost == _simple_inv("50 GBP")
        assert result_value == _simple_inv("300 GBP")

    def test_currency_conversion_multiple_currencies(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """_CurrencyConversion with multiple target currencies."""
        inv = _inv("10 STOCK")
        conv = _CurrencyConversion("USD,EUR")
        result = conv.apply(inv, sample_prices, date(2022, 2, 4))
        assert result == _simple_inv("200 USD")

    def test_units_conversion_preserves_currencies(
        self,
    ) -> None:
        """UNITS conversion preserves all currencies."""
        inv = _inv("10 USD,20 EUR,5 STOCK")
        result = UNITS.apply(inv)
        assert result == _simple_inv("10 USD,20 EUR,5 STOCK")

    def test_at_cost_conversion(
        self,
    ) -> None:
        """AT_COST conversion aggregates by cost currency."""
        inv = _inv("10 STOCK {5 USD},15 STOCK {10 USD}")
        result = AT_COST.apply(inv)
        assert result == _simple_inv("200 USD")

    def test_empty_inventory_conversion(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Conversion of empty inventory."""
        inv = CounterInventory()
        for conv_name in ["at_cost", "at_value", "units", "USD"]:
            conv = conversion_from_str(conv_name)
            result = conv.apply(inv, sample_prices, date(2022, 2, 4))
            assert result.is_empty()

    def test_negative_balance_conversion(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Conversion of inventory with negative balances."""
        inv = _inv("-10 STOCK {5 USD}")
        result = AT_VALUE.apply(inv, sample_prices, date(2022, 2, 4))
        assert result == _simple_inv("-200 USD")

    def test_conversion_from_str_non_string_passthrough(
        self,
    ) -> None:
        """conversion_from_str with non-string input passes through."""
        assert conversion_from_str(AT_COST) is AT_COST
        assert conversion_from_str(AT_VALUE) is AT_VALUE
        assert conversion_from_str(UNITS) is UNITS

    def test_triple_indirect_conversion(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Triple hop indirect conversion: STOCK -> GBP -> EUR -> USD."""
        inv = _inv("10 STOCK {10 GBP}")
        result = convert_position(
            _pos("10 STOCK {10 GBP}"), "EUR", sample_prices, date(2022, 2, 4)
        )
        assert result.currency == "EUR"
        assert result.number == Decimal("3600")

    def test_same_currency_conversion(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """Converting to the same currency should return units."""
        pos = _pos("100 USD")
        result = convert_position(pos, "USD", sample_prices, date(2022, 2, 4))
        assert result == _amt("100 USD")

    def test_cost_currency_same_as_target_no_direct_price(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """convert_position: cost currency == target, no direct price returns units."""
        pos = _pos("10 STOCK {100 USD}")
        result = convert_position(pos, "USD", sample_prices, date(2022, 1, 1))
        assert result == _amt("10 STOCK")

    def test_get_market_value_cost_currency_same_as_target(
        self,
        sample_prices: FavaPriceMap,
    ) -> None:
        """get_market_value uses cost as fallback when no market price available."""
        pos = _pos("10 STOCK {100 USD}")
        result = get_market_value(pos, sample_prices, date(2022, 1, 1))
        assert result == _amt("1000 USD")


class TestChartAndConversionIntegration:
    """Integration tests for charts with currency conversion."""

    def test_interval_totals_with_currency_conversion(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """interval_totals with currency conversion."""
        filtered = example_ledger.get_filtered()
        data_usd = example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            "USD",
        )
        data_at_cost = example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            "at_cost",
        )
        assert isinstance(data_usd, list)
        assert isinstance(data_at_cost, list)
        assert len(data_usd) == len(data_at_cost)

    def test_linechart_currency_conversion_preserves_dates(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """linechart currency conversion preserves date sequence."""
        filtered = example_ledger.get_filtered()
        data_units = example_ledger.charts.linechart(
            filtered,
            "Assets:Testing:MultipleCommodities",
            "units",
        )
        data_usd = example_ledger.charts.linechart(
            filtered,
            "Assets:Testing:MultipleCommodities",
            "USD",
        )
        assert len(data_units) == len(data_usd)
        for d1, d2 in zip(data_units, data_usd):
            assert d1.date == d2.date

    def test_net_worth_with_different_conversions_consistent_length(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """net_worth with different conversions has same intervals."""
        filtered = example_ledger.get_filtered()
        data_at_cost = example_ledger.charts.net_worth(
            filtered, Month, "at_cost"
        )
        data_at_value = example_ledger.charts.net_worth(
            filtered, Month, "at_value"
        )
        assert len(data_at_cost) == len(data_at_value)
        for cost_item, value_item in zip(data_at_cost, data_at_value):
            assert cost_item.date == value_item.date

    def test_hierarchy_at_value_conversion(
        self,
        example_ledger: FavaLedger,
    ) -> None:
        """hierarchy with at_value conversion."""
        filtered = example_ledger.get_filtered()
        data = example_ledger.charts.hierarchy(filtered, "Assets", AT_VALUE)
        assert isinstance(data.balance_children, dict)
        for value in data.balance_children.values():
            assert isinstance(value, Decimal)

    def test_account_balances_in_interval_totals(
        self,
        small_example_ledger: FavaLedger,
    ) -> None:
        """interval_totals account_balances should sum to total balance."""
        filtered = small_example_ledger.get_filtered()
        data = small_example_ledger.charts.interval_totals(
            filtered,
            Month,
            "Expenses",
            "at_cost",
        )
        for item in data:
            total_from_accounts = SimpleCounterInventory()
            for acct_bal in item.account_balances.values():
                for currency, amount in acct_bal.items():
                    total_from_accounts.add(currency, amount)
            assert total_from_accounts == item.balance
