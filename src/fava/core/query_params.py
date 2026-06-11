"""Unified query parameter parsing and serialization.

This module provides a canonical layer for parsing and serializing the
query parameters shared between the backend (Flask request args) and
the frontend (URL search params).

All declarative schema metadata (field names, defaults, aliases, etc.)
is auto-generated from the single-source-of-truth JSON schema at
``schemas/query_params.schema.json`` into the sibling module
:mod:`_query_params_schema_generated`.  Edit that JSON file and run
``python scripts/generate_query_params_schema.py`` to regenerate.

The language-specific normalisation/serialisation logic below must
mirror the TypeScript module ``frontend/src/lib/query_params.ts``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fava.core._query_params_schema_generated import CONVERSION_ALIASES
from fava.core._query_params_schema_generated import DEFAULT_CONVERSION
from fava.core._query_params_schema_generated import EXPLICIT_PARAM_NAME
from fava.core._query_params_schema_generated import FIELD_DATACLASS_MAP
from fava.core._query_params_schema_generated import QUERY_PARAM_NAMES
from fava.core._query_params_schema_generated import QUERY_PARAM_SCHEMA_META
from fava.core._query_params_schema_generated import QueryParamName
from fava.core._query_params_schema_generated import SYNCED_QUERY_PARAM_NAMES
from fava.util.date import INTERVALS
from fava.util.date import Month

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping

    from fava.util.date import Interval

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryParams:
    """The full set of shared query parameters."""

    time: str = ""
    account: str = ""
    filter: str = ""  # noqa: A002
    conversion: str = DEFAULT_CONVERSION
    interval: Interval = Month
    charts: bool = True
    query_string: str = ""
    explicit: bool = False

    def as_filters(self) -> Filters:
        """Return the three entry filters."""
        return Filters(
            account=self.account,
            filter=self.filter,
            time=self.time,
        )

    def as_filters_conversion_interval(self) -> FiltersConversionInterval:
        """Return filters together with conversion and interval."""
        return FiltersConversionInterval(
            account=self.account,
            filter=self.filter,
            time=self.time,
            conversion=self.conversion,
            interval=self.interval,
        )


@dataclass(frozen=True)
class Filters:
    """The three entry filters that Fava supports."""

    account: str = ""
    filter: str = ""  # noqa: A002
    time: str = ""


@dataclass(frozen=True)
class FiltersConversionInterval(Filters):
    """Filters together with conversion and interval."""

    conversion: str = DEFAULT_CONVERSION
    interval: Interval = Month


DEFAULT_QUERY_PARAMS = QueryParams()



def normalize_time(value: object | None) -> str:
    """Normalize the time filter value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_account(value: object | None) -> str:
    """Normalize the account filter value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_filter(value: object | None) -> str:
    """Normalize the advanced filter (FQL) value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_conversion(value: object | None) -> str:
    """Normalize the conversion string, falling back to the default.

    Handles deprecated alias values from older Fava 0.x versions
    (e.g. ``"unit"`` → ``"units"``, ``"cost"`` → ``"at_cost"``).
    """
    if value is None:
        return DEFAULT_CONVERSION
    if isinstance(value, str):
        trimmed = value.strip()
    else:
        trimmed = str(value).strip()

    if not trimmed:
        return DEFAULT_CONVERSION

    lower = trimmed.lower()
    aliased = CONVERSION_ALIASES.get(lower)
    if aliased is not None and aliased != trimmed:
        log.warning(
            "Deprecated conversion value: '%s', using alias '%s'",
            trimmed,
            aliased,
        )
        return aliased

    return trimmed


def normalize_interval(value: object | None) -> Interval:
    """Normalize the interval string, falling back to the default.

    Accepts either a string name (e.g. ``"year"``, ``"monthly"``) or an
    existing interval instance.  Unknown strings fall back to ``Month``
    with a warning log.
    """
    if value is None:
        return Month

    if value in INTERVALS.values():
        return value  # type: ignore[return-value]

    if isinstance(value, str):
        normalized = value.strip().lower()
    else:
        normalized = str(value).strip().lower()

    result = INTERVALS.get(normalized, Month)
    if result is Month and normalized not in INTERVALS and normalized != "":
        log.warning(
            "Invalid interval value: '%s', falling back to default 'month'",
            value,
        )
    return result


def normalize_charts(value: object | None) -> bool:
    """Normalize the charts flag.

    Charts are shown by default and only hidden when the value is exactly
    ``"false"`` (mirrors the frontend behaviour).
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value != "false"
    return str(value) != "false"


def normalize_query_string(value: object | None) -> str:
    """Normalize the BQL query string value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def normalize_explicit(value: object | None) -> bool:
    """Normalize the explicit flag.

    The flag is set when the query string contains ``_e=1`` or ``_e=true``,
    indicating that the default values were explicitly set by the user
    (as opposed to being implicit from the URL having no query string).
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value == "1" or value.lower() == "true"
    return False


# Build the full schema with callable references by enriching the generated meta.
# The generated module provides all declarative data; we attach runtime callables here.
_NORMALIZE_FN_TABLE: dict[str, object] = {
    "normalize_time": normalize_time,
    "normalize_account": normalize_account,
    "normalize_filter": normalize_filter,
    "normalize_conversion": normalize_conversion,
    "normalize_interval": normalize_interval,
    "normalize_charts": normalize_charts,
    "normalize_query_string": normalize_query_string,
    "normalize_explicit": normalize_explicit,
}

QUERY_PARAM_SCHEMA: dict[str, dict[str, object]] = {
    url_name: {
        "default": meta["default"],
        "type": meta["type"],
        "synced": meta["synced"],
        "serializable_default": meta["serialize_default"],
        "normalize_fn": _NORMALIZE_FN_TABLE[str(meta["normalize_fn_name"])],
        "aliases": CONVERSION_ALIASES if meta.get("has_aliases") else None,
        "valid_values": (
            list(INTERVALS.keys()) if meta.get("valid_values_ref") == "intervalValidValues" else None
        ),
    }
    for url_name, meta in QUERY_PARAM_SCHEMA_META.items()
}


def parse_query_params(
    params: Mapping[str, object] | None = None,
) -> QueryParams:
    """Parse query parameters from a mapping (e.g. ``request.args``)."""
    if params is None:
        return DEFAULT_QUERY_PARAMS

    def _get(name: str) -> object | None:
        try:
            return params.get(name)
        except AttributeError:
            return None

    return QueryParams(
        time=normalize_time(_get("time")),
        account=normalize_account(_get("account")),
        filter=normalize_filter(_get("filter")),
        conversion=normalize_conversion(_get("conversion")),
        interval=normalize_interval(_get("interval")),
        charts=normalize_charts(_get("charts")),
        query_string=normalize_query_string(_get("query_string")),
        explicit=normalize_explicit(_get("_e")),
    )


@dataclass(frozen=True)
class SerializeOptions:
    """Options for :func:`serialize_query_params`."""

    omit_defaults: bool = False
    include_charts: bool = True
    include_query_string: bool = False
    explicit: bool = False


def serialize_query_params(
    params: QueryParams | Filters | FiltersConversionInterval | Mapping[str, object],
    options: SerializeOptions | None = None,
) -> list[tuple[str, str]]:
    """Serialize parameters to a list of (name, value) pairs.

    The return value is directly usable with :func:`urllib.parse.urlencode`.
    """
    from collections.abc import Mapping as _Mapping

    opts = options or SerializeOptions()
    result: list[tuple[str, str]] = []

    if isinstance(params, _Mapping):
        parsed = parse_query_params(params)
    elif isinstance(params, FiltersConversionInterval):
        parsed = QueryParams(
            time=params.time,
            account=params.account,
            filter=params.filter,
            conversion=params.conversion,
            interval=params.interval,
        )
    elif isinstance(params, Filters):
        parsed = QueryParams(
            time=params.time,
            account=params.account,
            filter=params.filter,
        )
    else:
        parsed = params

    time = normalize_time(parsed.time)
    if time and (not opts.omit_defaults or time != DEFAULT_QUERY_PARAMS.time):
        result.append(("time", time))

    account = normalize_account(parsed.account)
    if account and (
        not opts.omit_defaults or account != DEFAULT_QUERY_PARAMS.account
    ):
        result.append(("account", account))

    filter_ = normalize_filter(parsed.filter)
    if filter_ and (
        not opts.omit_defaults or filter_ != DEFAULT_QUERY_PARAMS.filter
    ):
        result.append(("filter", filter_))

    conversion = normalize_conversion(parsed.conversion)
    if not opts.omit_defaults or conversion != DEFAULT_QUERY_PARAMS.conversion:
        result.append(("conversion", conversion))

    interval = normalize_interval(parsed.interval)
    interval_str = next(
        (k for k, v in INTERVALS.items() if v is interval),
        "month",
    )
    if not opts.omit_defaults or interval is not DEFAULT_QUERY_PARAMS.interval:
        result.append(("interval", interval_str))

    if opts.include_charts:
        charts = normalize_charts(parsed.charts)
        if not opts.omit_defaults or not charts:
            if not charts:
                result.append(("charts", "false"))

    if opts.include_query_string:
        query_string = normalize_query_string(parsed.query_string)
        if query_string:
            result.append(("query_string", query_string))

    explicit = getattr(parsed, "explicit", False)
    all_defaults = (
        time == DEFAULT_QUERY_PARAMS.time
        and account == DEFAULT_QUERY_PARAMS.account
        and filter_ == DEFAULT_QUERY_PARAMS.filter
        and conversion == DEFAULT_QUERY_PARAMS.conversion
        and interval is DEFAULT_QUERY_PARAMS.interval
        and (not opts.include_charts or charts == DEFAULT_QUERY_PARAMS.charts)
    )

    if opts.explicit or explicit or (all_defaults and explicit):
        result.append((EXPLICIT_PARAM_NAME, "1"))

    return result


def query_params_to_query_string(
    params: QueryParams | Filters | FiltersConversionInterval | Mapping[str, object],
    options: SerializeOptions | None = None,
) -> str:
    """Serialize parameters to a URL query string."""
    pairs = serialize_query_params(params, options)
    return urlencode(pairs)


def set_query_param_on_dict(
    values: dict[str, str],
    key: QueryParamName,
    raw_value: object,
) -> None:
    """Set a query parameter on a ``dict`` (used for ``url_for`` injections).

    Empty values (that match the default semantics) are removed, which
    mirrors the frontend ``set_query_param`` behaviour.
    """
    if key == "_e":
        if raw_value is True or raw_value == "1" or raw_value == "true":
            values["_e"] = "1"
        else:
            values.pop("_e", None)
        return

    if key == "charts":
        if raw_value is False or (isinstance(raw_value, str) and raw_value == "false"):
            values["charts"] = "false"
        else:
            values.pop("charts", None)
        return

    if key == "conversion":
        normalized = normalize_conversion(raw_value)
        if normalized and normalized != DEFAULT_CONVERSION:
            values["conversion"] = normalized
        else:
            values.pop("conversion", None)
        return

    if key == "interval":
        interval = normalize_interval(raw_value)
        if interval is not DEFAULT_QUERY_PARAMS.interval:
            interval_str = next(
                (k for k, v in INTERVALS.items() if v is interval),
                "month",
            )
            values["interval"] = interval_str
        else:
            values.pop("interval", None)
        return

    if isinstance(raw_value, str):
        value = raw_value
    else:
        value = str(raw_value) if raw_value is not None else ""

    if value:
        values[key] = value
    else:
        values.pop(key, None)


def get_filters_from_mapping(
    params: Mapping[str, object] | None,
) -> Filters:
    """Extract the three entry filters from a mapping."""
    return parse_query_params(params).as_filters()


def get_filters_conversion_interval_from_mapping(
    params: Mapping[str, object] | None,
) -> FiltersConversionInterval:
    """Extract filters + conversion + interval from a mapping."""
    return parse_query_params(params).as_filters_conversion_interval()


def is_explicit_url(params: Mapping[str, object] | None) -> bool:
    """Check if the URL parameters have the explicit flag set."""
    return parse_query_params(params).explicit


def mark_explicit(values: dict[str, str]) -> None:
    """Add the explicit flag to a values dict."""
    values[EXPLICIT_PARAM_NAME] = "1"


def unmark_explicit(values: dict[str, str]) -> None:
    """Remove the explicit flag from a values dict."""
    values.pop(EXPLICIT_PARAM_NAME, None)
