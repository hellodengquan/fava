"""Tests for the unified report filter context."""

from __future__ import annotations

import pytest

from fava.core import ReportContext
from fava.core.conversion import AT_COST
from fava.core.conversion import AT_VALUE
from fava.core.conversion import UNITS
from fava.core.conversion import conversion_from_str
from fava.util.date import Month
from fava.util.date import Quarter
from fava.util.date import Week
from fava.util.date import Year


class TestReportContextCreation:
    def test_default_values(self) -> None:
        ctx = ReportContext()
        assert ctx.time == ""
        assert ctx.account == ""
        assert ctx.filter == ""
        assert ctx.conversion == "at_cost"
        assert ctx.interval == "month"

    def test_from_dict_all_params(self) -> None:
        ctx = ReportContext.from_dict(
            {
                "time": "2024",
                "account": "Assets:US:BofA",
                "filter": "#trip",
                "conversion": "USD",
                "interval": "year",
            }
        )
        assert ctx.time == "2024"
        assert ctx.account == "Assets:US:BofA"
        assert ctx.filter == "#trip"
        assert ctx.conversion == "USD"
        assert ctx.interval == "year"

    def test_from_dict_missing_params_uses_defaults(self) -> None:
        ctx = ReportContext.from_dict({})
        assert ctx.time == ""
        assert ctx.account == ""
        assert ctx.filter == ""
        assert ctx.conversion == "at_cost"
        assert ctx.interval == "month"

    def test_from_dict_empty_conversion(self) -> None:
        ctx = ReportContext.from_dict({"conversion": ""})
        assert ctx.conversion == "at_cost"

    def test_from_dict_empty_interval(self) -> None:
        ctx = ReportContext.from_dict({"interval": ""})
        assert ctx.interval == "month"

    def test_from_dict_interval_case_insensitive(self) -> None:
        ctx = ReportContext.from_dict({"interval": "YEAR"})
        assert ctx.interval == "year"

    def test_from_request(self, app: pytest.FixtureRequest) -> None:
        from flask import Flask

        flask_app: Flask = app  # type: ignore[assignment]
        with flask_app.test_request_context(
            "/long-example/?time=2024&account=Assets&filter=%23trip&conversion=EUR&interval=quarter"
        ):
            ctx = ReportContext.from_request()
            assert ctx.time == "2024"
            assert ctx.account == "Assets"
            assert ctx.filter == "#trip"
            assert ctx.conversion == "EUR"
            assert ctx.interval == "quarter"

    def test_from_request_defaults(self, app: pytest.FixtureRequest) -> None:
        from flask import Flask

        flask_app: Flask = app  # type: ignore[assignment]
        with flask_app.test_request_context("/long-example/"):
            ctx = ReportContext.from_request()
            assert ctx.time == ""
            assert ctx.account == ""
            assert ctx.filter == ""
            assert ctx.conversion == "at_cost"
            assert ctx.interval == "month"


class TestReportContextImmutability:
    def test_frozen_dataclass(self) -> None:
        ctx = ReportContext(time="2024")
        with pytest.raises(AttributeError):
            ctx.time = "2025"  # type: ignore[misc]

    def test_frozen_dataclass_account(self) -> None:
        ctx = ReportContext()
        with pytest.raises(AttributeError):
            ctx.account = "Assets"  # type: ignore[misc]


class TestReportContextParsedConversion:
    def test_parsed_conversion_at_cost(self) -> None:
        ctx = ReportContext(conversion="at_cost")
        assert ctx.parsed_conversion is AT_COST

    def test_parsed_conversion_at_value(self) -> None:
        ctx = ReportContext(conversion="at_value")
        assert ctx.parsed_conversion is AT_VALUE

    def test_parsed_conversion_units(self) -> None:
        ctx = ReportContext(conversion="units")
        assert ctx.parsed_conversion is UNITS

    def test_parsed_conversion_currency(self) -> None:
        ctx = ReportContext(conversion="USD")
        conv = ctx.parsed_conversion
        assert conv is not AT_COST

    def test_parsed_conversion_default(self) -> None:
        ctx = ReportContext()
        assert ctx.parsed_conversion is AT_COST


class TestReportContextParsedInterval:
    def test_parsed_interval_month(self) -> None:
        ctx = ReportContext(interval="month")
        assert ctx.parsed_interval is Month

    def test_parsed_interval_year(self) -> None:
        ctx = ReportContext(interval="year")
        assert ctx.parsed_interval is Year

    def test_parsed_interval_quarter(self) -> None:
        ctx = ReportContext(interval="quarter")
        assert ctx.parsed_interval is Quarter

    def test_parsed_interval_week(self) -> None:
        ctx = ReportContext(interval="week")
        assert ctx.parsed_interval is Week

    def test_parsed_interval_unknown_defaults_to_month(self) -> None:
        ctx = ReportContext(interval="unknown")
        assert ctx.parsed_interval is Month

    def test_parsed_interval_default(self) -> None:
        ctx = ReportContext()
        assert ctx.parsed_interval is Month


class TestReportContextToDict:
    def test_to_dict_all_params(self) -> None:
        ctx = ReportContext(
            time="2024",
            account="Assets",
            filter="#trip",
            conversion="USD",
            interval="year",
        )
        d = ctx.to_dict()
        assert d["time"] == "2024"
        assert d["account"] == "Assets"
        assert d["filter"] == "#trip"
        assert d["conversion"] == "USD"
        assert d["interval"] == "year"

    def test_to_dict_skips_defaults(self) -> None:
        ctx = ReportContext()
        d = ctx.to_dict()
        assert "time" not in d
        assert "account" not in d
        assert "filter" not in d
        assert "conversion" not in d
        assert "interval" not in d

    def test_to_dict_skips_at_cost(self) -> None:
        ctx = ReportContext(conversion="at_cost")
        d = ctx.to_dict()
        assert "conversion" not in d

    def test_to_dict_includes_non_default_conversion(self) -> None:
        ctx = ReportContext(conversion="EUR")
        d = ctx.to_dict()
        assert d["conversion"] == "EUR"

    def test_to_dict_skips_month_interval(self) -> None:
        ctx = ReportContext(interval="month")
        d = ctx.to_dict()
        assert "interval" not in d

    def test_to_dict_includes_non_default_interval(self) -> None:
        ctx = ReportContext(interval="year")
        d = ctx.to_dict()
        assert d["interval"] == "year"

    def test_to_dict_empty_strings_excluded(self) -> None:
        ctx = ReportContext(time="", account="", filter="")
        d = ctx.to_dict()
        assert "time" not in d
        assert "account" not in d
        assert "filter" not in d


class TestReportContextUrlParams:
    def test_url_params_all(self) -> None:
        ctx = ReportContext(
            time="2024",
            account="Assets",
            filter="#trip",
            conversion="USD",
            interval="year",
        )
        params = ctx.url_params()
        assert params["time"] == "2024"
        assert params["account"] == "Assets"
        assert params["filter"] == "#trip"
        assert params["conversion"] == "USD"
        assert params["interval"] == "year"

    def test_url_params_includes_defaults(self) -> None:
        ctx = ReportContext()
        params = ctx.url_params()
        assert params["time"] == ""
        assert params["account"] == ""
        assert params["filter"] == ""
        assert params["conversion"] == "at_cost"
        assert params["interval"] == "month"


class TestReportContextCreateFilteredLedger:
    def test_create_filtered_ledger_no_filters(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext()
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == len(ledger.all_entries)

    def test_create_filtered_ledger_time_filter(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert filtered.date_range.begin.year == 2014

    def test_create_filtered_ledger_account_filter(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(account="Assets:US:BofA")
        filtered = ctx.create_filtered_ledger(ledger)
        from fava.beans.account import get_entry_accounts

        for entry in filtered.entries:
            accounts = get_entry_accounts(entry)
            assert any("BofA" in a for a in accounts)

    def test_create_filtered_ledger_tag_filter(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(filter="#test")
        filtered = ctx.create_filtered_ledger(ledger)
        for entry in filtered.entries:
            tags = getattr(entry, "tags", None)
            assert tags is not None and "test" in tags

    def test_create_filtered_ledger_combined_filters(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014", account="Expenses")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert len(filtered.entries) < len(ledger.all_entries)

    def test_create_filtered_ledger_consistent_with_get_filtered(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014", account="Assets", filter="#test")
        filtered_via_context = ctx.create_filtered_ledger(ledger)
        filtered_via_method = ledger.get_filtered(
            account="Assets", filter="#test", time="2014"
        )
        assert len(filtered_via_context.entries) == len(
            filtered_via_method.entries
        )


class TestReportContextTagInclusiveExclusive:
    def test_tag_filter_inclusive(self) -> None:
        ctx = ReportContext(filter="#trip")
        assert ctx.filter == "#trip"

    def test_tag_filter_exclusive_negation(self) -> None:
        ctx = ReportContext(filter="-#trip")
        assert ctx.filter == "-#trip"

    def test_tag_filter_combined_with_or(self) -> None:
        ctx = ReportContext(filter="#trip,#work")
        assert ctx.filter == "#trip,#work"

    def test_tag_filter_combined_with_and(self) -> None:
        ctx = ReportContext(filter="#trip #work")
        assert ctx.filter == "#trip #work"

    def test_tag_filter_with_account(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(filter="#test", account="Expenses")
        filtered = ctx.create_filtered_ledger(ledger)
        from fava.beans.account import get_entry_accounts

        for entry in filtered.entries:
            accounts = get_entry_accounts(entry)
            tags = getattr(entry, "tags", None)
            assert tags is not None and "test" in tags
            assert any("Expenses" in a for a in accounts)


class TestReportContextAccountMatching:
    def test_account_exact_match(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(account="Assets:US:BofA:Checking")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) > 0

    def test_account_prefix_match(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx_broad = ReportContext(account="Assets")
        broad_filtered = ctx_broad.create_filtered_ledger(ledger)
        ctx_narrow = ReportContext(account="Assets:US")
        narrow_filtered = ctx_narrow.create_filtered_ledger(ledger)
        assert len(broad_filtered.entries) >= len(narrow_filtered.entries)

    def test_account_regex_match(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(account=".*BofA.*")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) > 0


class TestReportContextRepr:
    def test_repr(self) -> None:
        ctx = ReportContext(time="2024", account="Assets")
        r = repr(ctx)
        assert "ReportContext" in r
        assert "2024" in r
        assert "Assets" in r
