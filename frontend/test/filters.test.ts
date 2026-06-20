import { deepEqual, equal, ok } from "node:assert/strict";
import { test } from "node:test";

import { get as store_get } from "svelte/store";

import {
  account_filter,
  getStaleFilterParams,
  getURLFilters,
  time_filter,
} from "../src/stores/filters.ts";
import { current_url, searchParams, syncedSearchParams } from "../src/stores/url.ts";
import { initialiseLedgerData } from "./helpers.ts";
import { setup_jsdom } from "./dom.ts";

test.before(initialiseLedgerData);
test.beforeEach(setup_jsdom);

const validationData = {
  accounts: ["Assets:US:BofA", "Assets:US:BofA:Checking", "Expenses:Rent"],
  years: ["2014", "2015", "2016"],
  tags: ["test", "home", "work"],
  links: ["test-link", "invoice-123"],
  payees: ["BayBook", "Supermarket", "Coffee Shop"],
};

test("getURLFilters extracts filters from URL correctly", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015&filter=%23test&conversion=USD&interval=Month",
  );
  const filters = getURLFilters(url);
  equal(filters.account, "Assets:US:BofA");
  equal(filters.time, "2015");
  equal(filters.filter, "#test");
  equal(filters.conversion, "USD");
  equal(filters.interval, "Month");
});

test("getURLFilters returns empty strings when no params", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/",
  );
  const filters = getURLFilters(url);
  equal(filters.account, "");
  equal(filters.time, "");
  equal(filters.filter, "");
  equal(filters.conversion, "");
  equal(filters.interval, "");
});

test("getStaleFilterParams returns empty for valid filters", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015&filter=%23test",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, []);
});

test("getStaleFilterParams detects invalid account filter", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=Assets:NonExistent",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, ["account"]);
});

test("getStaleFilterParams detects invalid time filter", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?time=1999",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, ["time"]);
});

test("getStaleFilterParams detects invalid tag in filter", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?filter=%23nonexistent-tag",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, ["filter"]);
});

test("getStaleFilterParams detects invalid link in filter", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?filter=%5Enonexistent-link",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, ["filter"]);
});

test("getStaleFilterParams detects invalid payee in filter", () => {
  const url = new URL(
    'http://localhost:5000/long-example/income_statement/?filter=payee:"Nonexistent"',
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, ["filter"]);
});

test("getStaleFilterParams detects multiple stale params", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=Assets:NonExistent&time=1999&filter=%23nonexistent",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, ["account", "time", "filter"]);
});

test("getStaleFilterParams allows account prefix filter", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, []);
});

test("getStaleFilterParams allows account component filter", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=Checking",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, []);
});

test("getStaleFilterParams allows valid regex in account filter", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=BofA.*",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, []);
});

test("getStaleFilterParams marks invalid regex as stale", () => {
  const url = new URL(
    "http://localhost:5000/long-example/income_statement/?account=[invalid",
  );
  const stale = getStaleFilterParams(url, validationData);
  deepEqual(stale, ["account"]);
});

test("current_url store syncs with URL searchParams", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015",
    ),
  );
  const url = store_get(current_url);
  equal(url.searchParams.get("account"), "Assets:US:BofA");
  equal(url.searchParams.get("time"), "2015");
});

test("filter stores react to current_url page switch within same ledger", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015",
    ),
  );
  equal(store_get(account_filter), "Assets:US:BofA");
  equal(store_get(time_filter), "2015");

  current_url.set(
    new URL(
      "http://localhost:5000/long-example/balance_sheet/?account=Assets:US:BofA&time=2015",
    ),
  );
  equal(store_get(account_filter), "Assets:US:BofA");
  equal(store_get(time_filter), "2015");
});

test("filter stores clear when switching to URL without filter params", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015",
    ),
  );
  equal(store_get(account_filter), "Assets:US:BofA");
  equal(store_get(time_filter), "2015");

  current_url.set(
    new URL(
      "http://localhost:5000/long-example/balance_sheet/",
    ),
  );
  equal(store_get(account_filter), "");
  equal(store_get(time_filter), "");
});

test("filter stores update when switching ledgers with different params", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015",
    ),
  );
  equal(store_get(account_filter), "Assets:US:BofA");
  equal(store_get(time_filter), "2015");

  current_url.set(
    new URL(
      "http://localhost:5000/example/income_statement/?time=2012",
    ),
  );
  equal(store_get(account_filter), "");
  equal(store_get(time_filter), "2012");
});

test("syncedSearchParams only includes non-empty filter params", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA",
    ),
  );
  const params = store_get(syncedSearchParams);
  equal(params.get("account"), "Assets:US:BofA");
  equal(params.get("time"), null);
  equal(params.get("filter"), null);
});

test("syncedSearchParams clears all filters when navigating to clean URL", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015&filter=%23test",
    ),
  );
  let params = store_get(syncedSearchParams);
  equal(params.get("account"), "Assets:US:BofA");
  equal(params.get("time"), "2015");

  current_url.set(
    new URL(
      "http://localhost:5000/long-example/balance_sheet/",
    ),
  );
  params = store_get(syncedSearchParams);
  equal(params.get("account"), null);
  equal(params.get("time"), null);
  equal(params.get("filter"), null);
});

test("searchParams derived store produces fresh instance per URL change", () => {
  current_url.set(
    new URL("http://localhost:5000/long-example/income_statement/?account=A"),
  );
  const sp1 = store_get(searchParams);
  equal(sp1.get("account"), "A");

  current_url.set(
    new URL("http://localhost:5000/long-example/income_statement/?account=B"),
  );
  const sp2 = store_get(searchParams);
  equal(sp2.get("account"), "B");
  equal(sp1.get("account"), "A");
});

test("closed account still in accounts list is valid for filter", () => {
  const closedAccountData = {
    accounts: ["Assets:Account1", "Expenses:Food"],
    years: ["2012", "2013", "2014"],
    tags: [],
    links: [],
    payees: [],
  };
  const url = new URL(
    "http://localhost:5000/example/income_statement/?account=Assets:Account1",
  );
  const stale = getStaleFilterParams(url, closedAccountData);
  deepEqual(stale, []);
});

test("deleted account not in accounts list is stale for filter", () => {
  const dataAfterDelete = {
    accounts: ["Expenses:Food"],
    years: ["2012", "2013", "2014"],
    tags: [],
    links: [],
    payees: [],
  };
  const url = new URL(
    "http://localhost:5000/example/income_statement/?account=Assets:DeletedAccount",
  );
  const stale = getStaleFilterParams(url, dataAfterDelete);
  deepEqual(stale, ["account"]);
});

test("hidden (zero-balance, no-transaction) account still in accounts list is valid", () => {
  const dataWithHidden = {
    accounts: ["Assets:Dormant", "Expenses:Food", "Income:Salary"],
    years: ["2014"],
    tags: [],
    links: [],
    payees: [],
  };
  const url = new URL(
    "http://localhost:5000/example/income_statement/?account=Assets:Dormant",
  );
  const stale = getStaleFilterParams(url, dataWithHidden);
  deepEqual(stale, []);
});

test("getStaleFilterParams returns only stale params without retaining references", () => {
  const data = {
    accounts: ["Assets:Active"],
    years: ["2020"],
    tags: ["active-tag"],
    links: ["active-link"],
    payees: ["ActivePayee"],
  };
  const url = new URL(
    "http://localhost:5000/ledger/report/?account=Assets:Active",
  );

  const results: string[][] = [];
  for (let i = 0; i < 1000; i++) {
    results.push(getStaleFilterParams(url, data));
  }

  for (const result of results) {
    deepEqual(result, []);
  }

  const firstResult = results[0];
  const lastResult = results[results.length - 1];
  ok(firstResult !== lastResult, "Each call should return a new array");
});

test("getStaleFilterParams does not accumulate internal regex state across calls", () => {
  const data = {
    accounts: ["Assets:Active"],
    years: ["2020"],
    tags: ["tag1"],
    links: ["link1"],
    payees: ["Payee1"],
  };

  const staleUrl = new URL(
    "http://localhost:5000/ledger/report/?filter=%23nonexistent",
  );
  getStaleFilterParams(staleUrl, data);

  const validUrl = new URL(
    "http://localhost:5000/ledger/report/?filter=%23tag1",
  );
  const stale = getStaleFilterParams(validUrl, data);
  deepEqual(stale, []);

  getStaleFilterParams(staleUrl, data);

  const stale2 = getStaleFilterParams(validUrl, data);
  deepEqual(stale2, []);
});

test("getStaleFilterParams handles concurrent validation objects without cross-contamination", () => {
  const dataA = {
    accounts: ["Assets:A"],
    years: ["2020"],
    tags: ["tagA"],
    links: ["linkA"],
    payees: ["PayeeA"],
  };
  const dataB = {
    accounts: ["Assets:B"],
    years: ["2021"],
    tags: ["tagB"],
    links: ["linkB"],
    payees: ["PayeeB"],
  };

  const urlA = new URL(
    "http://localhost:5000/ledger-a/report/?account=Assets:A&filter=%23tagA",
  );
  const urlB = new URL(
    "http://localhost:5000/ledger-b/report/?account=Assets:A&filter=%23tagA",
  );

  const staleA = getStaleFilterParams(urlA, dataA);
  deepEqual(staleA, []);

  const staleB = getStaleFilterParams(urlB, dataB);
  deepEqual(staleB, ["account", "filter"]);

  const staleA2 = getStaleFilterParams(urlA, dataA);
  deepEqual(staleA2, []);
});
