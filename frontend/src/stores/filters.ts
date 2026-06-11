import { derived } from "svelte/store";

import {
  DEFAULT_CONVERSION,
  DEFAULT_QUERY_PARAMS,
  getFilters,
  getFiltersConversionInterval,
  parseQueryParams,
  QUERY_PARAM_NAMES,
  type Filters,
  type FiltersConversionInterval,
  type QueryParams,
} from "../lib/query_params.ts";
import { searchParams } from "./url.ts";

export { DEFAULT_CONVERSION };
export type { Filters, FiltersConversionInterval, QueryParams };

const parsedParams = derived(searchParams, ($searchParams) =>
  parseQueryParams($searchParams),
);

export const time_filter = derived(
  parsedParams,
  ($params) => $params.time,
);

export const account_filter = derived(
  parsedParams,
  ($params) => $params.account,
);

export const fql_filter = derived(
  parsedParams,
  ($params) => $params.filter,
);

export const conversion = derived(
  parsedParams,
  ($params) => $params.conversion,
);

export const interval = derived(
  parsedParams,
  ($params) => $params.interval,
);

export const show_charts = derived(
  parsedParams,
  ($params) => $params.charts,
);

export const query_params = parsedParams;

export const filter_params = derived(
  parsedParams,
  ($params): Filters => getFilters($params),
);

export function getURLFilters(url: URL): FiltersConversionInterval {
  return getFiltersConversionInterval(parseQueryParams(url.searchParams));
}

export { DEFAULT_QUERY_PARAMS, QUERY_PARAM_NAMES };
