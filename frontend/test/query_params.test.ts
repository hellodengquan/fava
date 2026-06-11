import { equal, deepEqual, ok } from "node:assert/strict";
import { test } from "node:test";

import {
  QUERY_PARAM_NAMES,
  DEFAULT_QUERY_PARAMS,
  DEFAULT_CONVERSION,
  SYNCED_QUERY_PARAM_NAMES,
  QUERY_PARAM_SCHEMA,
  type QueryParams,
  type Filters,
  type FiltersConversionInterval,
  type QueryParamName,
  parseQueryParams,
  serializeQueryParams,
  normalizeTime,
  normalizeAccount,
  normalizeFilter,
  normalizeConversion,
  normalizeInterval,
  normalizeCharts,
  normalizeQueryString,
  setQueryParamOnURL,
  getFilters,
  getFiltersConversionInterval,
  getFiltersFromURL,
  getFiltersConversionIntervalFromURL,
} from "../src/lib/query_params.ts";

export const ROUNDTRIP_TEST_CASES: Array<{
  name: string;
  input: Record<string, string>;
  expected: Record<string, unknown>;
}> = [
  {
    name: "defaults (empty params)",
    input: {},
    expected: {
      time: "",
      account: "",
      filter: "",
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "all params set (English)",
    input: {
      time: "2024",
      account: "Assets:Cash",
      filter: "#tag",
      conversion: "USD",
      interval: "year",
      charts: "false",
      query_string: "SELECT *",
    },
    expected: {
      time: "2024",
      account: "Assets:Cash",
      filter: "#tag",
      conversion: "USD",
      interval: "year",
      charts: false,
      query_string: "SELECT *",
    },
  },
  {
    name: "Chinese account name",
    input: {
      account: "资产:现金",
      filter: 'payee:"张三"',
    },
    expected: {
      time: "",
      account: "资产:现金",
      filter: 'payee:"张三"',
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "Japanese and Korean account names",
    input: {
      account: "費用:食費",
      filter: "#한글태그",
    },
    expected: {
      time: "",
      account: "費用:食費",
      filter: "#한글태그",
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "special characters in params",
    input: {
      account: "Assets:Cash & Equivalents",
      filter: 'payee:"A & B"',
      query_string: "SELECT name WHERE account ~ '.*&.*'",
    },
    expected: {
      time: "",
      account: "Assets:Cash & Equivalents",
      filter: 'payee:"A & B"',
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "SELECT name WHERE account ~ '.*&.*'",
    },
  },
  {
    name: "percent sign in account (should be literal)",
    input: {
      account: "Assets:100%Equity",
    },
    expected: {
      time: "",
      account: "Assets:100%Equity",
      filter: "",
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "whitespace trimming",
    input: {
      time: "  2024  ",
      account: "  Assets:Cash  ",
      filter: "  #tag  ",
      conversion: "  USD  ",
      interval: "  year  ",
    },
    expected: {
      time: "2024",
      account: "Assets:Cash",
      filter: "#tag",
      conversion: "USD",
      interval: "year",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "empty strings fall back to defaults",
    input: {
      time: "",
      account: "",
      filter: "",
      conversion: "",
      interval: "",
      charts: "",
      query_string: "",
    },
    expected: {
      time: "",
      account: "",
      filter: "",
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "invalid interval falls back to month",
    input: {
      interval: "foo",
    },
    expected: {
      time: "",
      account: "",
      filter: "",
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "mixed case interval normalized to lower",
    input: {
      interval: "YEAR",
    },
    expected: {
      time: "",
      account: "",
      filter: "",
      conversion: "at_cost",
      interval: "year",
      charts: true,
      query_string: "",
    },
  },
  {
    name: "emoji characters preserved",
    input: {
      account: "🎉:Expenses:💰",
      filter: "#标签🎉",
    },
    expected: {
      time: "",
      account: "🎉:Expenses:💰",
      filter: "#标签🎉",
      conversion: "at_cost",
      interval: "month",
      charts: true,
      query_string: "",
    },
  },
];

test("query param names are consistent with schema", () => {
  const paramNames = Object.values(QUERY_PARAM_NAMES).sort();
  const schemaKeys = Object.keys(QUERY_PARAM_SCHEMA).sort();
  deepEqual(paramNames, schemaKeys);
});

test("synced params match schema", () => {
  const syncedFromSchema = Object.entries(QUERY_PARAM_SCHEMA)
    .filter(([, v]) => v.synced)
    .map(([k]) => k)
    .sort();
  const syncedFromModule = [...SYNCED_QUERY_PARAM_NAMES].sort();
  deepEqual(syncedFromModule, syncedFromSchema);
});

test("schema defaults match DEFAULT_QUERY_PARAMS", () => {
  for (const [key, schema] of Object.entries(QUERY_PARAM_SCHEMA)) {
    equal(
      DEFAULT_QUERY_PARAMS[key as keyof typeof DEFAULT_QUERY_PARAMS],
      schema.default,
      `default mismatch for ${key}`,
    );
  }
});

test("schema normalizeFn produce same results as standalone functions", () => {
  const testInputs: Record<string, string | null> = {
    time: "  2024  ",
    account: "  资产:现金  ",
    filter: "  #tag  ",
    conversion: "  USD  ",
    interval: "YEAR",
    charts: "false",
    query_string: "SELECT *",
  };

  const standalone = {
    time: normalizeTime(testInputs.time),
    account: normalizeAccount(testInputs.account),
    filter: normalizeFilter(testInputs.filter),
    conversion: normalizeConversion(testInputs.conversion),
    interval: normalizeInterval(testInputs.interval),
    charts: normalizeCharts(testInputs.charts),
    query_string: normalizeQueryString(testInputs.query_string),
  };

  for (const [key, schema] of Object.entries(QUERY_PARAM_SCHEMA)) {
    const fromSchema = schema.normalizeFn(testInputs[key]);
    const fromStandalone = standalone[key as keyof typeof standalone];
    equal(
      fromSchema,
      fromStandalone,
      `normalizeFn mismatch for ${key}`,
    );
  }
});

test("normalizeTime handles various inputs", () => {
  equal(normalizeTime(null), "");
  equal(normalizeTime(undefined), "");
  equal(normalizeTime(""), "");
  equal(normalizeTime("  "), "");
  equal(normalizeTime("2024"), "2024");
  equal(normalizeTime("  2024-01  "), "2024-01");
  equal(normalizeTime("year-2 - year"), "year-2 - year");
});

test("normalizeAccount handles Chinese and special characters", () => {
  equal(normalizeAccount(null), "");
  equal(normalizeAccount(""), "");
  equal(normalizeAccount("Assets:Cash"), "Assets:Cash");
  equal(normalizeAccount("  资产:现金  "), "资产:现金");
  equal(normalizeAccount("Expenses:餐饮-午餐"), "Expenses:餐饮-午餐");
  equal(normalizeAccount("账户名 with spaces"), "账户名 with spaces");
  equal(normalizeAccount("特殊字符:!@#$%^&*()"), "特殊字符:!@#$%^&*()");
  equal(normalizeAccount("日本語:勘定科目"), "日本語:勘定科目");
  equal(normalizeAccount("한국어:계정"), "한국어:계정");
  equal(normalizeAccount("Emoji:🎉💰"), "Emoji:🎉💰");
});

test("normalizeFilter handles various inputs", () => {
  equal(normalizeFilter(null), "");
  equal(normalizeFilter(""), "");
  equal(normalizeFilter("  #tag  "), "#tag");
  equal(normalizeFilter('payee:"中文收款人"'), 'payee:"中文收款人"');
});

test("normalizeConversion falls back to default", () => {
  equal(normalizeConversion(null), DEFAULT_CONVERSION);
  equal(normalizeConversion(""), DEFAULT_CONVERSION);
  equal(normalizeConversion("  "), DEFAULT_CONVERSION);
  equal(normalizeConversion("USD"), "USD");
  equal(normalizeConversion("  at_value  "), "at_value");
});

test("normalizeInterval falls back to default with warning", () => {
  equal(normalizeInterval(null), "month");
  equal(normalizeInterval(""), "month");
  equal(normalizeInterval("year"), "year");
  equal(normalizeInterval("month"), "month");
  equal(normalizeInterval("day"), "day");
  equal(normalizeInterval("foo"), "month");
  equal(normalizeInterval("invalid_value"), "month");
});

test("normalizeCharts boolean semantics", () => {
  equal(normalizeCharts(null), true);
  equal(normalizeCharts(""), true);
  equal(normalizeCharts("true"), true);
  equal(normalizeCharts("false"), false);
  equal(normalizeCharts("anything"), true);
});

test("normalizeQueryString passthrough", () => {
  equal(normalizeQueryString(null), "");
  equal(normalizeQueryString(""), "");
  equal(normalizeQueryString("SELECT *"), "SELECT *");
  equal(normalizeQueryString("中文查询"), "中文查询");
});

test("parseQueryParams from URLSearchParams", () => {
  const params = new URLSearchParams({
    time: "2024",
    account: "Assets:Cash",
    filter: "#tag",
    conversion: "USD",
    interval: "year",
    charts: "false",
    query_string: "SELECT",
  });
  const parsed = parseQueryParams(params);
  equal(parsed.time, "2024");
  equal(parsed.account, "Assets:Cash");
  equal(parsed.filter, "#tag");
  equal(parsed.conversion, "USD");
  equal(parsed.interval, "year");
  equal(parsed.charts, false);
  equal(parsed.query_string, "SELECT");
});

test("parseQueryParams from record object", () => {
  const parsed = parseQueryParams({
    time: "2024",
    account: "资产:现金",
    filter: null,
    conversion: undefined,
  });
  equal(parsed.time, "2024");
  equal(parsed.account, "资产:现金");
  equal(parsed.filter, "");
  equal(parsed.conversion, "at_cost");
  equal(parsed.interval, "month");
  equal(parsed.charts, true);
  equal(parsed.query_string, "");
});

test("parseQueryParams defaults match schema", () => {
  const parsed = parseQueryParams({});
  equal(parsed.time, QUERY_PARAM_SCHEMA.time.default as string);
  equal(parsed.account, QUERY_PARAM_SCHEMA.account.default as string);
  equal(parsed.filter, QUERY_PARAM_SCHEMA.filter.default as string);
  equal(parsed.conversion, QUERY_PARAM_SCHEMA.conversion.default as string);
  equal(parsed.interval, QUERY_PARAM_SCHEMA.interval.default as string);
  equal(parsed.charts, QUERY_PARAM_SCHEMA.charts.default as boolean);
  equal(parsed.query_string, QUERY_PARAM_SCHEMA.query_string.default as string);
  deepEqual(parsed, DEFAULT_QUERY_PARAMS);
});

test("parseQueryParams with URL-encoded Chinese account", () => {
  const url = new URL("http://localhost/?account=%E8%B5%84%E4%BA%A7:%E7%8E%B0%E9%87%91");
  const parsed = parseQueryParams(url.searchParams);
  equal(parsed.account, "资产:现金");
});

test("serializeQueryParams round-trip", () => {
  const original: QueryParams = {
    time: "2024",
    account: "资产:现金",
    filter: "#tag",
    conversion: "USD",
    interval: "year",
    charts: false,
    query_string: "SELECT * FROM accounts",
  };

  const serialized = serializeQueryParams(original, {
    includeCharts: true,
    includeQueryString: true,
  });

  const reparsed = parseQueryParams(serialized);
  equal(reparsed.time, original.time);
  equal(reparsed.account, original.account);
  equal(reparsed.filter, original.filter);
  equal(reparsed.conversion, original.conversion);
  equal(reparsed.interval, original.interval);
  equal(reparsed.charts, original.charts);
  equal(reparsed.query_string, original.query_string);
});

test("serializeQueryParams with Chinese and special characters round-trip", () => {
  const testCases = [
    { account: "资产:现金", desc: "Chinese account" },
    { account: "Expenses:餐饮娱乐", desc: "Chinese with colon" },
    { account: "日本語:費用", desc: "Japanese" },
    { account: "한국어:지출", desc: "Korean" },
    { account: "Account:with spaces", desc: "spaces" },
    { account: "Special:!@#$%^&*()_+-=", desc: "special chars" },
    { filter: 'payee:"中文 收 款人"', desc: "Chinese in filter" },
    { query_string: "SELECT 中文 FROM 表", desc: "Chinese query string" },
  ];

  for (const tc of testCases) {
    const original = { ...DEFAULT_QUERY_PARAMS, ...tc };
    const serialized = serializeQueryParams(original, {
      includeCharts: true,
      includeQueryString: true,
    });
    const reparsed = parseQueryParams(serialized);

    equal(
      reparsed.account,
      original.account,
      `round-trip failed for ${tc.desc}: account`,
    );
    equal(
      reparsed.filter,
      original.filter,
      `round-trip failed for ${tc.desc}: filter`,
    );
    equal(
      reparsed.query_string,
      original.query_string,
      `round-trip failed for ${tc.desc}: query_string`,
    );
  }
});

test("setQueryParamOnURL mutates URL correctly", () => {
  const url = new URL("http://localhost/");

  setQueryParamOnURL(url, "time", "2024");
  equal(url.searchParams.get("time"), "2024");

  setQueryParamOnURL(url, "account", "资产:现金");
  equal(url.searchParams.get("account"), "资产:现金");

  setQueryParamOnURL(url, "time", "");
  equal(url.searchParams.get("time"), null);

  setQueryParamOnURL(url, "interval", "year");
  equal(url.searchParams.get("interval"), "year");

  setQueryParamOnURL(url, "interval", "month");
  equal(url.searchParams.get("interval"), null);

  setQueryParamOnURL(url, "conversion", "at_cost");
  equal(url.searchParams.get("conversion"), null);

  setQueryParamOnURL(url, "conversion", "USD");
  equal(url.searchParams.get("conversion"), "USD");

  setQueryParamOnURL(url, "charts", false);
  equal(url.searchParams.get("charts"), "false");

  setQueryParamOnURL(url, "charts", true);
  equal(url.searchParams.get("charts"), null);
});

test("getFilters and getFiltersConversionInterval extract subsets", () => {
  const params: QueryParams = {
    time: "2024",
    account: "Assets:Cash",
    filter: "#tag",
    conversion: "USD",
    interval: "year",
    charts: false,
    query_string: "SELECT",
  };

  const filters = getFilters(params);
  equal(filters.time, "2024");
  equal(filters.account, "Assets:Cash");
  equal(filters.filter, "#tag");

  const fci = getFiltersConversionInterval(params);
  equal(fci.time, "2024");
  equal(fci.account, "Assets:Cash");
  equal(fci.filter, "#tag");
  equal(fci.conversion, "USD");
  equal(fci.interval, "year");
});

test("getFiltersFromURL and getFiltersConversionIntervalFromURL", () => {
  const url = new URL(
    "http://localhost/?time=2024&account=%E8%B5%84%E4%BA%A7:%E7%8E%B0%E9%87%91&filter=%23tag&conversion=USD&interval=year",
  );

  const filters = getFiltersFromURL(url);
  equal(filters.time, "2024");
  equal(filters.account, "资产:现金");
  equal(filters.filter, "#tag");

  const fci = getFiltersConversionIntervalFromURL(url);
  equal(fci.conversion, "USD");
  equal(fci.interval, "year");
});

test("URL encode/decode round-trip with Chinese account name via URL object", () => {
  const accountName = "资产:现金-主账户";
  const url = new URL("http://localhost/");
  setQueryParamOnURL(url, "account", accountName);

  const encodedHref = url.href;
  ok(
    encodedHref.includes("%") || url.searchParams.get("account") === accountName,
    "URL should handle encoding properly",
  );

  const reparsed = parseQueryParams(url.searchParams);
  equal(reparsed.account, accountName);

  const urlFromString = new URL(encodedHref);
  equal(urlFromString.searchParams.get("account"), accountName);
});

test("empty values preserve defaults", () => {
  const params = parseQueryParams({
    time: "",
    account: "",
    filter: "",
    conversion: "",
    interval: "",
    charts: "",
    query_string: "",
  });
  equal(params.conversion, DEFAULT_CONVERSION);
  equal(params.interval, "month");
  equal(params.charts, true);
  equal(params.time, "");
  equal(params.account, "");
  equal(params.filter, "");
  equal(params.query_string, "");
});

test("round-trip test cases all pass", () => {
  for (const tc of ROUNDTRIP_TEST_CASES) {
    const parsed = parseQueryParams(tc.input);

    equal(
      parsed.time,
      tc.expected.time,
      `[${tc.name}] time mismatch`,
    );
    equal(
      parsed.account,
      tc.expected.account,
      `[${tc.name}] account mismatch`,
    );
    equal(
      parsed.filter,
      tc.expected.filter,
      `[${tc.name}] filter mismatch`,
    );
    equal(
      parsed.conversion,
      tc.expected.conversion,
      `[${tc.name}] conversion mismatch`,
    );
    equal(
      parsed.interval,
      tc.expected.interval,
      `[${tc.name}] interval mismatch`,
    );
    equal(
      parsed.charts,
      tc.expected.charts as boolean,
      `[${tc.name}] charts mismatch`,
    );
    equal(
      parsed.query_string,
      tc.expected.query_string,
      `[${tc.name}] query_string mismatch`,
    );

    const serialized = serializeQueryParams(parsed, {
      includeCharts: true,
      includeQueryString: true,
    });
    const reparsed = parseQueryParams(serialized);

    equal(
      reparsed.time,
      parsed.time,
      `[${tc.name}] time round-trip mismatch`,
    );
    equal(
      reparsed.account,
      parsed.account,
      `[${tc.name}] account round-trip mismatch`,
    );
    equal(
      reparsed.filter,
      parsed.filter,
      `[${tc.name}] filter round-trip mismatch`,
    );
    equal(
      reparsed.conversion,
      parsed.conversion,
      `[${tc.name}] conversion round-trip mismatch`,
    );
    equal(
      reparsed.interval,
      parsed.interval,
      `[${tc.name}] interval round-trip mismatch`,
    );
    equal(
      reparsed.charts,
      parsed.charts,
      `[${tc.name}] charts round-trip mismatch`,
    );
    equal(
      reparsed.query_string,
      parsed.query_string,
      `[${tc.name}] query_string round-trip mismatch`,
    );
  }
});

test("percent sign in account name round-trip through URL string", () => {
  const original = "Assets:100%Equity";
  const url = new URL("http://localhost/");
  setQueryParamOnURL(url, "account", original);

  const urlString = url.toString();
  const reparsedUrl = new URL(urlString);
  const reparsed = parseQueryParams(reparsedUrl.searchParams);

  equal(
    reparsed.account,
    original,
    "percent sign should survive URL round-trip",
  );
});

test("plus sign in filter round-trip (should be literal, not space)", () => {
  const original = "#tag+other";
  const url = new URL("http://localhost/");
  setQueryParamOnURL(url, "filter", original);

  const reparsed = parseQueryParams(url.searchParams);
  equal(
    reparsed.filter,
    original,
    "plus sign should survive URL round-trip",
  );
});
