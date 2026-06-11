"""Auto-generated query parameter schema constants.

DO NOT EDIT BY HAND!
This file is generated from ``schemas/query_params.schema.json`` by
``scripts/generate_query_params_schema.py``.

To make changes:
1. Edit the JSON schema file.
2. Re-run the generator script.

Generated at: 2026-06-11T11:41:27+00:00
"""

from __future__ import annotations

from typing import Literal

# Canonical query parameter URL names, keyed by logical constant.
QUERY_PARAM_NAMES = {
    "TIME": "time",
    "ACCOUNT": "account",
    "FILTER": "filter",
    "CONVERSION": "conversion",
    "INTERVAL": "interval",
    "CHARTS": "charts",
    "QUERY_STRING": "query_string",
    "EXPLICIT": "_e",
}

# Shortcut to the explicit flag's URL name.
EXPLICIT_PARAM_NAME = QUERY_PARAM_NAMES["EXPLICIT"]

# Deprecated-to-canonical mapping for conversion values.
CONVERSION_ALIASES = {
    "unit": "units",
    "units": "units",
    "cost": "at_cost",
    "value": "at_value",
}

# Union type of all valid query parameter URL names.
QueryParamName = Literal[
    "_e",
    "account",
    "charts",
    "conversion",
    "filter",
    "interval",
    "query_string",
    "time",
]

# Default value for the conversion parameter.
DEFAULT_CONVERSION = "at_cost"

# Default value for the interval parameter (as string; see also fava.util.date.Month).
DEFAULT_INTERVAL_STR = "month"

# Valid string values accepted by the interval parameter.
INTERVAL_VALID_VALUES: tuple[str, ...] = (
    "year",
    "quarter",
    "month",
    "week",
    "day",
)

# Subset of params that must be kept in sync across frontend/backend stores.
SYNCED_QUERY_PARAM_NAMES: tuple[QueryParamName, ...] = (
    "account",
    "charts",
    "conversion",
    "filter",
    "interval",
    "time",
)

# Maps each URL parameter name to its QueryParams dataclass field name.
FIELD_DATACLASS_MAP: dict[str, str] = {
    "time": "time",
    "account": "account",
    "filter": "filter",
    "conversion": "conversion",
    "interval": "interval",
    "charts": "charts",
    "query_string": "query_string",
    "_e": "explicit",
}

# Declarative schema metadata — all non-callable fields shared between Python and TS.
QUERY_PARAM_SCHEMA_META: dict[str, dict[str, object]] = {
    "time": {
        "default": "",
        "type": "string",
        "synced": True,
        "serialize_default": False,
        "normalize_fn_name": "normalize_time",
        "dataclass_field": "time",
    },
    "account": {
        "default": "",
        "type": "string",
        "synced": True,
        "serialize_default": False,
        "normalize_fn_name": "normalize_account",
        "dataclass_field": "account",
    },
    "filter": {
        "default": "",
        "type": "string",
        "synced": True,
        "serialize_default": False,
        "normalize_fn_name": "normalize_filter",
        "dataclass_field": "filter",
    },
    "conversion": {
        "default": "at_cost",
        "type": "string",
        "synced": True,
        "serialize_default": True,
        "normalize_fn_name": "normalize_conversion",
        "dataclass_field": "conversion",
        "has_aliases": True,
    },
    "interval": {
        "default": "month",
        "type": "string",
        "synced": True,
        "serialize_default": True,
        "normalize_fn_name": "normalize_interval",
        "dataclass_field": "interval",
        "valid_values_ref": "intervalValidValues",
        "python_type": "Interval",
    },
    "charts": {
        "default": True,
        "type": "boolean",
        "synced": True,
        "serialize_default": False,
        "normalize_fn_name": "normalize_charts",
        "dataclass_field": "charts",
    },
    "query_string": {
        "default": "",
        "type": "string",
        "synced": False,
        "serialize_default": False,
        "normalize_fn_name": "normalize_query_string",
        "dataclass_field": "query_string",
    },
    "_e": {
        "default": False,
        "type": "boolean",
        "synced": False,
        "serialize_default": False,
        "normalize_fn_name": "normalize_explicit",
        "dataclass_field": "explicit",
        "is_explicit_flag": True,
    },
}

__all__ = [
    "QUERY_PARAM_NAMES",
    "EXPLICIT_PARAM_NAME",
    "CONVERSION_ALIASES",
    "QueryParamName",
    "DEFAULT_CONVERSION",
    "DEFAULT_INTERVAL_STR",
    "SYNCED_QUERY_PARAM_NAMES",
    "FIELD_DATACLASS_MAP",
    "INTERVAL_VALID_VALUES",
    "QUERY_PARAM_SCHEMA_META",
]
