import { deepEqual, equal, ok } from "node:assert/strict";
import { test } from "node:test";

import {
  getReportFilterContext,
  reportFilterContextFromDict,
  reportFilterContextToUrlParams,
  reportFilterContextEqual,
  type ReportFilterContext,
} from "../src/stores/filters.ts";
import { setup_jsdom } from "./dom.ts";

test.beforeEach(setup_jsdom);

test("getReportFilterContext extracts all params from URL", () => {
  const url = new URL(
    "http://localhost/income_statement/?time=2024&account=Assets&filter=%23trip&conversion=EUR&interval=year",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.time, "2024");
  equal(ctx.account, "Assets");
  equal(ctx.filter, "#trip");
  equal(ctx.conversion, "EUR");
  equal(ctx.interval, "year");
});

test("getReportFilterContext uses defaults for missing params", () => {
  const url = new URL("http://localhost/income_statement/");
  const ctx = getReportFilterContext(url);
  equal(ctx.time, "");
  equal(ctx.account, "");
  equal(ctx.filter, "");
  equal(ctx.conversion, "at_cost");
  equal(ctx.interval, "month");
});

test("getReportFilterContext normalizes interval to lowercase", () => {
  const url = new URL(
    "http://localhost/income_statement/?interval=YEAR",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.interval, "year");
});

test("getReportFilterContext handles empty conversion as default", () => {
  const url = new URL(
    "http://localhost/income_statement/?conversion=",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.conversion, "at_cost");
});

test("getReportFilterContext handles empty interval as default", () => {
  const url = new URL(
    "http://localhost/income_statement/?interval=",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.interval, "month");
});

test("getReportFilterContext preserves tag filter with hash", () => {
  const url = new URL(
    "http://localhost/income_statement/?filter=%23trip",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.filter, "#trip");
});

test("reportFilterContextFromDict with all params", () => {
  const ctx = reportFilterContextFromDict({
    time: "2024-Q1",
    account: "Assets:US",
    filter: "#work",
    conversion: "USD",
    interval: "quarter",
  });
  equal(ctx.time, "2024-Q1");
  equal(ctx.account, "Assets:US");
  equal(ctx.filter, "#work");
  equal(ctx.conversion, "USD");
  equal(ctx.interval, "quarter");
});

test("reportFilterContextFromDict with empty dict uses defaults", () => {
  const ctx = reportFilterContextFromDict({});
  equal(ctx.time, "");
  equal(ctx.account, "");
  equal(ctx.filter, "");
  equal(ctx.conversion, "at_cost");
  equal(ctx.interval, "month");
});

test("reportFilterContextFromDict with partial params", () => {
  const ctx = reportFilterContextFromDict({ time: "2024" });
  equal(ctx.time, "2024");
  equal(ctx.account, "");
  equal(ctx.filter, "");
  equal(ctx.conversion, "at_cost");
  equal(ctx.interval, "month");
});

test("reportFilterContextFromDict normalizes interval to lowercase", () => {
  const ctx = reportFilterContextFromDict({ interval: "WEEK" });
  equal(ctx.interval, "week");
});

test("reportFilterContextFromDict handles empty conversion", () => {
  const ctx = reportFilterContextFromDict({ conversion: "" });
  equal(ctx.conversion, "at_cost");
});

test("reportFilterContextFromDict handles empty interval", () => {
  const ctx = reportFilterContextFromDict({ interval: "" });
  equal(ctx.interval, "month");
});

test("reportFilterContextToUrlParams includes non-default values", () => {
  const ctx: ReportFilterContext = {
    time: "2024",
    account: "Assets",
    filter: "#trip",
    conversion: "EUR",
    interval: "year",
  };
  const params = reportFilterContextToUrlParams(ctx);
  equal(params.time, "2024");
  equal(params.account, "Assets");
  equal(params.filter, "#trip");
  equal(params.conversion, "EUR");
  equal(params.interval, "year");
});

test("reportFilterContextToUrlParams excludes default conversion", () => {
  const ctx: ReportFilterContext = {
    time: "2024",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  const params = reportFilterContextToUrlParams(ctx);
  ok(!("conversion" in params));
});

test("reportFilterContextToUrlParams excludes default interval", () => {
  const ctx: ReportFilterContext = {
    time: "",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  const params = reportFilterContextToUrlParams(ctx);
  ok(!("interval" in params));
});

test("reportFilterContextToUrlParams excludes empty strings", () => {
  const ctx: ReportFilterContext = {
    time: "",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  const params = reportFilterContextToUrlParams(ctx);
  deepEqual(params, {});
});

test("reportFilterContextToUrlParams includes non-empty time", () => {
  const ctx: ReportFilterContext = {
    time: "2024",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  const params = reportFilterContextToUrlParams(ctx);
  equal(params.time, "2024");
  ok(!("account" in params));
});

test("reportFilterContextEqual returns true for identical contexts", () => {
  const a: ReportFilterContext = {
    time: "2024",
    account: "Assets",
    filter: "#trip",
    conversion: "EUR",
    interval: "year",
  };
  const b: ReportFilterContext = {
    time: "2024",
    account: "Assets",
    filter: "#trip",
    conversion: "EUR",
    interval: "year",
  };
  ok(reportFilterContextEqual(a, b));
});

test("reportFilterContextEqual returns false for different time", () => {
  const a: ReportFilterContext = {
    time: "2024",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  const b: ReportFilterContext = {
    time: "2025",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  ok(!reportFilterContextEqual(a, b));
});

test("reportFilterContextEqual returns false for different account", () => {
  const a: ReportFilterContext = {
    time: "",
    account: "Assets",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  const b: ReportFilterContext = {
    time: "",
    account: "Liabilities",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  ok(!reportFilterContextEqual(a, b));
});

test("reportFilterContextEqual returns false for different filter", () => {
  const a: ReportFilterContext = {
    time: "",
    account: "",
    filter: "#trip",
    conversion: "at_cost",
    interval: "month",
  };
  const b: ReportFilterContext = {
    time: "",
    account: "",
    filter: "#work",
    conversion: "at_cost",
    interval: "month",
  };
  ok(!reportFilterContextEqual(a, b));
});

test("reportFilterContextEqual returns false for different conversion", () => {
  const a: ReportFilterContext = {
    time: "",
    account: "",
    filter: "",
    conversion: "USD",
    interval: "month",
  };
  const b: ReportFilterContext = {
    time: "",
    account: "",
    filter: "",
    conversion: "EUR",
    interval: "month",
  };
  ok(!reportFilterContextEqual(a, b));
});

test("reportFilterContextEqual returns false for different interval", () => {
  const a: ReportFilterContext = {
    time: "",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "year",
  };
  const b: ReportFilterContext = {
    time: "",
    account: "",
    filter: "",
    conversion: "at_cost",
    interval: "month",
  };
  ok(!reportFilterContextEqual(a, b));
});

test("roundtrip: from URL -> to URL params", () => {
  const url = new URL(
    "http://localhost/income_statement/?time=2024&account=Assets&conversion=EUR&interval=year",
  );
  const ctx = getReportFilterContext(url);
  const params = reportFilterContextToUrlParams(ctx);
  equal(params.time, "2024");
  equal(params.account, "Assets");
  equal(params.conversion, "EUR");
  equal(params.interval, "year");
});

test("roundtrip: from dict -> to URL params -> back", () => {
  const original = reportFilterContextFromDict({
    time: "2024-Q1",
    account: "Expenses",
    filter: "-#nomatch",
    conversion: "units",
    interval: "week",
  });
  const params = reportFilterContextToUrlParams(original);
  const restored = reportFilterContextFromDict(params);
  ok(reportFilterContextEqual(original, restored));
});

test("negated tag filter preserved through context", () => {
  const url = new URL(
    "http://localhost/income_statement/?filter=-%23nomatch",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.filter, "-#nomatch");
  const params = reportFilterContextToUrlParams(ctx);
  equal(params.filter, "-#nomatch");
});

test("combined tag filter preserved through context", () => {
  const url = new URL(
    "http://localhost/income_statement/?filter=%23trip%2C%23work",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.filter, "#trip,#work");
});

test("link filter preserved through context", () => {
  const url = new URL(
    "http://localhost/income_statement/?filter=%5Etrip-link",
  );
  const ctx = getReportFilterContext(url);
  equal(ctx.filter, "^trip-link");
});
