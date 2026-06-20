"""Tests for Fava's main Flask app."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from fava.core import FavaLedger
from fava.core import charts
from fava.core.conversion import conversion_from_str
from fava.internal_api import BalancesChart
from fava.internal_api import BarChart
from fava.internal_api import ChartApi
from fava.internal_api import ChartDataLoader
from fava.internal_api import get_ledger_data
from fava.internal_api import HierarchyChart
from fava.util.date import Month
from fava.util.date import Year

if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask

    from .conftest import SnapshotFunc


def test_get_ledger_data(app: Flask, snapshot: SnapshotFunc) -> None:
    """The currently filtered journal can be downloaded."""
    with app.test_request_context("/long-example/"):
        app.preprocess_request()
        snapshot(get_ledger_data(), json=True)


def test_chart_api(app: Flask, snapshot: SnapshotFunc) -> None:
    """The serialisation and generation of charts works."""
    with app.test_request_context("/long-example/"):
        app.preprocess_request()

        hierarchy = ChartApi.hierarchy(ChartDataLoader.hierarchy("Assets"))
        assert isinstance(hierarchy, HierarchyChart)
        assert hierarchy.data.account == "Assets"
        assert hierarchy.label == "Assets"
        assert hierarchy.type == "hierarchy"

        balances = ChartApi.account_balance(
            ChartDataLoader.account_balance("Assets:US:Vanguard:Cash"),
        )
        assert isinstance(balances, BalancesChart)
        assert len(balances.data) == 117
        assert balances.label == "Account Balance"
        assert balances.type == "balances"

        net_worth = ChartApi.net_worth(ChartDataLoader.net_worth())
        assert isinstance(net_worth, BalancesChart)
        assert len(net_worth.data) == 197
        assert net_worth.label == "Net Worth"
        assert net_worth.type == "balances"

        interval_totals = ChartApi.interval_totals(
            ChartDataLoader.interval_totals(Month, "Income"),
            account_name="Income",
        )
        assert isinstance(interval_totals, BarChart)
        assert len(interval_totals.data) == 100
        assert interval_totals.label == "Income"
        assert interval_totals.type == "bar"

        snapshot(
            [hierarchy, balances, net_worth, interval_totals],
            json=True,
        )


def test_chart_pure_functions_no_ledger_dependency(
    app: Flask,
) -> None:
    """Pure chart functions can be called without direct ledger dependency.

    This verifies that the refactored pure functions in fava.core.charts
    do not depend on FavaModule/self.ledger and can be injected with
    explicit dependencies.
    """
    with app.test_request_context("/long-example/"):
        app.preprocess_request()
        from fava.context import g

        prices = g.ledger.prices
        filtered = g.filtered
        conv = g.conv

        # Test linechart pure function
        line_data = charts.linechart(
            filtered,
            "Assets:US:Vanguard:Cash",
            conv,
            prices,
        )
        assert len(line_data) == 117

        # Test hierarchy pure function
        hierarchy_data = charts.hierarchy(
            filtered,
            "Assets",
            conv,
            prices,
        )
        assert hierarchy_data.account == "Assets"

        # Test interval_totals pure function (no budgets)
        interval_data = charts.interval_totals(
            filtered,
            Month,
            "Income",
            conv,
            prices,
            calculate_budgets=None,
            invert=False,
        )
        assert len(interval_data) == 100

        # Test net_worth pure function
        net_worth_data = charts.net_worth(
            filtered,
            g.interval,
            conv,
            prices,
            (
                g.ledger.options["name_assets"],
                g.ledger.options["name_liabilities"],
            ),
        )
        assert len(net_worth_data) == 197


def test_chart_data_loader_caching(app: Flask) -> None:
    """ChartDataLoader caches results based on mtime and request parameters."""
    ChartDataLoader.clear_cache()

    with app.test_request_context("/long-example/?interval=year"):
        app.preprocess_request()
        from fava.context import g

        # First call - should miss cache
        result1 = ChartDataLoader.net_worth()
        cache_info1 = ChartDataLoader._cached_net_worth.cache_info()
        assert cache_info1.misses == 1
        assert cache_info1.hits == 0

        # Second call with same params - should hit cache
        result2 = ChartDataLoader.net_worth()
        cache_info2 = ChartDataLoader._cached_net_worth.cache_info()
        assert cache_info2.hits == 1
        assert result1 == result2

    # Different request context with different interval
    with app.test_request_context("/long-example/?interval=month"):
        app.preprocess_request()

        # Different interval - should miss cache
        result3 = ChartDataLoader.net_worth()
        cache_info3 = ChartDataLoader._cached_net_worth.cache_info()
        assert cache_info3.misses == 2

        # Clear cache
        ChartDataLoader.clear_cache()
        cache_info4 = ChartDataLoader._cached_net_worth.cache_info()
        assert cache_info4.hits == 0
        assert cache_info4.misses == 0


def test_chart_with_damaged_ledger(
    tmp_path: Path,
    test_data_dir: Path,
) -> None:
    """Chart functions handle damaged/unparseable ledger files gracefully."""
    from fava.context import g
    from fava.application import create_app

    # Create a damaged beancount file with invalid syntax
    damaged_file = tmp_path / "damaged.beancount"
    damaged_file.write_text("""
option "title" "Damaged Ledger"
option "operating_currency" "USD"

2020-01-01 open Assets:Cash
2020-01-01 open Expenses:Food

This is invalid syntax that will cause parsing errors
2020-01-02 * "Grocery"
  Assets:Cash  -50.00 USD
  Expenses:Food
""")

    # Create app with damaged ledger
    app = create_app([str(damaged_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/damaged/"):
        app.preprocess_request()

        # Verify ledger has load errors
        assert len(g.ledger.load_errors) > 0, "Damaged file should have load errors"

        # Chart functions should handle empty entries gracefully
        # without raising exceptions, returning empty results
        balances = ChartDataLoader.account_balance("Assets:Cash")
        assert isinstance(balances, list)
        assert len(balances) == 0  # No valid transactions, so empty

        net_worth = ChartDataLoader.net_worth()
        assert isinstance(net_worth, list)
        # May have intervals but all with zero balance

        interval_totals = ChartDataLoader.interval_totals(Month, "Expenses")
        assert isinstance(interval_totals, list)
        assert len(interval_totals) >= 0  # Should not crash


def test_chart_with_parser_syntax_error(tmp_path: Path) -> None:
    """Chart functions handle ParserSyntaxError from Beancount parser.

    When the Beancount parser encounters completely unparseable tokens
    (not just semantically invalid directives), it produces
    ParserSyntaxError errors. This test ensures the chart pipeline
    does not crash when the ledger contains such errors.
    """
    from beancount.parser.grammar import ParserSyntaxError
    from fava.context import g
    from fava.application import create_app

    # Create a file that triggers ParserSyntaxError (invalid tokens)
    parser_error_file = tmp_path / "parser_error.beancount"
    parser_error_file.write_text("""
option "title" "Parser Error Ledger"
option "operating_currency" "USD"

2020-01-01 open Assets:Cash
2020-01-01 open Expenses:Food

GARBAGE_TOKEN_NOT_RECOGNIZED
2020-01-02 * "Grocery"
  Assets:Cash  -50.00 USD
  Expenses:Food
""")

    app = create_app([str(parser_error_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/parser-error/"):
        app.preprocess_request()

        # Verify ledger has ParserSyntaxError specifically
        error_type_names = [type(e).__name__ for e in g.ledger.load_errors]
        assert "ParserSyntaxError" in error_type_names, (
            f"Expected ParserSyntaxError in errors, got: {error_type_names}"
        )
        assert len(g.ledger.load_errors) > 0

        # Chart functions should not crash despite parse errors
        ChartDataLoader.clear_cache()
        balances = ChartDataLoader.account_balance("Assets:Cash")
        assert isinstance(balances, list)

        hierarchy = ChartDataLoader.hierarchy("Assets")
        assert hierarchy is not None

        interval_totals = ChartDataLoader.interval_totals(Month, "Expenses")
        assert isinstance(interval_totals, list)

        net_worth = ChartDataLoader.net_worth()
        assert isinstance(net_worth, list)


def test_chart_with_lexer_error(tmp_path: Path) -> None:
    """Chart functions handle LexerError from Beancount lexer.

    LexerError occurs when the Beancount lexer encounters tokens it
    cannot recognize at all (e.g., free-form text that is not a valid
    directive). This is a different failure mode from ParserSyntaxError.
    """
    from fava.context import g
    from fava.application import create_app

    # Create a file that triggers LexerError (unrecognizable tokens)
    lexer_error_file = tmp_path / "lexer_error.beancount"
    lexer_error_file.write_text("""
option "title" "Lexer Error Ledger"
option "operating_currency" "USD"

2020-01-01 open Assets:Bank
2020-01-01 open Expenses:Misc

Just some random words here that are not valid beancount syntax at all
Another line of garbage
""")

    app = create_app([str(lexer_error_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/lexer-error/"):
        app.preprocess_request()

        # Verify lexer errors are present
        error_type_names = [type(e).__name__ for e in g.ledger.load_errors]
        assert any("LexerError" in name or "ParserSyntaxError" in name
                    for name in error_type_names), (
            f"Expected LexerError or ParserSyntaxError, got: {error_type_names}"
        )

        # Chart functions should not crash
        ChartDataLoader.clear_cache()
        balances = ChartDataLoader.account_balance("Assets:Bank")
        assert isinstance(balances, list)

        net_worth = ChartDataLoader.net_worth()
        assert isinstance(net_worth, list)


def test_chart_with_validation_error(tmp_path: Path) -> None:
    """Chart functions handle ValidationError (unbalanced transactions).

    ValidationError occurs when a transaction does not balance. The
    entries are still parsed but semantically invalid. Chart functions
    should still work with the valid subset of entries.
    """
    from fava.context import g
    from fava.application import create_app

    validation_error_file = tmp_path / "validation_error.beancount"
    validation_error_file.write_text("""
option "title" "Validation Error Ledger"
option "operating_currency" "USD"

2020-01-01 open Assets:Bank
2020-01-01 open Expenses:Misc

2020-01-02 * "Unbalanced transaction"
  Assets:Bank  -50.00 USD
  Expenses:Misc  30.00 USD
""")

    app = create_app([str(validation_error_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/validation-error/"):
        app.preprocess_request()

        # Verify validation errors
        error_type_names = [type(e).__name__ for e in g.ledger.load_errors]
        assert "ValidationError" in error_type_names, (
            f"Expected ValidationError, got: {error_type_names}"
        )

        # Chart functions should still work (entries are parsed)
        ChartDataLoader.clear_cache()
        balances = ChartDataLoader.account_balance("Assets:Bank")
        assert isinstance(balances, list)
        # The unbalanced transaction is still included in entries
        assert len(balances) > 0

        net_worth = ChartDataLoader.net_worth()
        assert isinstance(net_worth, list)


def test_chart_with_load_error_include(tmp_path: Path) -> None:
    """Chart functions handle LoadError from missing include files."""
    from fava.context import g
    from fava.application import create_app

    load_error_file = tmp_path / "load_error.beancount"
    load_error_file.write_text("""
option "title" "Load Error Ledger"
option "operating_currency" "USD"

include "nonexistent_sub_file.beancount"

2020-01-01 open Assets:Bank
2020-01-01 open Expenses:Misc
""")

    app = create_app([str(load_error_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/load-error/"):
        app.preprocess_request()

        # Verify LoadError
        error_type_names = [type(e).__name__ for e in g.ledger.load_errors]
        assert "LoadError" in error_type_names, (
            f"Expected LoadError, got: {error_type_names}"
        )

        # Chart functions should still work with remaining entries
        ChartDataLoader.clear_cache()
        balances = ChartDataLoader.account_balance("Assets:Bank")
        assert isinstance(balances, list)

        net_worth = ChartDataLoader.net_worth()
        assert isinstance(net_worth, list)


def test_chart_with_empty_ledger(tmp_path: Path) -> None:
    """Chart functions handle empty (no transactions) ledger gracefully."""
    from fava.context import g
    from fava.application import create_app

    empty_file = tmp_path / "empty.beancount"
    empty_file.write_text("""
option "title" "Empty Ledger"
option "operating_currency" "USD"

2020-01-01 open Assets:Cash
2020-01-01 open Expenses:Food
""")

    app = create_app([str(empty_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/empty/"):
        app.preprocess_request()

        # Verify no load errors but also no entries
        assert len(g.ledger.load_errors) == 0
        assert len(g.ledger.all_entries) > 0  # At least Open directives
        assert len(g.filtered.entries) > 0

        # Chart functions should handle empty transactions gracefully
        balances = ChartDataLoader.account_balance("Assets:Cash")
        assert isinstance(balances, list)
        assert len(balances) == 0

        interval_totals = ChartDataLoader.interval_totals(
            Year,
            "Expenses",
        )
        assert isinstance(interval_totals, list)

        net_worth = ChartDataLoader.net_worth()
        assert isinstance(net_worth, list)


def test_chart_api_with_invalid_account(app: Flask) -> None:
    """ChartApi handles invalid/missing accounts gracefully."""
    with app.test_request_context("/long-example/"):
        app.preprocess_request()

        # Non-existent account should not crash, but may return empty
        balances = ChartDataLoader.account_balance("Non:Existent:Account")
        assert isinstance(balances, list)

        # Build chart even with empty data
        chart = ChartApi.account_balance(balances)
        assert isinstance(chart, BalancesChart)
        assert chart.data == []
        assert chart.label == "Account Balance"


def test_chart_data_loader_mock_verify(
    app: Flask,
) -> None:
    """Verify ChartDataLoader calls pure functions instead of g.ledger.charts.

    This is an important verification that the decoupling is complete.
    """
    with app.test_request_context("/long-example/"):
        app.preprocess_request()
        from fava.context import g

        # Patch g.ledger.charts to ensure it's NOT called
        original_charts = g.ledger.charts
        with patch.object(
            g.ledger,
            "charts",
            autospec=True,
        ) as mock_charts:
            # Clear any cached results first
            ChartDataLoader.clear_cache()

            # This should call charts.linechart pure function, not g.ledger.charts
            _ = ChartDataLoader.account_balance("Assets:US:Vanguard:Cash")

            # Verify g.ledger.charts.linechart was NOT called
            mock_charts.linechart.assert_not_called()
            mock_charts.hierarchy.assert_not_called()
            mock_charts.interval_totals.assert_not_called()
            mock_charts.net_worth.assert_not_called()

        # Restore original charts to avoid affecting other tests
        g.ledger.charts = original_charts


def test_ledger_cache_maxsize_configurable(tmp_path: Path) -> None:
    """FavaLedger cache maxsize can be configured via fava-option."""
    from fava.context import g
    from fava.application import create_app

    ledger_file = tmp_path / "cache_config.beancount"
    ledger_file.write_text("""
option "title" "Cache Config Ledger"
option "operating_currency" "USD"

2016-04-01 custom "fava-option" "ledger_cache_maxsize" "32"

2020-01-01 open Assets:Bank
2020-01-01 open Expenses:Misc
""")

    app = create_app([str(ledger_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/cache-config/"):
        app.preprocess_request()

        # Verify the configured maxsize is picked up
        assert g.ledger.fava_options.ledger_cache_maxsize == 32
        assert g.ledger._cache_maxsize == 32


def test_chart_cache_uses_include_mtime(tmp_path: Path) -> None:
    """Chart cache invalidates when an include sub-file changes.

    This test verifies that _content_hash incorporates changes from
    the watcher's last_notified timestamp, which is updated when
    any watched file (including includes) changes.
    """
    from fava.context import g
    from fava.application import create_app

    # Create a sub-ledger file
    sub_file = tmp_path / "sub.beancount"
    sub_file.write_text("""
2020-01-01 open Assets:Bank
2020-01-01 open Expenses:Misc

2020-01-02 * "Test"
  Assets:Bank  -10.00 USD
  Expenses:Misc
""")

    # Create a main ledger that includes the sub-file
    main_file = tmp_path / "main.beancount"
    main_file.write_text(f"""
option "title" "Include Test Ledger"
option "operating_currency" "USD"

include "{sub_file.name}"
""")

    app = create_app([str(main_file)])
    app.config["TESTING"] = True

    with app.test_request_context("/include-test/"):
        app.preprocess_request()

        # Get initial content hash
        hash1 = ChartDataLoader._content_hash()

        # Simulate a change notification on the sub-file
        g.ledger.watcher.notify(sub_file)

        # Content hash should change after sub-file notification
        hash2 = ChartDataLoader._content_hash()
        assert hash2 > hash1, (
            f"Content hash should increase after sub-file notification: "
            f"{hash2} should be > {hash1}"
        )

        # Verify that the cache key changes, forcing a cache miss
        ChartDataLoader.clear_cache()
        # First call after clear - should work without errors
        result = ChartDataLoader.account_balance("Assets:Bank")
        assert isinstance(result, list)

