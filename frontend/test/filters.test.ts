import { deepEqual, equal } from "node:assert/strict";
import { test } from "node:test";

import { get as store_get } from "svelte/store";

import {
  getStaleFilterParams,
  getURLFilters,
} from "../src/stores/filters.ts";
import { current_url } from "../src/stores/url.ts";
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
