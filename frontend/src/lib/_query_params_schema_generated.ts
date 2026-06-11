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
 * @generatedAt 2026-06-11T11:41:27+00:00
 */

import type { Interval } from "./interval.ts";
import { DEFAULT_INTERVAL, INTERVALS } from "./interval.ts";

// Canonical query parameter URL names, keyed by logical constant.
export const QUERY_PARAM_NAMES = {
  TIME: "time",
  ACCOUNT: "account",
  FILTER: "filter",
  CONVERSION: "conversion",
  INTERVAL: "interval",
  CHARTS: "charts",
  QUERY_STRING: "query_string",
  EXPLICIT: "_e",
} as const;

// Shortcut to the explicit flag's URL name.
export const EXPLICIT_PARAM_NAME = QUERY_PARAM_NAMES.EXPLICIT;

// Deprecated-to-canonical mapping for conversion values.
export const CONVERSION_ALIASES: Readonly<Record<string, string>> = {
  "unit": "units",
  "units": "units",
  "cost": "at_cost",
  "value": "at_value",
};

// Union type of all valid query parameter URL names.
export type QueryParamName = (typeof QUERY_PARAM_NAMES)[keyof typeof QUERY_PARAM_NAMES];

// Default value for the conversion parameter.
export const DEFAULT_CONVERSION = "at_cost";

// Default value for the interval parameter (as string; see also DEFAULT_INTERVAL).
export const DEFAULT_INTERVAL_STR = "month";

// Valid string values accepted by the interval parameter.
export const INTERVAL_VALID_VALUES: readonly Interval[] = [
  "year",
  "quarter",
  "month",
  "week",
  "day",
];

// Subset of params that must be kept in sync across frontend/backend stores.
export const SYNCED_QUERY_PARAM_NAMES: QueryParamName[] = [
  "account",
  "charts",
  "conversion",
  "filter",
  "interval",
  "time",
];

// Maps each URL parameter name to its QueryParams object field name.
export const FIELD_DATACLASS_MAP: Readonly<Record<string, string>> = {
  "time": "time",
  "account": "account",
  "filter": "filter",
  "conversion": "conversion",
  "interval": "interval",
  "charts": "charts",
  "query_string": "query_string",
  "_e": "explicit",
};

// Declarative schema metadata — non-callable fields shared between Python and TS.
export interface QueryParamSchemaMeta {
  readonly default: string | boolean;
  readonly type: "string" | "boolean";
  readonly synced: boolean;
  readonly serializeDefault: boolean;
  readonly normalizeFnName: string;
  readonly dataclassField: string;
  readonly hasAliases?: boolean;
  readonly validValuesRef?: string;
  readonly isExplicitFlag?: boolean;
  readonly typescriptType?: string;
}

export const QUERY_PARAM_SCHEMA_META: Record<string, QueryParamSchemaMeta> = {
  "time": {
    default: "",
    type: "string",
    synced: true,
    serializeDefault: false,
    normalizeFnName: "normalizeTime",
    dataclassField: "time",
  },
  "account": {
    default: "",
    type: "string",
    synced: true,
    serializeDefault: false,
    normalizeFnName: "normalizeAccount",
    dataclassField: "account",
  },
  "filter": {
    default: "",
    type: "string",
    synced: true,
    serializeDefault: false,
    normalizeFnName: "normalizeFilter",
    dataclassField: "filter",
  },
  "conversion": {
    default: "at_cost",
    type: "string",
    synced: true,
    serializeDefault: true,
    normalizeFnName: "normalizeConversion",
    dataclassField: "conversion",
    hasAliases: true,
  },
  "interval": {
    default: "month",
    type: "string",
    synced: true,
    serializeDefault: true,
    normalizeFnName: "normalizeInterval",
    dataclassField: "interval",
    validValuesRef: "intervalValidValues",
    typescriptType: "Interval",
  },
  "charts": {
    default: true,
    type: "boolean",
    synced: true,
    serializeDefault: false,
    normalizeFnName: "normalizeCharts",
    dataclassField: "charts",
  },
  "query_string": {
    default: "",
    type: "string",
    synced: false,
    serializeDefault: false,
    normalizeFnName: "normalizeQueryString",
    dataclassField: "query_string",
  },
  "_e": {
    default: false,
    type: "boolean",
    synced: false,
    serializeDefault: false,
    normalizeFnName: "normalizeExplicit",
    dataclassField: "explicit",
    isExplicitFlag: true,
  },
};

