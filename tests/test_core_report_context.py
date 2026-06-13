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


class TestReportContextEmptyFilters:
    def test_empty_filter_string(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(filter="")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == len(ledger.all_entries)

    def test_empty_account_string(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(account="")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == len(ledger.all_entries)

    def test_empty_time_string(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == len(ledger.all_entries)

    def test_all_empty_produces_full_ledger(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="", account="", filter="")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == len(ledger.all_entries)
        assert filtered.date_range is None

    def test_whitespace_only_filter(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(filter="  ")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == len(ledger.all_entries)

    def test_whitespace_only_account(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(account="  ")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == 0


class TestReportContextCrossYearTimePeriods:
    def test_cross_year_range(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2013-10-01 - 2015-03-31")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert filtered.date_range.begin.year == 2013
        assert filtered.date_range.begin.month == 10
        assert filtered.date_range.end.year == 2015
        assert filtered.date_range.end.month == 4
        assert len(filtered.entries) < len(ledger.all_entries)

    def test_single_year(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert filtered.date_range.begin.year == 2014
        assert filtered.date_range.end.year == 2015

    def test_single_month(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014-06")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert filtered.date_range.begin.year == 2014
        assert filtered.date_range.begin.month == 6

    def test_single_day(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014-06-15")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert filtered.date_range.begin.day == 15

    def test_quarter(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014-Q2")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert filtered.date_range.begin.month == 4
        assert filtered.date_range.end.month == 7

    def test_year_range(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2013 - 2015")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert filtered.date_range.begin.year == 2013
        assert filtered.date_range.end.year == 2016

    def test_time_filter_narrows_results(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx_broad = ReportContext(time="2014")
        ctx_narrow = ReportContext(time="2014-06")
        broad = ctx_broad.create_filtered_ledger(ledger)
        narrow = ctx_narrow.create_filtered_ledger(ledger)
        assert len(broad.entries) >= len(narrow.entries)


class TestReportContextCombinedEdgeCases:
    def test_time_and_account_combined(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014", account="Expenses")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        assert len(filtered.entries) > 0
        assert len(filtered.entries) < len(ledger.all_entries)

    def test_time_and_filter_combined(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014", filter="#test")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None

    def test_account_and_filter_combined(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(account="Expenses", filter="#test")
        filtered = ctx.create_filtered_ledger(ledger)
        from fava.beans.account import get_entry_accounts

        for entry in filtered.entries:
            accounts = get_entry_accounts(entry)
            tags = getattr(entry, "tags", None)
            assert tags is not None and "test" in tags
            assert any("Expenses" in a for a in accounts)

    def test_all_three_filters_combined(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(time="2014", account="Expenses", filter="#test")
        filtered = ctx.create_filtered_ledger(ledger)
        assert filtered.date_range is not None
        from fava.beans.account import get_entry_accounts

        for entry in filtered.entries:
            accounts = get_entry_accounts(entry)
            tags = getattr(entry, "tags", None)
            assert tags is not None and "test" in tags
            assert any("Expenses" in a for a in accounts)

    def test_nonexistent_account_produces_empty(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(account="NonExistent:Account:Path")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == 0

    def test_nonexistent_tag_produces_empty(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx = ReportContext(filter="#nonexistent-tag-xyz")
        filtered = ctx.create_filtered_ledger(ledger)
        assert len(filtered.entries) == 0

    def test_conversion_does_not_affect_filter(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx_at_cost = ReportContext(
            time="2014", conversion="at_cost"
        )
        ctx_units = ReportContext(time="2014", conversion="units")
        filtered_at_cost = ctx_at_cost.create_filtered_ledger(ledger)
        filtered_units = ctx_units.create_filtered_ledger(ledger)
        assert len(filtered_at_cost.entries) == len(
            filtered_units.entries
        )

    def test_interval_does_not_affect_filter(
        self, example_ledger: pytest.FixtureRequest
    ) -> None:
        from fava.core import FavaLedger

        ledger: FavaLedger = example_ledger  # type: ignore[assignment]
        ctx_month = ReportContext(time="2014", interval="month")
        ctx_year = ReportContext(time="2014", interval="year")
        filtered_month = ctx_month.create_filtered_ledger(ledger)
        filtered_year = ctx_year.create_filtered_ledger(ledger)
        assert len(filtered_month.entries) == len(
            filtered_year.entries
        )


class TestReportContextFromRequestEdgeCases:
    def test_from_request_with_time_range(
        self, app: pytest.FixtureRequest
    ) -> None:
        from flask import Flask

        flask_app: Flask = app  # type: ignore[assignment]
        with flask_app.test_request_context(
            "/long-example/?time=2013+ - +2015"
        ):
            ctx = ReportContext.from_request()
            assert "2013" in ctx.time
            assert "2015" in ctx.time

    def test_from_request_with_hash_filter(
        self, app: pytest.FixtureRequest
    ) -> None:
        from flask import Flask

        flask_app: Flask = app  # type: ignore[assignment]
        with flask_app.test_request_context(
            "/long-example/?filter=%23trip"
        ):
            ctx = ReportContext.from_request()
            assert ctx.filter == "#trip"

    def test_from_request_with_link_filter(
        self, app: pytest.FixtureRequest
    ) -> None:
        from flask import Flask

        flask_app: Flask = app  # type: ignore[assignment]
        with flask_app.test_request_context(
            "/long-example/?filter=%5Emy-link"
        ):
            ctx = ReportContext.from_request()
            assert ctx.filter == "^my-link"

    def test_from_request_with_negated_tag(
        self, app: pytest.FixtureRequest
    ) -> None:
        from flask import Flask

        flask_app: Flask = app  # type: ignore[assignment]
        with flask_app.test_request_context(
            "/long-example/?filter=-%23trip"
        ):
            ctx = ReportContext.from_request()
            assert ctx.filter == "-#trip"

    def test_from_request_with_multiple_params(
        self, app: pytest.FixtureRequest
    ) -> None:
        from flask import Flask

        flask_app: Flask = app  # type: ignore[assignment]
        with flask_app.test_request_context(
            "/long-example/?time=2014&account=Assets&filter=%23test&conversion=units&interval=week"
        ):
            ctx = ReportContext.from_request()
            assert ctx.time == "2014"
            assert ctx.account == "Assets"
            assert ctx.filter == "#test"
            assert ctx.conversion == "units"
            assert ctx.interval == "week"


class TestReportContextEquality:
    def test_same_params_are_equal(self) -> None:
        ctx1 = ReportContext(time="2024", account="Assets")
        ctx2 = ReportContext(time="2024", account="Assets")
        assert ctx1 == ctx2

    def test_different_params_are_not_equal(self) -> None:
        ctx1 = ReportContext(time="2024")
        ctx2 = ReportContext(time="2025")
        assert ctx1 != ctx2

    def test_hash_consistency(self) -> None:
        ctx1 = ReportContext(time="2024", account="Assets")
        ctx2 = ReportContext(time="2024", account="Assets")
        assert hash(ctx1) == hash(ctx2)

    def test_usable_as_dict_key(self) -> None:
        ctx = ReportContext(time="2024")
        d = {ctx: "value"}
        assert d[ReportContext(time="2024")] == "value"
