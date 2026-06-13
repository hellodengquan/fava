import { derived, type Readable } from "svelte/store";

import { searchParams } from "./url.ts";

/** The time filter. */
export const time_filter = derived(
  searchParams,
  ($searchParams) => $searchParams.get("time") ?? "",
);
/** The account filter. */
export const account_filter = derived(
  searchParams,
  ($searchParams) => $searchParams.get("account") ?? "",
);
/** The filter with our custom query syntax. */
export const fql_filter = derived(
  searchParams,
  ($searchParams) => $searchParams.get("filter") ?? "",
);

/** The three entry filters that Fava supports. */
export interface Filters extends Record<string, string> {
  account: string;
  filter: string;
  time: string;
}

/** The three filters as well as conversion and interval. */
export interface FiltersConversionInterval extends Filters {
  conversion: string;
  interval: string;
}

/**
 * Unified report filter context for the frontend.
 *
 * This interface mirrors the backend ReportContext class, ensuring that
 * the frontend and backend use the same parameter structure. It provides
 * a single source of truth for all filtering and display parameters used
 * across reports, ensuring consistency between charts and tables.
 */
export interface ReportFilterContext extends FiltersConversionInterval {
  /** Time filter string (e.g., "2024", "2024-Q1", "2024-01-01"). */
  time: string;
  /** Account filter string (account name or regex pattern). */
  account: string;
  /** Advanced filter string in Fava's filter query language. */
  filter: string;
  /** Conversion mode string (e.g., "at_cost", "USD", "EUR"). */
  conversion: string;
  /** Interval string for grouping data (e.g., "month", "year"). */
  interval: string;
}

/**
 * Create a ReportFilterContext from a URL.
 *
 * This function ensures consistent parameter extraction from URLs,
 * mirroring the backend ReportContext.from_request() method.
 *
 * @param url - The URL to extract filter parameters from.
 * @returns A ReportFilterContext populated from the URL's search params.
 */
export function getReportFilterContext(url: URL): ReportFilterContext {
  const conversion = url.searchParams.get("conversion");
  const interval = url.searchParams.get("interval");
  return {
    time: url.searchParams.get("time") ?? "",
    account: url.searchParams.get("account") ?? "",
    filter: url.searchParams.get("filter") ?? "",
    conversion: conversion || "at_cost",
    interval: interval ? interval.toLowerCase() : "month",
  };
}

/**
 * Create ReportFilterContext from a dictionary of parameters.
 *
 * @param params - Dictionary containing filter parameters.
 * @returns A ReportFilterContext populated from the dictionary.
 */
export function reportFilterContextFromDict(
  params: Partial<ReportFilterContext>,
): ReportFilterContext {
  return {
    time: params.time ?? "",
    account: params.account ?? "",
    filter: params.filter ?? "",
    conversion: params.conversion || "at_cost",
    interval: params.interval ? params.interval.toLowerCase() : "month",
  };
}

/**
 * Convert a ReportFilterContext to URL parameters.
 *
 * @param context - The ReportFilterContext to convert.
 * @returns Dictionary with all context parameters suitable for URL search params.
 */
export function reportFilterContextToUrlParams(
  context: ReportFilterContext,
): Record<string, string> {
  const params: Record<string, string> = {};
  if (context.time) params.time = context.time;
  if (context.account) params.account = context.account;
  if (context.filter) params.filter = context.filter;
  if (context.conversion && context.conversion !== "at_cost") {
    params.conversion = context.conversion;
  }
  if (context.interval && context.interval !== "month") {
    params.interval = context.interval;
  }
  return params;
}

/**
 * Check if two ReportFilterContext objects are equal.
 *
 * @param a - First context.
 * @param b - Second context.
 * @returns True if all fields are equal.
 */
export function reportFilterContextEqual(
  a: ReportFilterContext,
  b: ReportFilterContext,
): boolean {
  return (
    a.time === b.time &&
    a.account === b.account &&
    a.filter === b.filter &&
    a.conversion === b.conversion &&
    a.interval === b.interval
  );
}

/** The current filters, can be used as URL parameters. */
export const filter_params = derived(
  [time_filter, account_filter, fql_filter],
  ([$time_filter, $account_filter, $fql_filter]): Filters => ({
    time: $time_filter,
    account: $account_filter,
    filter: $fql_filter,
  }),
);

/**
 * The unified report filter context store.
 *
 * This derived store provides a single source of truth for all report
 * filtering parameters. It should be used by both chart and table
 * components to ensure they use the same data source.
 */
export const report_filter_context: Readable<ReportFilterContext> = derived(
  searchParams,
  ($searchParams): ReportFilterContext => {
    const conversion = $searchParams.get("conversion");
    const interval = $searchParams.get("interval");
    return {
      time: $searchParams.get("time") ?? "",
      account: $searchParams.get("account") ?? "",
      filter: $searchParams.get("filter") ?? "",
      conversion: conversion || "at_cost",
      interval: interval ? interval.toLowerCase() : "month",
    };
  },
);

/**
 * @deprecated Use getReportFilterContext() instead for consistency with the backend.
 */
export function getURLFilters(url: URL): FiltersConversionInterval {
  return {
    account: url.searchParams.get("account") ?? "",
    filter: url.searchParams.get("filter") ?? "",
    time: url.searchParams.get("time") ?? "",
    conversion: url.searchParams.get("conversion") ?? "",
    interval: url.searchParams.get("interval") ?? "",
  };
}
