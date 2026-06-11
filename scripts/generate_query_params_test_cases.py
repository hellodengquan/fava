#!/usr/bin/env python3
"""Generate shared regression test cases for Fava query parameter parsing.

Generates a JSON file ``schemas/query_params_test_cases.generated.json``
that contains a comprehensive set of (input, expected_output) pairs derived
from the single-source-of-truth schema. Both the Python backend and the
TypeScript frontend consume this exact file in their test suites to ensure
behaviour parity.

Usage::

    python scripts/generate_query_params_test_cases.py

The generated JSON should be checked into version control so that test
runs are reproducible without invoking the generator.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "query_params.schema.json"
TEST_CASES_PATH = (
    PROJECT_ROOT / "schemas" / "query_params_test_cases.generated.json"
)


def load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        print(f"ERROR: Schema not found at {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(1)
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_test_cases(schema: dict) -> dict:
    """Build the full test case suite."""
    field_aliases = schema["fieldNameAliases"]
    conversion_aliases = schema["conversionAliases"]
    interval_values = schema["intervalValidValues"]
    default_conversion = schema["defaultConversion"]
    default_interval = schema["defaultInterval"]

    parse_cases: list[dict] = []
    serialize_cases: list[dict] = []
    roundtrip_cases: list[dict] = []

    # ------------------------------------------------------------------
    # 1. Empty params → all defaults
    # ------------------------------------------------------------------
    parse_cases.append({
        "name": "empty params → defaults",
        "input": {},
        "expected": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": default_conversion,
            "interval": default_interval,
            "charts": True,
            "query_string": "",
            "explicit": False,
        },
    })

    # ------------------------------------------------------------------
    # 2. Default value for every field individually
    # ------------------------------------------------------------------
    for url_name, meta in schema["fields"].items():
        default = meta["default"]
        if url_name == "interval":
            default = default_interval
        if url_name == "conversion":
            default = default_conversion

        input_dict = {url_name: default if not isinstance(default, bool) else str(default).lower()}
        expected = {
            meta["dataclassFieldName"]: default
            if not isinstance(default, bool)
            else default,
        }
        # For interval, bool is not involved
        parse_cases.append({
            "name": f"single default param: {url_name}",
            "input": input_dict,
            "expectedPartial": expected,
        })

    # ------------------------------------------------------------------
    # 3. Conversion alias mapping — each alias
    # ------------------------------------------------------------------
    for alias_from, alias_to in conversion_aliases.items():
        parse_cases.append({
            "name": f"conversion alias: '{alias_from}' → '{alias_to}'",
            "input": {"conversion": alias_from},
            "expectedPartial": {"conversion": alias_to},
        })

    # Case-insensitive alias variants (Python normalises via .lower())
    for alias_from in conversion_aliases:
        parse_cases.append({
            "name": f"conversion alias case-insensitive: '{alias_from.upper()}'",
            "input": {"conversion": alias_from.upper()},
            "expectedPartial": {"conversion": conversion_aliases[alias_from]},
        })

    # Whitespace around alias values
    for alias_from, alias_to in conversion_aliases.items():
        parse_cases.append({
            "name": f"conversion alias with whitespace: ' {alias_from} '",
            "input": {"conversion": f"  {alias_from}  "},
            "expectedPartial": {"conversion": alias_to},
        })

    # ------------------------------------------------------------------
    # 4. All interval valid values
    # ------------------------------------------------------------------
    for interval in interval_values:
        parse_cases.append({
            "name": f"interval valid value: '{interval}'",
            "input": {"interval": interval},
            "expectedPartial": {"interval": interval},
        })
    # Mixed-case interval
    for interval in interval_values:
        parse_cases.append({
            "name": f"interval mixed case: '{interval.upper()}'",
            "input": {"interval": interval.upper()},
            "expectedPartial": {"interval": interval},
        })
    # Whitespace around interval
    for interval in interval_values:
        parse_cases.append({
            "name": f"interval with whitespace: ' {interval} '",
            "input": {"interval": f"  {interval}  "},
            "expectedPartial": {"interval": interval},
        })

    # Invalid interval → default
    parse_cases.append({
        "name": "invalid interval → default month",
        "input": {"interval": "millennium"},
        "expectedPartial": {"interval": default_interval},
    })

    # ------------------------------------------------------------------
    # 5. Explicit flag variations
    # ------------------------------------------------------------------
    parse_cases.append({
        "name": "explicit flag: _e=1",
        "input": {"_e": "1"},
        "expectedPartial": {"explicit": True},
    })
    parse_cases.append({
        "name": "explicit flag: _e=true",
        "input": {"_e": "true"},
        "expectedPartial": {"explicit": True},
    })
    parse_cases.append({
        "name": "explicit flag: _e=TRUE (case-insensitive)",
        "input": {"_e": "TRUE"},
        "expectedPartial": {"explicit": True},
    })
    parse_cases.append({
        "name": "explicit flag: _e=0 → false",
        "input": {"_e": "0"},
        "expectedPartial": {"explicit": False},
    })
    parse_cases.append({
        "name": "explicit flag: _e=false → false",
        "input": {"_e": "false"},
        "expectedPartial": {"explicit": False},
    })

    # ------------------------------------------------------------------
    # 6. Charts flag
    # ------------------------------------------------------------------
    parse_cases.append({
        "name": "charts=false",
        "input": {"charts": "false"},
        "expectedPartial": {"charts": False},
    })
    parse_cases.append({
        "name": "charts=any-other-value → true",
        "input": {"charts": "true"},
        "expectedPartial": {"charts": True},
    })
    parse_cases.append({
        "name": "charts absent → true",
        "input": {},
        "expectedPartial": {"charts": True},
    })

    # ------------------------------------------------------------------
    # 7. Whitespace trimming for string filters (time/account/filter)
    # ------------------------------------------------------------------
    for field_url, field_data in [
        ("time", "2024-01-02"),
        ("account", "Assets:Cash"),
        ("filter", "#tag and #other"),
    ]:
        dataclass_field = schema["fields"][field_url]["dataclassFieldName"]
        parse_cases.append({
            "name": f"{field_url} trimmed: '  {field_data}  '",
            "input": {field_url: f"  {field_data}  "},
            "expectedPartial": {dataclass_field: field_data},
        })

    # query_string is NOT trimmed
    parse_cases.append({
        "name": "query_string preserves whitespace",
        "input": {"query_string": "  SELECT *  "},
        "expectedPartial": {"query_string": "  SELECT *  "},
    })

    # ------------------------------------------------------------------
    # 8. Chinese / unicode inputs
    # ------------------------------------------------------------------
    parse_cases.append({
        "name": "Chinese account name",
        "input": {"account": "  资产:现金  ", "conversion": "units"},
        "expectedPartial": {"account": "资产:现金", "conversion": "units"},
    })

    # ------------------------------------------------------------------
    # 9. Full param combinations
    # ------------------------------------------------------------------
    parse_cases.append({
        "name": "all params set (English)",
        "input": {
            "time": "2024",
            "account": "Assets:Cash",
            "filter": "#paycheck",
            "conversion": "USD",
            "interval": "year",
            "charts": "false",
        },
        "expectedPartial": {
            "time": "2024",
            "account": "Assets:Cash",
            "filter": "#paycheck",
            "conversion": "USD",
            "interval": "year",
            "charts": False,
        },
    })

    # ------------------------------------------------------------------
    # SERIALIZATION CASES
    # ------------------------------------------------------------------

    # All-default params without explicit → contains conversion+interval, no _e
    serialize_cases.append({
        "name": "serialize all defaults without explicit",
        "input": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": default_conversion,
            "interval": default_interval,
            "charts": True,
            "query_string": "",
            "explicit": False,
        },
        "options": {"includeCharts": True},
        "expectedPairsContain": [
            ["conversion", default_conversion],
            ["interval", default_interval],
        ],
        "expectedPairsNotContainKeys": ["_e"],
    })

    # All-default params with explicit → contains _e=1
    serialize_cases.append({
        "name": "serialize all defaults with explicit=True",
        "input": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": default_conversion,
            "interval": default_interval,
            "charts": True,
            "query_string": "",
            "explicit": True,
        },
        "options": {"includeCharts": True},
        "expectedPairsContain": [
            ["conversion", default_conversion],
            ["interval", default_interval],
            ["_e", "1"],
        ],
    })

    # SerializeOptions.explicit=True also adds _e
    serialize_cases.append({
        "name": "serialize with options.explicit=True",
        "input": {
            "time": "2024",
            "account": "",
            "filter": "",
            "conversion": default_conversion,
            "interval": default_interval,
            "charts": True,
            "query_string": "",
            "explicit": False,
        },
        "options": {"includeCharts": True, "explicit": True},
        "expectedPairsContain": [
            ["time", "2024"],
            ["_e", "1"],
        ],
    })

    # charts=false serializes as charts=false
    serialize_cases.append({
        "name": "serialize charts=false",
        "input": {
            "time": "",
            "account": "",
            "filter": "",
            "conversion": default_conversion,
            "interval": default_interval,
            "charts": False,
            "query_string": "",
            "explicit": False,
        },
        "options": {"includeCharts": True},
        "expectedPairsContain": [
            ["conversion", default_conversion],
            ["interval", default_interval],
            ["charts", "false"],
        ],
    })

    # Legacy conversion value normalises to canonical in output
    for alias_from, alias_to in conversion_aliases.items():
        serialize_cases.append({
            "name": f"serialise converts alias '{alias_from}' to canonical '{alias_to}'",
            "input": {
                "time": "",
                "account": "",
                "filter": "",
                # Pass the alias as the user-facing conversion value
                "conversion": alias_from,
                "interval": default_interval,
                "charts": True,
                "query_string": "",
                "explicit": False,
            },
            "options": {"includeCharts": True},
            "expectedPairsContain": [
                ["conversion", alias_to],
                ["interval", default_interval],
            ],
        })

    # ------------------------------------------------------------------
    # ROUNDTRIP CASES — parse → serialize → parse == original
    # ------------------------------------------------------------------
    roundtrip_inputs = [
        {
            "name": "Chinese account + explicit flag",
            "urlParams": {
                "account": "资产:现金",
                "conversion": "units",
                "_e": "1",
            },
        },
        {
            "name": "all params + explicit",
            "urlParams": {
                "time": "2024",
                "account": "Expenses:Food",
                "filter": "#tag",
                "conversion": "EUR",
                "interval": "quarter",
                "charts": "false",
                "_e": "1",
            },
        },
        {
            "name": "legacy alias 'unit'",
            "urlParams": {"conversion": "unit"},
        },
        {
            "name": "legacy alias 'cost'",
            "urlParams": {"conversion": "cost"},
        },
        {
            "name": "whitespace everywhere",
            "urlParams": {
                "time": "  2024  ",
                "account": "  Assets:Cash  ",
                "filter": "  #tag  ",
                "interval": "  YEAR  ",
            },
        },
    ]

    for rt in roundtrip_inputs:
        roundtrip_cases.append({
            "name": rt["name"],
            "input": rt["urlParams"],
        })

    # ------------------------------------------------------------------
    # Assemble final structure
    # ------------------------------------------------------------------
    return {
        "$schema": "query_params_test_cases.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generatedFrom": str(SCHEMA_PATH.name),
        "schemaVersion": schema.get("metadata", {}).get("version", "1.0.0"),
        "parseCases": parse_cases,
        "serializeCases": serialize_cases,
        "roundtripCases": roundtrip_cases,
    }


def main() -> int:
    schema = load_schema()
    test_cases = build_test_cases(schema)

    TEST_CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TEST_CASES_PATH.open("w", encoding="utf-8") as f:
        json.dump(test_cases, f, ensure_ascii=False, indent=2)
        f.write("\n")

    n_parse = len(test_cases["parseCases"])
    n_ser = len(test_cases["serializeCases"])
    n_rt = len(test_cases["roundtripCases"])
    print(
        f"[OK] Generated {n_parse} parse + {n_ser} serialize + {n_rt} roundtrip "
        f"= {n_parse + n_ser + n_rt} test cases → "
        f"{TEST_CASES_PATH.relative_to(PROJECT_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
