import { derived } from "svelte/store";

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

/** The current filters, can be used as URL parameters. */
export const filter_params = derived(
  [time_filter, account_filter, fql_filter],
  ([$time_filter, $account_filter, $fql_filter]): Filters => ({
    time: $time_filter,
    account: $account_filter,
    filter: $fql_filter,
  }),
);

export function getURLFilters(url: URL): FiltersConversionInterval {
  return {
    account: url.searchParams.get("account") ?? "",
    filter: url.searchParams.get("filter") ?? "",
    time: url.searchParams.get("time") ?? "",
    conversion: url.searchParams.get("conversion") ?? "",
    interval: url.searchParams.get("interval") ?? "",
  };
}

function isAccountFilterValid(
  value: string,
  accounts: readonly string[],
): boolean {
  if (!value) return true;
  if (accounts.includes(value)) return true;
  const prefix = `${value}:`;
  for (const account of accounts) {
    if (account.startsWith(prefix)) return true;
    if (account.split(":").includes(value)) return true;
  }
  try {
    const regex = new RegExp(value, "i");
    for (const account of accounts) {
      if (regex.test(account)) return true;
    }
  } catch {
    return false;
  }
  return false;
}

function isTimeFilterValid(value: string, years: readonly string[]): boolean {
  if (!value) return true;
  for (const year of years) {
    if (value.startsWith(year)) return true;
  }
  return false;
}

function isFqlFilterValid(
  value: string,
  tags: readonly string[],
  links: readonly string[],
  payees: readonly string[],
): boolean {
  if (!value) return true;
  const tagMatch = /#(\S+)/g;
  const linkMatch = /\^(\S+)/g;
  const payeeMatch = /payee:"([^"]+)"/g;
  let match: RegExpExecArray | null;
  match = tagMatch.exec(value);
  while (match !== null) {
    if (match[1] != null && !tags.includes(match[1])) return false;
    match = tagMatch.exec(value);
  }
  match = linkMatch.exec(value);
  while (match !== null) {
    if (match[1] != null && !links.includes(match[1])) return false;
    match = linkMatch.exec(value);
  }
  match = payeeMatch.exec(value);
  while (match !== null) {
    if (match[1] != null && !payees.includes(match[1])) return false;
    match = payeeMatch.exec(value);
  }
  return true;
}

export interface LedgerDataForValidation {
  accounts: readonly string[];
  years: readonly string[];
  tags: readonly string[];
  links: readonly string[];
  payees: readonly string[];
}

export function getStaleFilterParams(
  url: URL,
  data: LedgerDataForValidation,
): string[] {
  const stale: string[] = [];
  const account = url.searchParams.get("account") ?? "";
  if (!isAccountFilterValid(account, data.accounts)) {
    stale.push("account");
  }
  const time = url.searchParams.get("time") ?? "";
  if (!isTimeFilterValid(time, data.years)) {
    stale.push("time");
  }
  const filter = url.searchParams.get("filter") ?? "";
  if (!isFqlFilterValid(filter, data.tags, data.links, data.payees)) {
    stale.push("filter");
  }
  return stale;
}
