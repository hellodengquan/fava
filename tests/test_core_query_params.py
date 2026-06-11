"""Tests for the unified query parameter parsing layer.

These tests mirror ``frontend/test/query_params.test.ts`` to ensure
parity between the frontend TypeScript implementation and the backend
Python implementation.  The ``ROUNDTRIP_TEST_CASES`` list must stay in
sync with the TypeScript version.
"""

from __future__ import annotations

import pytest

from fava.core.query_params import (
    DEFAULT_CONVERSION,
    DEFAULT_QUERY_PARAMS,
    Filters,
    FiltersConversionInterval,
    QueryParams,
    QUERY_PARAM_NAMES,
    QUERY_PARAM_SCHEMA,
    SYNCED_QUERY_PARAM_NAMES,
    get_filters_conversion_interval_from_mapping,
    get_filters_from_mapping,
    normalize_account,
    normalize_charts,
    normalize_conversion,
    normalize_filter,
    normalize_interval,
    normalize_query_string,
    normalize_time,
    parse_query_params,
    query_params_to_query_string,
    serialize_query_params,
    set_query_param_on_dict,
)
from fava.util.date import Month, Year


ROUNDTRIP_TEST_CASES = [
    {
        "name": "defaults (empty params)",
        "input": {},
        "expected": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "all params set (English)",
        "input": {
            "time": "2024",
            "account": "Assets:Cash",
            "filter": "#tag",
            "conversion": "USD",
            "interval": "year",
            "charts": "false",
            "query_string": "SELECT *",
        },
        "expected": {
            "time": "2024",
            "account": "Assets:Cash",
            "filter": "#tag",
            "conversion": "USD",
            "interval": "year",
            "charts": False,
            "query_string": "SELECT *",
        },
    },
    {
        "name": "Chinese account name",
        "input": {
            "account": "资产:现金",
            "filter": 'payee:"张三"',
        },
        "expected": {
            "time": "",
            "account": "资产:现金",
            "filter": 'payee:"张三"',
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "Japanese and Korean account names",
        "input": {
            "account": "費用:食費",
            "filter": "#한글태그",
        },
        "expected": {
            "time": "",
            "account": "費用:食費",
            "filter": "#한글태그",
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "special characters in params",
        "input": {
            "account": "Assets:Cash & Equivalents",
            "filter": 'payee:"A & B"',
            "query_string": "SELECT name WHERE account ~ '.*&.*'",
        },
        "expected": {
            "time": "",
            "account": "Assets:Cash & Equivalents",
            "filter": 'payee:"A & B"',
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "SELECT name WHERE account ~ '.*&.*'",
        },
    },
    {
        "name": "percent sign in account (should be literal)",
        "input": {
            "account": "Assets:100%Equity",
        },
        "expected": {
            "time": "",
            "account": "Assets:100%Equity",
            "filter": "",
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "whitespace trimming",
        "input": {
            "time": "  2024  ",
            "account": "  Assets:Cash  ",
            "filter": "  #tag  ",
            "conversion": "  USD  ",
            "interval": "  year  ",
        },
        "expected": {
            "time": "2024",
            "account": "Assets:Cash",
            "filter": "#tag",
            "conversion": "USD",
            "interval": "year",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "empty strings fall back to defaults",
        "input": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": "",
            "interval": "",
            "charts": "",
            "query_string": "",
        },
        "expected": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "invalid interval falls back to month",
        "input": {
            "interval": "foo",
        },
        "expected": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "mixed case interval normalized to lower",
        "input": {
            "interval": "YEAR",
        },
        "expected": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": "at_cost",
            "interval": "year",
            "charts": True,
            "query_string": "",
        },
    },
    {
        "name": "emoji characters preserved",
        "input": {
            "account": "🎉:Expenses:💰",
            "filter": "#标签🎉",
        },
        "expected": {
            "time": "",
            "account": "🎉:Expenses:💰",
            "filter": "#标签🎉",
            "conversion": "at_cost",
            "interval": "month",
            "charts": True,
            "query_string": "",
        },
    },
]


def _interval_str(interval_obj) -> str:
    """Convert an interval instance to its canonical string name."""
    from fava.util.date import INTERVALS

    for name, inst in INTERVALS.items():
        if interval_obj is inst:
            return name
    return "unknown"


def test_query_param_names_consistent_with_schema():
    """QUERY_PARAM_NAMES values must match QUERY_PARAM_SCHEMA keys."""
    param_names = set(QUERY_PARAM_NAMES.values())
    schema_keys = set(QUERY_PARAM_SCHEMA.keys())
    assert param_names == schema_keys


def test_synced_params_match_schema():
    """SYNCED_QUERY_PARAM_NAMES must match schema entries with synced=True."""
    synced_from_schema = {
        k for k, v in QUERY_PARAM_SCHEMA.items() if v["synced"]
    }
    synced_from_module = set(SYNCED_QUERY_PARAM_NAMES)
    assert synced_from_module == synced_from_schema


def test_schema_defaults_match_default_query_params():
    """Schema defaults must match DEFAULT_QUERY_PARAMS."""
    for key, schema in QUERY_PARAM_SCHEMA.items():
        default = getattr(DEFAULT_QUERY_PARAMS, key)
        if key == "interval":
            assert _interval_str(default) == schema["default"]
        else:
            assert default == schema["default"], f"default mismatch for {key}"


def test_schema_types_match():
    """Schema type declarations describe the wire (URL string) type."""
    for key, schema in QUERY_PARAM_SCHEMA.items():
        default = getattr(DEFAULT_QUERY_PARAMS, key)
        if key == "interval":
            assert _interval_str(default) == schema["default"]
        elif schema["type"] == "string":
            assert isinstance(default, str), f"type mismatch for {key}"
        elif schema["type"] == "bool":
            assert isinstance(default, bool), f"type mismatch for {key}"


def test_normalize_time_various_inputs():
    assert normalize_time(None) == ""
    assert normalize_time("") == ""
    assert normalize_time("  ") == ""
    assert normalize_time("2024") == "2024"
    assert normalize_time("  2024-01  ") == "2024-01"
    assert normalize_time("year-2 - year") == "year-2 - year"


def test_normalize_account_chinese_and_special_chars():
    assert normalize_account(None) == ""
    assert normalize_account("") == ""
    assert normalize_account("Assets:Cash") == "Assets:Cash"
    assert normalize_account("  资产:现金  ") == "资产:现金"
    assert normalize_account("Expenses:餐饮-午餐") == "Expenses:餐饮-午餐"
    assert normalize_account("账户名 with spaces") == "账户名 with spaces"
    assert normalize_account("特殊字符:!@#$%^&*()") == "特殊字符:!@#$%^&*()"
    assert normalize_account("日本語:勘定科目") == "日本語:勘定科目"
    assert normalize_account("한국어:계정") == "한국어:계정"
    assert normalize_account("Emoji:🎉💰") == "Emoji:🎉💰"


def test_normalize_filter_various_inputs():
    assert normalize_filter(None) == ""
    assert normalize_filter("") == ""
    assert normalize_filter("  #tag  ") == "#tag"
    assert normalize_filter('payee:"中文收款人"') == 'payee:"中文收款人"'


def test_normalize_conversion_falls_back_to_default():
    assert normalize_conversion(None) == DEFAULT_CONVERSION
    assert normalize_conversion("") == DEFAULT_CONVERSION
    assert normalize_conversion("  ") == DEFAULT_CONVERSION
    assert normalize_conversion("USD") == "USD"
    assert normalize_conversion("  at_value  ") == "at_value"


def test_normalize_interval_falls_back_to_default():
    assert normalize_interval(None) is Month
    assert normalize_interval("") is Month
    assert normalize_interval("year") is Year
    assert normalize_interval("month") is Month
    assert normalize_interval("day") is not Month
    assert normalize_interval("foo") is Month
    assert normalize_interval("invalid_value") is Month


def test_normalize_interval_logs_warning_on_invalid(caplog):
    with caplog.at_level("WARNING"):
        result = normalize_interval("foo")
    assert result is Month
    assert "Invalid interval value" in caplog.text
    assert "foo" in caplog.text


def test_normalize_charts_boolean_semantics():
    assert normalize_charts(None) is True
    assert normalize_charts("") is True
    assert normalize_charts("true") is True
    assert normalize_charts("false") is False
    assert normalize_charts("anything") is True
    assert normalize_charts(True) is True
    assert normalize_charts(False) is False


def test_normalize_query_string_passthrough():
    assert normalize_query_string(None) == ""
    assert normalize_query_string("") == ""
    assert normalize_query_string("SELECT *") == "SELECT *"
    assert normalize_query_string("中文查询") == "中文查询"


def test_parse_query_params_from_dict():
    params = {
        "time": "2024",
        "account": "Assets:Cash",
        "filter": "#tag",
        "conversion": "USD",
        "interval": "year",
        "charts": "false",
        "query_string": "SELECT",
    }
    parsed = parse_query_params(params)
    assert parsed.time == "2024"
    assert parsed.account == "Assets:Cash"
    assert parsed.filter == "#tag"
    assert parsed.conversion == "USD"
    assert parsed.interval is Year
    assert parsed.charts is False
    assert parsed.query_string == "SELECT"


def test_parse_query_params_defaults():
    parsed = parse_query_params({})
    assert parsed == DEFAULT_QUERY_PARAMS


def test_parse_query_params_chinese_account():
    parsed = parse_query_params({"account": "资产:现金"})
    assert parsed.account == "资产:现金"


def test_serialize_query_params_round_trip():
    original = QueryParams(
        time="2024",
        account="资产:现金",
        filter="#tag",
        conversion="USD",
        interval=Year,
        charts=False,
        query_string="SELECT * FROM accounts",
    )

    from fava.core.query_params import SerializeOptions

    serialized = serialize_query_params(
        original,
        SerializeOptions(include_charts=True, include_query_string=True),
    )
    serialized_dict = dict(serialized)

    reparsed = parse_query_params(serialized_dict)

    assert reparsed.time == original.time
    assert reparsed.account == original.account
    assert reparsed.filter == original.filter
    assert reparsed.conversion == original.conversion
    assert reparsed.interval is original.interval
    assert reparsed.charts == original.charts
    assert reparsed.query_string == original.query_string


@pytest.mark.parametrize(
    "account,desc",
    [
        ("资产:现金", "Chinese account"),
        ("Expenses:餐饮娱乐", "Chinese with colon"),
        ("費用:食費", "Japanese"),
        ("지출:한국어", "Korean"),
        ("Account:with spaces", "spaces"),
        ("Special:!@#$%^&*()_+-=", "special chars"),
    ],
)
def test_serialize_query_params_chinese_roundtrip(account, desc):
    from fava.core.query_params import SerializeOptions

    original = QueryParams(account=account)
    serialized = serialize_query_params(
        original,
        SerializeOptions(include_charts=True, include_query_string=True),
    )
    serialized_dict = dict(serialized)
    reparsed = parse_query_params(serialized_dict)
    assert reparsed.account == original.account, f"round-trip failed for {desc}"


def test_set_query_param_on_dict():
    values = {}

    set_query_param_on_dict(values, "time", "2024")
    assert values.get("time") == "2024"

    set_query_param_on_dict(values, "account", "资产:现金")
    assert values.get("account") == "资产:现金"

    set_query_param_on_dict(values, "time", "")
    assert "time" not in values

    set_query_param_on_dict(values, "interval", "year")
    assert values.get("interval") == "year"

    set_query_param_on_dict(values, "interval", "month")
    assert "interval" not in values

    set_query_param_on_dict(values, "conversion", "at_cost")
    assert "conversion" not in values

    set_query_param_on_dict(values, "conversion", "USD")
    assert values.get("conversion") == "USD"

    set_query_param_on_dict(values, "charts", False)
    assert values.get("charts") == "false"

    set_query_param_on_dict(values, "charts", True)
    assert "charts" not in values


def test_filters_helpers():
    params = QueryParams(
        time="2024",
        account="Assets:Cash",
        filter="#tag",
        conversion="USD",
        interval=Year,
        charts=False,
        query_string="SELECT",
    )

    filters = params.as_filters()
    assert isinstance(filters, Filters)
    assert filters.time == "2024"
    assert filters.account == "Assets:Cash"
    assert filters.filter == "#tag"

    fci = params.as_filters_conversion_interval()
    assert isinstance(fci, FiltersConversionInterval)
    assert fci.conversion == "USD"
    assert fci.interval is Year


def test_get_filters_from_mapping():
    params = {
        "time": "2024",
        "account": "资产:现金",
        "filter": "#tag",
    }

    filters = get_filters_from_mapping(params)
    assert filters.time == "2024"
    assert filters.account == "资产:现金"
    assert filters.filter == "#tag"

    fci = get_filters_conversion_interval_from_mapping(params)
    assert fci.conversion == "at_cost"
    assert fci.interval is Month


@pytest.mark.parametrize("tc", ROUNDTRIP_TEST_CASES, ids=lambda x: x["name"])
def test_roundtrip_test_cases(tc):
    """Each round-trip test case must parse and round-trip correctly."""
    parsed = parse_query_params(tc["input"])
    expected = tc["expected"]

    assert parsed.time == expected["time"], f"[{tc['name']}] time mismatch"
    assert parsed.account == expected["account"], f"[{tc['name']}] account mismatch"
    assert parsed.filter == expected["filter"], f"[{tc['name']}] filter mismatch"
    assert (
        parsed.conversion == expected["conversion"]
    ), f"[{tc['name']}] conversion mismatch"
    assert (
        _interval_str(parsed.interval) == expected["interval"]
    ), f"[{tc['name']}] interval mismatch"
    assert parsed.charts == expected["charts"], f"[{tc['name']}] charts mismatch"
    assert (
        parsed.query_string == expected["query_string"]
    ), f"[{tc['name']}] query_string mismatch"

    from fava.core.query_params import SerializeOptions

    serialized = serialize_query_params(
        parsed,
        SerializeOptions(include_charts=True, include_query_string=True),
    )
    serialized_dict = dict(serialized)
    reparsed = parse_query_params(serialized_dict)

    assert reparsed.time == parsed.time, f"[{tc['name']}] time round-trip"
    assert reparsed.account == parsed.account, f"[{tc['name']}] account round-trip"
    assert reparsed.filter == parsed.filter, f"[{tc['name']}] filter round-trip"
    assert (
        reparsed.conversion == parsed.conversion
    ), f"[{tc['name']}] conversion round-trip"
    assert (
        reparsed.interval is parsed.interval
    ), f"[{tc['name']}] interval round-trip"
    assert reparsed.charts == parsed.charts, f"[{tc['name']}] charts round-trip"
    assert (
        reparsed.query_string == parsed.query_string
    ), f"[{tc['name']}] query_string round-trip"


def test_percent_sign_roundtrip():
    """Percent signs in account names should survive URL encoding."""
    from urllib.parse import parse_qs
    from urllib.parse import urlencode

    original = "Assets:100%Equity"

    query_string = urlencode({"account": original})
    parsed_dict = parse_qs(query_string)

    assert parsed_dict["account"][0] == original


def test_query_params_to_query_string():
    from fava.core.query_params import SerializeOptions

    params = QueryParams(
        time="2024",
        account="Assets:Cash",
        conversion="USD",
        interval=Year,
    )
    qs = query_params_to_query_string(params)
    assert "time=2024" in qs
    assert "account=Assets%3ACash" in qs or "account=Assets:Cash" in qs
    assert "conversion=USD" in qs
    assert "interval=year" in qs


def test_empty_params_produce_defaults():
    params = parse_query_params(
        {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": "",
            "interval": "",
            "charts": "",
            "query_string": "",
        }
    )
    assert params.conversion == DEFAULT_CONVERSION
    assert params.interval is Month
    assert params.charts is True
    assert params.time == ""
    assert params.account == ""
    assert params.filter == ""
    assert params.query_string == ""
