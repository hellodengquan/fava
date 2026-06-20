import { deepEqual, equal, ok } from "node:assert/strict";
import { test } from "node:test";

import { get as store_get } from "svelte/store";

import {
  account_filter,
  fql_filter,
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

test("account_filter subscriber pattern simulating component mount/unmount", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA",
    ),
  );

  let account_callback_calls = 0;
  let last_account_value = "";
  const unsubscribe = account_filter.subscribe((v) => {
    account_callback_calls++;
    last_account_value = v;
  });

  equal(account_callback_calls, 1, "First sync call during subscribe");
  equal(last_account_value, "Assets:US:BofA");

  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Expenses:Rent",
    ),
  );
  equal(account_callback_calls, 2, "Callback invoked on URL change");
  equal(last_account_value, "Expenses:Rent");

  unsubscribe();

  const calls_after_unsubscribe = account_callback_calls;
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/balance_sheet/?account=Income:Salary",
    ),
  );
  equal(
    account_callback_calls,
    calls_after_unsubscribe,
    "Unsubscribed listener must not be called after unsubscribe()",
  );
  equal(last_account_value, "Expenses:Rent", "Value must not change after unsubscribe");
});

test("fql_filter subscriber pattern simulating component mount/unmount", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?filter=%23test",
    ),
  );

  let fql_callback_calls = 0;
  let last_fql_value = "";
  const unsubscribe = fql_filter.subscribe((v) => {
    fql_callback_calls++;
    last_fql_value = v;
  });
  equal(fql_callback_calls, 1);
  equal(last_fql_value, "#test");

  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?filter=%23home",
    ),
  );
  equal(fql_callback_calls, 2);
  equal(last_fql_value, "#home");

  unsubscribe();

  const calls_after_unsubscribe = fql_callback_calls;
  const value_after_unsubscribe = last_fql_value;
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/balance_sheet/?filter=%23work",
    ),
  );
  equal(fql_callback_calls, calls_after_unsubscribe);
  equal(last_fql_value, value_after_unsubscribe);
});

test("time_filter subscriber pattern simulating component mount/unmount", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?time=2015",
    ),
  );

  let time_callback_calls = 0;
  let last_time_value = "";
  const unsubscribe = time_filter.subscribe((v) => {
    time_callback_calls++;
    last_time_value = v;
  });
  equal(time_callback_calls, 1);
  equal(last_time_value, "2015");

  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?time=2016",
    ),
  );
  equal(time_callback_calls, 2);
  equal(last_time_value, "2016");

  unsubscribe();

  const calls_after_unsubscribe = time_callback_calls;
  const value_after_unsubscribe = last_time_value;
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/balance_sheet/?time=2014",
    ),
  );
  equal(time_callback_calls, calls_after_unsubscribe);
  equal(last_time_value, value_after_unsubscribe);
});

test("simulated ledger change (full URL reset) triggers listener cleanup", () => {
  current_url.set(
    new URL(
      "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA&time=2015&filter=%23test",
    ),
  );

  let account_cb_count = 0;
  let fql_cb_count = 0;
  let time_cb_count = 0;

  const unsub_account = account_filter.subscribe(() => account_cb_count++);
  const unsub_fql = fql_filter.subscribe(() => fql_cb_count++);
  const unsub_time = time_filter.subscribe(() => time_cb_count++);

  equal(account_cb_count, 1);
  equal(fql_cb_count, 1);
  equal(time_cb_count, 1);

  unsub_account();
  unsub_fql();
  unsub_time();

  current_url.set(
    new URL(
      "http://localhost:5000/example/income_statement/",
    ),
  );

  equal(account_cb_count, 1, "account listener must be silent after unsub");
  equal(fql_cb_count, 1, "fql listener must be silent after unsub");
  equal(time_cb_count, 1, "time listener must be silent after unsub");
});

test("multi-ledger iframe scenario: slug isolation prevents cross-ledger filter pollution", () => {
  const ledgerAURL = new URL(
    "http://localhost:5000/long-example/balance_sheet/?account=Assets:US:BofA&time=2015",
  );
  current_url.set(ledgerAURL);
  const A_account = store_get(account_filter);
  const A_time = store_get(time_filter);
  equal(A_account, "Assets:US:BofA");
  equal(A_time, "2015");

  const ledgerBURL = new URL(
    "http://localhost:5000/example/income_statement/?account=Assets:Account1&time=2012",
  );
  current_url.set(ledgerBURL);
  const B_account = store_get(account_filter);
  const B_time = store_get(time_filter);
  equal(B_account, "Assets:Account1");
  equal(B_time, "2012");

  current_url.set(ledgerAURL);
  const A_back_account = store_get(account_filter);
  const A_back_time = store_get(time_filter);
  equal(A_back_account, "Assets:US:BofA");
  equal(A_back_time, "2015");

  const C_url = new URL(
    "http://localhost:5000/edit-example/journal/",
  );
  current_url.set(C_url);
  equal(store_get(account_filter), "");
  equal(store_get(time_filter), "");
});

test("multi-ledger iframe scenario: each ledger validates filters against its own data", () => {
  const ledgerLongData = {
    accounts: ["Assets:US:BofA", "Assets:US:BofA:Checking", "Expenses:Home:Rent"],
    years: ["2014", "2015", "2016"],
    tags: ["test"],
    links: [],
    payees: [],
  };
  const ledgerExampleData = {
    accounts: ["Assets:Account1", "Income:Salary", "Expenses:Food"],
    years: ["2012", "2013"],
    tags: [],
    links: [],
    payees: [],
  };

  const urlLongExample = new URL(
    "http://localhost:5000/long-example/income_statement/?account=Assets:US:BofA",
  );
  const staleLong = getStaleFilterParams(urlLongExample, ledgerLongData);
  deepEqual(staleLong, []);
  const staleAsExample = getStaleFilterParams(urlLongExample, ledgerExampleData);
  deepEqual(staleAsExample, ["account"]);

  const urlExample = new URL(
    "http://localhost:5000/example/income_statement/?account=Assets:Account1",
  );
  const staleExample = getStaleFilterParams(urlExample, ledgerExampleData);
  deepEqual(staleExample, []);
  const staleAsLong = getStaleFilterParams(urlExample, ledgerLongData);
  deepEqual(staleAsLong, ["account"]);
});

test("stale filter cleanup triggered after extended idle period via URL refresh", () => {
  const initialData = {
    accounts: ["Assets:Active", "Expenses:ToDelete"],
    years: ["2020", "2021"],
    tags: ["old-tag"],
    links: [],
    payees: [],
  };
  const urlWithAll = new URL(
    "http://localhost:5000/ledger/report/?account=Expenses:ToDelete&time=2021&filter=%23old-tag",
  );
  const staleBefore = getStaleFilterParams(urlWithAll, initialData);
  deepEqual(staleBefore, []);

  const dataAfterLongIdle = {
    accounts: ["Assets:Active"],
    years: ["2020", "2021", "2022"],
    tags: ["new-tag"],
    links: [],
    payees: [],
  };
  const staleAfter = getStaleFilterParams(urlWithAll, dataAfterLongIdle);
  deepEqual(staleAfter, ["account", "filter"]);

  const url = new URL(urlWithAll);
  const cleared = new Set<string>();
  for (const param of staleAfter) {
    url.searchParams.delete(param);
    cleared.add(param);
  }
  equal(cleared.has("account"), true);
  equal(cleared.has("filter"), true);
  equal(url.searchParams.get("account"), null);
  equal(url.searchParams.get("filter"), null);
  equal(url.searchParams.get("time"), "2021");
});
