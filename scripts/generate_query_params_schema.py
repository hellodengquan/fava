#!/usr/bin/env python3
"""Code generator for Fava's shared query parameter schema.

Reads the single-source-of-truth JSON schema from ``schemas/query_params.schema.json``
and generates:

1. ``src/fava/core/_query_params_schema_generated.py`` - Python constants and schema
2. ``frontend/src/lib/_query_params_schema_generated.ts`` - TypeScript constants and schema

Usage::

    python scripts/generate_query_params_schema.py

The generated files contain auto-generated markers and should not be edited by hand.
Modify ``schemas/query_params.schema.json`` instead, then re-run this generator.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "query_params.schema.json"
PYTHON_OUT = PROJECT_ROOT / "src" / "fava" / "core" / "_query_params_schema_generated.py"
TYPESCRIPT_OUT = (
    PROJECT_ROOT
    / "frontend"
    / "src"
    / "lib"
    / "_query_params_schema_generated.ts"
)

PYTHON_HEADER = '''\
"""Auto-generated query parameter schema constants.

DO NOT EDIT BY HAND!
This file is generated from ``schemas/query_params.schema.json`` by
``scripts/generate_query_params_schema.py``.

To make changes:
1. Edit the JSON schema file.
2. Re-run the generator script.

Generated at: {generated_at}
"""

from __future__ import annotations

from typing import Literal

'''

TYPESCRIPT_HEADER = '''\
/**
 * Auto-generated query parameter schema constants.
 *
 * ⚠️  DO NOT EDIT BY HAND!
 *
 * This file is generated from `schemas/query_params.schema.json` by
 * `scripts/generate_query_params_schema.py`.
 *
 * To make changes:
 * 1. Edit the JSON schema file.
 * 2. Re-run the generator script.
 *
 * @generatedAt {generated_at}
 */

'''

PYTHON_FOOTER = '''
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
'''

TYPESCRIPT_FOOTER = '''
'''


def load_schema() -> dict[str, Any]:
    """Load and validate the JSON schema."""
    if not SCHEMA_PATH.exists():
        print(f"ERROR: Schema not found at {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(1)
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    required_top = [
        "fieldNameAliases",
        "conversionAliases",
        "intervalValidValues",
        "defaultConversion",
        "defaultInterval",
        "fields",
    ]
    for key in required_top:
        if key not in schema:
            print(f"ERROR: Schema missing top-level key '{key}'", file=sys.stderr)
            sys.exit(1)
    return schema


def py_quote(value: Any) -> str:
    """Quote a Python literal value appropriately."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if value is None:
        return "None"
    return repr(value)


def ts_quote(value: Any) -> str:
    """Quote a TypeScript literal value appropriately."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if value is None:
        return "null"
    return json.dumps(value)


def generate_python(schema: dict[str, Any], generated_at: str) -> str:
    """Generate the Python output file."""
    lines: list[str] = []

    field_aliases = schema["fieldNameAliases"]
    conversion_aliases = schema["conversionAliases"]
    interval_values = schema["intervalValidValues"]
    default_conversion = schema["defaultConversion"]
    default_interval = schema["defaultInterval"]
    fields = schema["fields"]

    # QUERY_PARAM_NAMES
    lines.append("# Canonical query parameter URL names, keyed by logical constant.")
    lines.append("QUERY_PARAM_NAMES = {")
    for const_name, url_name in field_aliases.items():
        lines.append(f'    "{const_name}": {py_quote(url_name)},')
    lines.append("}")
    lines.append("")

    # EXPLICIT_PARAM_NAME
    lines.append("# Shortcut to the explicit flag's URL name.")
    lines.append(f'EXPLICIT_PARAM_NAME = QUERY_PARAM_NAMES["EXPLICIT"]')
    lines.append("")

    # CONVERSION_ALIASES
    lines.append("# Deprecated-to-canonical mapping for conversion values.")
    lines.append("CONVERSION_ALIASES = {")
    for old, new in conversion_aliases.items():
        lines.append(f"    {py_quote(old)}: {py_quote(new)},")
    lines.append("}")
    lines.append("")

    # QueryParamName Literal type
    all_names = sorted(field_aliases.values())
    lines.append("# Union type of all valid query parameter URL names.")
    lines.append("QueryParamName = Literal[")
    for name in all_names:
        lines.append(f"    {py_quote(name)},")
    lines.append("]")
    lines.append("")

    # DEFAULT_CONVERSION
    lines.append("# Default value for the conversion parameter.")
    lines.append(f"DEFAULT_CONVERSION = {py_quote(default_conversion)}")
    lines.append("")

    # DEFAULT_INTERVAL_STR
    lines.append("# Default value for the interval parameter (as string; see also fava.util.date.Month).")
    lines.append(f"DEFAULT_INTERVAL_STR = {py_quote(default_interval)}")
    lines.append("")

    # INTERVAL_VALID_VALUES
    lines.append("# Valid string values accepted by the interval parameter.")
    lines.append("INTERVAL_VALID_VALUES: tuple[str, ...] = (")
    for val in interval_values:
        lines.append(f"    {py_quote(val)},")
    lines.append(")")
    lines.append("")

    # SYNCED_QUERY_PARAM_NAMES
    synced = sorted(
        name for name, meta in fields.items() if meta.get("synced", False)
    )
    lines.append("# Subset of params that must be kept in sync across frontend/backend stores.")
    lines.append("SYNCED_QUERY_PARAM_NAMES: tuple[QueryParamName, ...] = (")
    for name in synced:
        lines.append(f"    {py_quote(name)},")
    lines.append(")")
    lines.append("")

    # FIELD_DATACLASS_MAP
    lines.append("# Maps each URL parameter name to its QueryParams dataclass field name.")
    lines.append("FIELD_DATACLASS_MAP: dict[str, str] = {")
    for url_name, meta in fields.items():
        lines.append(f"    {py_quote(url_name)}: {py_quote(meta['dataclassFieldName'])},")
    lines.append("}")
    lines.append("")

    # QUERY_PARAM_SCHEMA_META - the declarative schema dict (without callables)
    lines.append("# Declarative schema metadata — all non-callable fields shared between Python and TS.")
    lines.append("QUERY_PARAM_SCHEMA_META: dict[str, dict[str, object]] = {")
    for url_name, meta in fields.items():
        lines.append(f"    {py_quote(url_name)}: {{")
        # default - use pythonDefault override if present for interval
        default_val = meta.get("pythonDefault", meta["default"])
        if url_name == "interval":
            # Month singleton will be referenced from fava.util.date, keep as string default in meta
            default_for_meta = meta["default"]
            lines.append(f'        "default": {py_quote(default_for_meta)},')
        else:
            lines.append(f'        "default": {py_quote(default_val)},')
        lines.append(f'        "type": {py_quote(meta["type"])},')
        lines.append(f'        "synced": {py_quote(meta["synced"])},')
        lines.append(
            f'        "serialize_default": {py_quote(meta["serializableDefault"])},'
        )
        lines.append(
            f'        "normalize_fn_name": {py_quote(meta["normalizeFnName"]["python"])},'
        )
        lines.append(
            f'        "dataclass_field": {py_quote(meta["dataclassFieldName"])},'
        )
        if meta.get("hasAliases"):
            lines.append('        "has_aliases": True,')
        if meta.get("hasValidValues"):
            lines.append(
                f'        "valid_values_ref": {py_quote(meta["validValuesRef"])},'
            )
        if meta.get("isExplicitFlag"):
            lines.append('        "is_explicit_flag": True,')
        if meta.get("pythonType"):
            lines.append(f'        "python_type": {py_quote(meta["pythonType"])},')
        lines.append("    },")
    lines.append("}")
    lines.append("")

    return "".join(
        [
            PYTHON_HEADER.format(generated_at=generated_at),
            "\n".join(lines),
            PYTHON_FOOTER,
        ]
    )


def generate_typescript(schema: dict[str, Any], generated_at: str) -> str:
    """Generate the TypeScript output file."""
    lines: list[str] = []

    field_aliases = schema["fieldNameAliases"]
    conversion_aliases = schema["conversionAliases"]
    interval_values = schema["intervalValidValues"]
    default_conversion = schema["defaultConversion"]
    default_interval = schema["defaultInterval"]
    fields = schema["fields"]

    # imports
    lines.append('import type { Interval } from "./interval.ts";')
    lines.append('import { DEFAULT_INTERVAL, INTERVALS } from "./interval.ts";')
    lines.append("")

    # QUERY_PARAM_NAMES
    lines.append("// Canonical query parameter URL names, keyed by logical constant.")
    lines.append("export const QUERY_PARAM_NAMES = {")
    for const_name, url_name in field_aliases.items():
        lines.append(f"  {const_name}: {ts_quote(url_name)},")
    lines.append("} as const;")
    lines.append("")

    # EXPLICIT_PARAM_NAME
    lines.append("// Shortcut to the explicit flag's URL name.")
    lines.append("export const EXPLICIT_PARAM_NAME = QUERY_PARAM_NAMES.EXPLICIT;")
    lines.append("")

    # CONVERSION_ALIASES
    lines.append("// Deprecated-to-canonical mapping for conversion values.")
    lines.append("export const CONVERSION_ALIASES: Readonly<Record<string, string>> = {")
    for old, new in conversion_aliases.items():
        lines.append(f"  {ts_quote(old)}: {ts_quote(new)},")
    lines.append("};")
    lines.append("")

    # QueryParamName type
    lines.append("// Union type of all valid query parameter URL names.")
    lines.append(
        "export type QueryParamName = (typeof QUERY_PARAM_NAMES)[keyof typeof QUERY_PARAM_NAMES];"
    )
    lines.append("")

    # DEFAULT_CONVERSION
    lines.append("// Default value for the conversion parameter.")
    lines.append(f"export const DEFAULT_CONVERSION = {ts_quote(default_conversion)};")
    lines.append("")

    # DEFAULT_INTERVAL_STR
    lines.append("// Default value for the interval parameter (as string; see also DEFAULT_INTERVAL).")
    lines.append(f"export const DEFAULT_INTERVAL_STR = {ts_quote(default_interval)};")
    lines.append("")

    # INTERVAL_VALID_VALUES
    lines.append("// Valid string values accepted by the interval parameter.")
    lines.append("export const INTERVAL_VALID_VALUES: readonly Interval[] = [")
    for val in interval_values:
        lines.append(f"  {ts_quote(val)},")
    lines.append("];")
    lines.append("")

    # SYNCED_QUERY_PARAM_NAMES
    synced = sorted(
        name for name, meta in fields.items() if meta.get("synced", False)
    )
    lines.append("// Subset of params that must be kept in sync across frontend/backend stores.")
    lines.append("export const SYNCED_QUERY_PARAM_NAMES: QueryParamName[] = [")
    for name in synced:
        lines.append(f"  {ts_quote(name)},")
    lines.append("];")
    lines.append("")

    # FIELD_DATACLASS_MAP
    lines.append("// Maps each URL parameter name to its QueryParams object field name.")
    lines.append("export const FIELD_DATACLASS_MAP: Readonly<Record<string, string>> = {")
    for url_name, meta in fields.items():
        lines.append(f"  {ts_quote(url_name)}: {ts_quote(meta['dataclassFieldName'])},")
    lines.append("};")
    lines.append("")

    # QUERY_PARAM_SCHEMA_META interface
    lines.append("// Declarative schema metadata — non-callable fields shared between Python and TS.")
    lines.append("export interface QueryParamSchemaMeta {")
    lines.append("  readonly default: string | boolean;")
    lines.append('  readonly type: "string" | "boolean";')
    lines.append("  readonly synced: boolean;")
    lines.append("  readonly serializeDefault: boolean;")
    lines.append("  readonly normalizeFnName: string;")
    lines.append("  readonly dataclassField: string;")
    lines.append("  readonly hasAliases?: boolean;")
    lines.append("  readonly validValuesRef?: string;")
    lines.append("  readonly isExplicitFlag?: boolean;")
    lines.append("  readonly typescriptType?: string;")
    lines.append("}")
    lines.append("")

    lines.append("export const QUERY_PARAM_SCHEMA_META: Record<string, QueryParamSchemaMeta> = {")
    for url_name, meta in fields.items():
        lines.append(f"  {ts_quote(url_name)}: {{")
        default_val = meta.get("typescriptDefault", meta["default"])
        if url_name == "interval":
            # For interval, keep string default in meta
            default_for_meta = meta["default"]
            lines.append(f"    default: {ts_quote(default_for_meta)},")
        else:
            lines.append(f"    default: {ts_quote(default_val)},")
        lines.append(f'    type: {ts_quote(meta["type"])},')
        lines.append(f"    synced: {ts_quote(meta['synced'])},")
        lines.append(f"    serializeDefault: {ts_quote(meta['serializableDefault'])},")
        lines.append(
            f'    normalizeFnName: {ts_quote(meta["normalizeFnName"]["typescript"])},'
        )
        lines.append(
            f'    dataclassField: {ts_quote(meta["dataclassFieldName"])},'
        )
        if meta.get("hasAliases"):
            lines.append("    hasAliases: true,")
        if meta.get("hasValidValues"):
            lines.append(f"    validValuesRef: {ts_quote(meta['validValuesRef'])},")
        if meta.get("isExplicitFlag"):
            lines.append("    isExplicitFlag: true,")
        if meta.get("typescriptType"):
            lines.append(f"    typescriptType: {ts_quote(meta['typescriptType'])},")
        lines.append("  },")
    lines.append("};")
    lines.append("")

    return "".join(
        [
            TYPESCRIPT_HEADER.format(generated_at=generated_at),
            "\n".join(lines),
            TYPESCRIPT_FOOTER,
        ]
    )


def ensure_parent_dir(path: Path) -> None:
    """Ensure the parent directory for an output file exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_if_changed(path: Path, content: str) -> bool:
    """Write content to path only if it differs; returns True if written."""
    ensure_parent_dir(path)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return False
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    schema = load_schema()
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    py_content = generate_python(schema, generated_at)
    ts_content = generate_typescript(schema, generated_at)

    py_wrote = write_if_changed(PYTHON_OUT, py_content)
    ts_wrote = write_if_changed(TYPESCRIPT_OUT, ts_content)

    if py_wrote:
        print(f"[OK] Generated Python -> {PYTHON_OUT.relative_to(PROJECT_ROOT)}")
    else:
        print(f"[skip] Python up-to-date -> {PYTHON_OUT.relative_to(PROJECT_ROOT)}")

    if ts_wrote:
        print(f"[OK] Generated TypeScript -> {TYPESCRIPT_OUT.relative_to(PROJECT_ROOT)}")
    else:
        print(f"[skip] TypeScript up-to-date -> {TYPESCRIPT_OUT.relative_to(PROJECT_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
