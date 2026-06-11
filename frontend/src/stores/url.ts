import { derived, writable } from "svelte/store";

import {
  SYNCED_QUERY_PARAM_NAMES,
  QUERY_PARAM_NAMES,
  serializeQueryParams,
  parseQueryParams,
  normalizeConversion,
  normalizeInterval,
  normalizeCharts,
} from "../lib/query_params.ts";

export const current_url = writable<URL>();

export const hash = derived(current_url, (u) => u.hash.slice(1));

export const pathname = derived(current_url, (u) => u.pathname);

const search = derived(current_url, (u) => u.search);

export const searchParams = derived(
  search,
  ($search) => new URLSearchParams($search),
);

export const show_charts = derived(
  searchParams,
  ($searchParams) => normalizeCharts($searchParams.get(QUERY_PARAM_NAMES.CHARTS)),
);

export const conversion = derived(
  searchParams,
  ($searchParams) => normalizeConversion($searchParams.get(QUERY_PARAM_NAMES.CONVERSION)),
);

export const interval = derived(searchParams, ($searchParams) =>
  normalizeInterval($searchParams.get(QUERY_PARAM_NAMES.INTERVAL)),
);

export const syncedSearchParams = derived(searchParams, ($searchParams) => {
  const parsed = parseQueryParams($searchParams);
  return serializeQueryParams(parsed, {
    omitDefaults: false,
    includeCharts: true,
    includeQueryString: false,
  });
});

export { SYNCED_QUERY_PARAM_NAMES, QUERY_PARAM_NAMES };
