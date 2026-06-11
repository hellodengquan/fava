import { log_warn } from "../log.ts";
import type { Interval } from "./interval.ts";
import { DEFAULT_INTERVAL, INTERVALS, getInterval } from "./interval.ts";

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

export const EXPLICIT_PARAM_NAME = QUERY_PARAM_NAMES.EXPLICIT;

export const CONVERSION_ALIASES: Readonly<Record<string, string>> = {
  unit: "units",
  units: "units",
  cost: "at_cost",
  value: "at_value",
};

export type QueryParamName =
  (typeof QUERY_PARAM_NAMES)[keyof typeof QUERY_PARAM_NAMES];

export const DEFAULT_CONVERSION = "at_cost";

export interface QueryParams {
  time: string;
  account: string;
  filter: string;
  conversion: string;
  interval: Interval;
  charts: boolean;
  query_string: string;
  explicit: boolean;
}

export const DEFAULT_QUERY_PARAMS: QueryParams = {
  time: "",
  account: "",
  filter: "",
  conversion: DEFAULT_CONVERSION,
  interval: DEFAULT_INTERVAL,
  charts: true,
  query_string: "",
  explicit: false,
};

export function normalizeTime(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  return trimmed;
}

export function normalizeAccount(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  return trimmed;
}

export function normalizeFilter(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  return trimmed;
}

export function normalizeConversion(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) {
    return DEFAULT_CONVERSION;
  }
  const lower = trimmed.toLowerCase();
  const aliased = CONVERSION_ALIASES[lower];
  if (aliased !== undefined && aliased !== trimmed) {
    log_warn(
      `[query_params] Deprecated conversion value: "${trimmed}", using alias "${aliased}"`,
    );
    return aliased;
  }
  return trimmed;
}

export function normalizeInterval(value: string | null | undefined): Interval {
  const trimmed = value?.trim().toLowerCase();
  const normalized = getInterval(trimmed ?? null);
  if (
    value != null &&
    value !== "" &&
    !INTERVALS.includes(trimmed as Interval)
  ) {
    log_warn(
      `[query_params] Invalid interval value: "${value}", falling back to default "${DEFAULT_INTERVAL}"`,
    );
  }
  return normalized;
}

export function normalizeCharts(value: string | null | undefined): boolean {
  return value !== "false";
}

export function normalizeQueryString(value: string | null | undefined): string {
  return value ?? "";
}

export function normalizeExplicit(value: string | null | undefined): boolean {
  if (value === null || value === undefined) return false;
  return value === "1" || value.toLowerCase() === "true";
}

export const SYNCED_QUERY_PARAM_NAMES: QueryParamName[] = [
  QUERY_PARAM_NAMES.ACCOUNT,
  QUERY_PARAM_NAMES.CHARTS,
  QUERY_PARAM_NAMES.CONVERSION,
  QUERY_PARAM_NAMES.FILTER,
  QUERY_PARAM_NAMES.INTERVAL,
  QUERY_PARAM_NAMES.TIME,
];

export interface QueryParamSchema {
  default: string | boolean;
  type: "string" | "boolean";
  synced: boolean;
  normalizeFn: (value: string | null | undefined) => string | boolean | Interval;
  serializableDefault: boolean;
  validValues?: readonly string[];
  aliases?: Readonly<Record<string, string>>;
}

export const QUERY_PARAM_SCHEMA: Record<string, QueryParamSchema> = {
  time: {
    default: "",
    type: "string",
    synced: true,
    normalizeFn: normalizeTime,
    serializableDefault: false,
  },
  account: {
    default: "",
    type: "string",
    synced: true,
    normalizeFn: normalizeAccount,
    serializableDefault: false,
  },
  filter: {
    default: "",
    type: "string",
    synced: true,
    normalizeFn: normalizeFilter,
    serializableDefault: false,
  },
  conversion: {
    default: DEFAULT_CONVERSION,
    type: "string",
    synced: true,
    normalizeFn: normalizeConversion,
    serializableDefault: true,
    aliases: CONVERSION_ALIASES,
  },
  interval: {
    default: DEFAULT_INTERVAL,
    type: "string",
    synced: true,
    normalizeFn: normalizeInterval,
    serializableDefault: true,
    validValues: INTERVALS,
  },
  charts: {
    default: true,
    type: "boolean",
    synced: true,
    normalizeFn: normalizeCharts,
    serializableDefault: false,
  },
  query_string: {
    default: "",
    type: "string",
    synced: false,
    normalizeFn: normalizeQueryString,
    serializableDefault: false,
  },
  _e: {
    default: false,
    type: "boolean",
    synced: false,
    normalizeFn: normalizeExplicit,
    serializableDefault: false,
  },
};

export function parseQueryParams(
  params: URLSearchParams | Record<string, string | null | undefined>,
): QueryParams {
  const get = (key: string): string | null | undefined => {
    if (params instanceof URLSearchParams) {
      return params.get(key);
    }
    return params[key];
  };

  return {
    time: normalizeTime(get(QUERY_PARAM_NAMES.TIME)),
    account: normalizeAccount(get(QUERY_PARAM_NAMES.ACCOUNT)),
    filter: normalizeFilter(get(QUERY_PARAM_NAMES.FILTER)),
    conversion: normalizeConversion(get(QUERY_PARAM_NAMES.CONVERSION)),
    interval: normalizeInterval(get(QUERY_PARAM_NAMES.INTERVAL)),
    charts: normalizeCharts(get(QUERY_PARAM_NAMES.CHARTS)),
    query_string: normalizeQueryString(get(QUERY_PARAM_NAMES.QUERY_STRING)),
    explicit: normalizeExplicit(get(QUERY_PARAM_NAMES.EXPLICIT)),
  };
}

export interface SerializeOptions {
  omitDefaults?: boolean;
  includeCharts?: boolean;
  includeQueryString?: boolean;
  explicit?: boolean;
}

export function serializeQueryParams(
  params: Partial<QueryParams>,
  options: SerializeOptions = {},
): URLSearchParams {
  const {
    omitDefaults = false,
    includeCharts = true,
    includeQueryString = false,
    explicit = false,
  } = options;

  const result = new URLSearchParams();

  const time = normalizeTime(params.time);
  if (time && (!omitDefaults || time !== DEFAULT_QUERY_PARAMS.time)) {
    result.set(QUERY_PARAM_NAMES.TIME, time);
  }

  const account = normalizeAccount(params.account);
  if (account && (!omitDefaults || account !== DEFAULT_QUERY_PARAMS.account)) {
    result.set(QUERY_PARAM_NAMES.ACCOUNT, account);
  }

  const filter = normalizeFilter(params.filter);
  if (filter && (!omitDefaults || filter !== DEFAULT_QUERY_PARAMS.filter)) {
    result.set(QUERY_PARAM_NAMES.FILTER, filter);
  }

  const conversion = normalizeConversion(params.conversion);
  if (!omitDefaults || conversion !== DEFAULT_QUERY_PARAMS.conversion) {
    result.set(QUERY_PARAM_NAMES.CONVERSION, conversion);
  }

  const interval = normalizeInterval(params.interval);
  if (!omitDefaults || interval !== DEFAULT_QUERY_PARAMS.interval) {
    result.set(QUERY_PARAM_NAMES.INTERVAL, interval);
  }

  if (includeCharts) {
    const charts = normalizeCharts(
      params.charts === undefined
        ? params.charts
        : params.charts
          ? ""
          : "false",
    );
    if (!omitDefaults || !charts) {
      if (!charts) {
        result.set(QUERY_PARAM_NAMES.CHARTS, "false");
      }
    }
  }

  if (includeQueryString) {
    const query_string = normalizeQueryString(params.query_string);
    if (query_string) {
      result.set(QUERY_PARAM_NAMES.QUERY_STRING, query_string);
    }
  }

  const hasExplicitParam = params.explicit === true;
  const allDefaults =
    time === DEFAULT_QUERY_PARAMS.time &&
    account === DEFAULT_QUERY_PARAMS.account &&
    filter === DEFAULT_QUERY_PARAMS.filter &&
    conversion === DEFAULT_QUERY_PARAMS.conversion &&
    interval === DEFAULT_QUERY_PARAMS.interval &&
    (!includeCharts || normalizeCharts("") === DEFAULT_QUERY_PARAMS.charts);

  if (explicit || hasExplicitParam || (allDefaults && params.explicit === true)) {
    result.set(EXPLICIT_PARAM_NAME, "1");
  }

  return result;
}

export function setQueryParamOnURL(
  url: URL,
  key: QueryParamName,
  rawValue: string | boolean | Interval,
): void {
  let value: string;

  if (key === QUERY_PARAM_NAMES.EXPLICIT) {
    if (rawValue === true || rawValue === "1" || rawValue === "true") {
      url.searchParams.set(key, "1");
    } else {
      url.searchParams.delete(key);
    }
    return;
  }

  if (key === QUERY_PARAM_NAMES.CHARTS) {
    value = rawValue === false ? "false" : "";
  } else if (key === QUERY_PARAM_NAMES.INTERVAL) {
    value = rawValue as string;
  } else {
    value = rawValue as string;
  }

  if (key === QUERY_PARAM_NAMES.CHARTS) {
    if (value) {
      url.searchParams.set(key, value);
    } else {
      url.searchParams.delete(key);
    }
    return;
  }

  if (key === QUERY_PARAM_NAMES.CONVERSION) {
    const normalized = normalizeConversion(value);
    if (normalized && normalized !== DEFAULT_CONVERSION) {
      url.searchParams.set(key, normalized);
    } else {
      url.searchParams.delete(key);
    }
    return;
  }

  if (key === QUERY_PARAM_NAMES.INTERVAL) {
    const normalized = normalizeInterval(value);
    if (normalized !== DEFAULT_INTERVAL) {
      url.searchParams.set(key, normalized);
    } else {
      url.searchParams.delete(key);
    }
    return;
  }

  if (value) {
    url.searchParams.set(key, value);
  } else {
    url.searchParams.delete(key);
  }
}

export interface Filters {
  account: string;
  filter: string;
  time: string;
}

export interface FiltersConversionInterval extends Filters {
  conversion: string;
  interval: Interval;
}

export function getFilters(params: QueryParams): Filters {
  return {
    account: params.account,
    filter: params.filter,
    time: params.time,
  };
}

export function getFiltersConversionInterval(
  params: QueryParams,
): FiltersConversionInterval {
  return {
    account: params.account,
    filter: params.filter,
    time: params.time,
    conversion: params.conversion,
    interval: params.interval,
  };
}

export function getFiltersFromURL(url: URL): Filters {
  return getFilters(parseQueryParams(url.searchParams));
}

export function getFiltersConversionIntervalFromURL(
  url: URL,
): FiltersConversionInterval {
  return getFiltersConversionInterval(parseQueryParams(url.searchParams));
}

export function isExplicitURL(url: URL): boolean {
  const value = url.searchParams.get(EXPLICIT_PARAM_NAME);
  return normalizeExplicit(value);
}

export function markExplicit(url: URL): void {
  url.searchParams.set(EXPLICIT_PARAM_NAME, "1");
}

export function unmarkExplicit(url: URL): void {
  url.searchParams.delete(EXPLICIT_PARAM_NAME);
}
