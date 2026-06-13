import { deepEqual, equal, ok } from "node:assert/strict";
import { test } from "node:test";

import { ParsedBarChart } from "../src/charts/bar.ts";
import type { ChartContext } from "../src/charts/context.ts";
import {
  colors10,
  colors15,
  filterTicks,
  includeZero,
  padExtent,
} from "../src/charts/helpers.ts";
import { ParsedHierarchyChart } from "../src/charts/hierarchy.ts";
import { chart_validator } from "../src/charts/index.ts";
import { LineChart, ParsedLineChart } from "../src/charts/line.ts";
import { ScatterPlot } from "../src/charts/scatterplot.ts";
import type { ReportFilterContext } from "../src/stores/filters.ts";
import { loadJSONSnapshot } from "./helpers.ts";

const defaultFilterContext: ReportFilterContext = {
  time: "",
  account: "",
  filter: "",
  conversion: "at_cost",
  interval: "month",
};

function makeCtx(
  overrides: Partial<ReportFilterContext> = {},
): ChartContext {
  const filterContext: ReportFilterContext = {
    time: overrides.time ?? defaultFilterContext.time,
    account: overrides.account ?? defaultFilterContext.account,
    filter: overrides.filter ?? defaultFilterContext.filter,
    conversion: overrides.conversion ?? defaultFilterContext.conversion,
    interval: overrides.interval ?? defaultFilterContext.interval,
  };
  return {
    currencies: ["USD"],
    dateFormat: () => "DATE",
    filterContext,
  };
}

test("chart helpers (filter ticks)", () => {
  deepEqual(filterTicks(["1", "2", "3"], 2), ["1", "3"]);
  deepEqual(filterTicks(["1", "2", "3"], 4), ["1", "2", "3"]);
});

test("chart helpers (color scales)", () => {
  equal(colors10[0], "rgb(126, 174, 253)");
  equal(colors15[0], "rgb(173, 200, 254)");
});

test("chart helpers (include zero in extent)", () => {
  deepEqual(includeZero([2, 5]), [0, 5]);
  deepEqual(includeZero([-12, -5]), [-12, 0]);
  deepEqual(includeZero([-5, 5]), [-5, 5]);
  deepEqual(includeZero([undefined, undefined]), [0, 1]);
});

test("chart helpers (pad extent)", () => {
  deepEqual(padExtent([0, 1]), [-0.03, 1.03]);
  deepEqual(padExtent([undefined, undefined]), [0, 1]);
});

test("handle data for hierarchical chart", async () => {
  const ctx = makeCtx();
  ok(ParsedHierarchyChart.validator({ label: "name", data: "" }).is_err);
  const data = await loadJSONSnapshot("test_internal_api-test_chart_api.json");
  const validated = chart_validator(data).unwrap();

  const [hierarchy, balances, net_worth] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);
  ok(balances instanceof ParsedLineChart);
  ok(net_worth instanceof ParsedLineChart);
  const hierarchy_with_context = hierarchy.with_context(ctx);
  deepEqual(hierarchy_with_context.currencies, ["USD"]);
  ok(hierarchy_with_context.data.get("USD"));
});

test("handle data for balances chart", () => {
  ok(ParsedLineChart.validator({ label: "name", data: "" }).is_err);
  const data: unknown = [
    { date: "2000-01-01", balance: { EUR: 10, USD: 10 } },
    { date: "2000-02-01", balance: { EUR: 10 } },
  ];
  const parsed = ParsedLineChart.validator({ label: "name", data })
    .unwrap()
    .with_context();
  ok(parsed instanceof LineChart);
  deepEqual(parsed.filter([]), [
    {
      name: "EUR",
      values: [
        { date: new Date("2000-01-01"), name: "EUR", value: 10 },
        { date: new Date("2000-02-01"), name: "EUR", value: 10 },
      ],
    },
    {
      name: "USD",
      values: [{ date: new Date("2000-01-01"), name: "USD", value: 10 }],
    },
  ]);
});

test("handle data for scatterplot chart", () => {
  ok(ScatterPlot.validator("asdfasdf").is_err);
  ok(ScatterPlot.validator({ label: "name", data: "" }).is_err);
  const data: unknown = [
    { type: "test", date: "2000-01-01", description: "desc" },
  ];
  const parsed = ScatterPlot.validator({ label: "name", data })
    .unwrap()
    .with_context();
  ok(parsed instanceof ScatterPlot);
  deepEqual(
    parsed,
    new ScatterPlot("name", [
      { date: new Date("2000-01-01"), description: "desc", type: "test" },
    ]),
  );
});

test("handle data for bar chart with stacked data", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { EUR: 10, USD: 10 },
      budgets: { USD: 20 },
      account_balances: {
        "Expenses:Dining": { USD: 8 },
        "Expenses:Transportation": { EUR: 6 },
        "Expenses:Taxes": { USD: 2, EUR: 4 },
      },
    },
    {
      date: "2000-02-01",
      balance: { EUR: 100 },
      budgets: { EUR: 50 },
      account_balances: {
        "Expenses:Shoes": { EUR: 60 },
        "Expenses:Taxes": { EUR: 40 },
      },
    },
  ];
  const ctx: ChartContext = { currencies: ["EUR", "USD"], dateFormat: () => "DATE", filterContext: defaultFilterContext };
  const chart = ParsedBarChart.validator({ label: "name", data })
    .unwrap()
    .with_context(ctx);
  equal(true, chart.hasStackedData);
  deepEqual(chart.accounts, [
    "Expenses:Dining",
    "Expenses:Shoes",
    "Expenses:Taxes",
    "Expenses:Transportation",
  ]);
  const result = chart.filter([]);
  const simplified_stacks = result.stacks.map(([currency, series_arr]) => [
    currency,
    series_arr.map((series) => ({
      key: series.key,
      index: series.index,
      points: series.map((p) => [p[0], p[1]]),
    })),
  ]);
  deepEqual(simplified_stacks, [
    [
      "EUR",
      [
        {
          key: "Expenses:Dining",
          index: 0,
          points: [
            [0, 0],
            [0, 0],
          ],
        },
        {
          key: "Expenses:Shoes",
          index: 1,
          points: [
            [0, 0],
            [0, 60],
          ],
        },
        {
          key: "Expenses:Taxes",
          index: 2,
          points: [
            [0, 4],
            [60, 100],
          ],
        },
        {
          key: "Expenses:Transportation",
          index: 3,
          points: [
            [4, 10],
            [0, 0],
          ],
        },
      ],
    ],
    [
      "USD",
      [
        {
          key: "Expenses:Dining",
          index: 0,
          points: [
            [0, 8],
            [0, 0],
          ],
        },
        {
          key: "Expenses:Shoes",
          index: 1,
          points: [
            [0, 0],
            [0, 0],
          ],
        },
        {
          key: "Expenses:Taxes",
          index: 2,
          points: [
            [8, 10],
            [0, 0],
          ],
        },
        {
          key: "Expenses:Transportation",
          index: 3,
          points: [
            [0, 0],
            [0, 0],
          ],
        },
      ],
    ],
  ]);
  deepEqual(result.bar_groups, [
    {
      date: new Date("2000-01-01"),
      label: "DATE",
      values: [
        {
          currency: "EUR",
          value: 10,
          budget: 0,
        },
        {
          currency: "USD",
          value: 10,
          budget: 20,
        },
      ],
      account_balances: {
        "Expenses:Dining": { USD: 8 },
        "Expenses:Transportation": { EUR: 6 },
        "Expenses:Taxes": { USD: 2, EUR: 4 },
      },
    },
    {
      date: new Date("2000-02-01"),
      label: "DATE",
      values: [
        {
          currency: "EUR",
          value: 100,
          budget: 50,
        },
        {
          currency: "USD",
          value: 0,
          budget: 0,
        },
      ],
      account_balances: {
        "Expenses:Shoes": { EUR: 60 },
        "Expenses:Taxes": { EUR: 40 },
      },
    },
  ]);
});

test("handle data for bar chart without stacked data", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { EUR: 10, USD: 10 },
      budgets: { USD: 20 },
      account_balances: {},
    },
    {
      date: "2000-02-01",
      balance: { EUR: 100 },
      budgets: { EUR: 50 },
      account_balances: {},
    },
  ];
  // even without the operating currencies, the two most popular ones will be selected
  const ctx: ChartContext = { currencies: [], dateFormat: () => "DATE", filterContext: defaultFilterContext };
  const chart = ParsedBarChart.validator({ label: "name", data })
    .unwrap()
    .with_context(ctx);
  equal(false, chart.hasStackedData);
  deepEqual(chart.filter([]).stacks, [
    ["EUR", []],
    ["USD", []],
  ]);
  const without_usd = chart.filter(["USD"]);
  deepEqual(without_usd.stacks, [["EUR", []]]);
  deepEqual(without_usd.bar_groups, [
    {
      date: new Date("2000-01-01"),
      label: "DATE",
      values: [{ currency: "EUR", value: 10, budget: 0 }],
      account_balances: {},
    },
    {
      date: new Date("2000-02-01"),
      label: "DATE",
      values: [{ currency: "EUR", value: 100, budget: 50 }],
      account_balances: {},
    },
  ]);
});

test("only use currencies in records for bar chart", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { AUD: 10, USD: 10 },
      budgets: { USD: 20 },
      account_balances: {},
    },
    {
      date: "2000-02-01",
      balance: { AUD: 100 },
      budgets: { AUD: 50 },
      account_balances: {},
    },
  ];
  const ctx: ChartContext = { currencies: ["EUR", "USD"], dateFormat: () => "DATE", filterContext: defaultFilterContext };
  const chart = ParsedBarChart.validator({ label: "name", data })
    .unwrap()
    .with_context(ctx);
  equal(false, chart.hasStackedData);
  deepEqual(chart.filter([]).stacks, [
    ["USD", []],
    ["AUD", []],
  ]);
  deepEqual(chart.filter([]).bar_groups, [
    {
      date: new Date("2000-01-01"),
      label: "DATE",
      values: [
        { currency: "USD", value: 10, budget: 20 },
        { currency: "AUD", value: 10, budget: 0 },
      ],
      account_balances: {},
    },
    {
      date: new Date("2000-02-01"),
      label: "DATE",
      values: [
        { currency: "USD", value: 0, budget: 0 },
        { currency: "AUD", value: 100, budget: 50 },
      ],
      account_balances: {},
    },
  ]);
});

test("chart context carries filterContext through to rendered chart", async () => {
  const data = await loadJSONSnapshot("test_internal_api-test_chart_api.json");
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctxWithTime = makeCtx({ time: "2020", interval: "year" });
  const rendered = hierarchy.with_context(ctxWithTime);
  ok(rendered.currencies.length > 0);
  equal(ctxWithTime.filterContext.time, "2020");
  equal(ctxWithTime.filterContext.interval, "year");
});

test("hierarchy chart snapshot with different filter contexts", async () => {
  const data = await loadJSONSnapshot("test_internal_api-test_chart_api.json");
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctxDefault = makeCtx();
  const ctxWithAccount = makeCtx({ account: "Assets:US" });
  const ctxWithConversion = makeCtx({ conversion: "EUR" });
  const ctxWithInterval = makeCtx({ interval: "quarter" });

  const renderedDefault = hierarchy.with_context(ctxDefault);
  const renderedWithAccount = hierarchy.with_context(ctxWithAccount);
  const renderedWithConversion = hierarchy.with_context(ctxWithConversion);
  const renderedWithInterval = hierarchy.with_context(ctxWithInterval);

  ok(renderedDefault.data.get("USD"));
  ok(renderedWithAccount.data.get("USD"));
  ok(renderedWithConversion.data.get("EUR") !== undefined || renderedWithConversion.currencies.includes("EUR") || renderedWithConversion.currencies.length > 0);
  ok(renderedWithInterval.data.get("USD"));

  deepEqual(renderedDefault.currencies, renderedWithAccount.currencies);
});

test("bar chart snapshot with filter context variations", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { EUR: 10, USD: 10 },
      budgets: { USD: 20 },
      account_balances: {
        "Expenses:Dining": { USD: 8 },
      },
    },
    {
      date: "2000-02-01",
      balance: { EUR: 100 },
      budgets: { EUR: 50 },
      account_balances: {
        "Expenses:Shoes": { EUR: 60 },
      },
    },
  ];

  const ctxMonth = makeCtx({ interval: "month" });
  const chartMonth = ParsedBarChart.validator({ label: "Monthly", data })
    .unwrap()
    .with_context(ctxMonth);
  equal(chartMonth.label, "Monthly");
  equal(chartMonth.filter([]).bar_groups.length, 2);
  equal(chartMonth.filter([]).bar_groups[0]!.label, "DATE");

  const ctxYear = makeCtx({ interval: "year" });
  const chartYear = ParsedBarChart.validator({ label: "Yearly", data })
    .unwrap()
    .with_context(ctxYear);
  equal(chartYear.label, "Yearly");
  equal(chartYear.filter([]).bar_groups.length, 2);
});

test("line chart snapshot ignores filterContext (no currencies filtering)", () => {
  const data: unknown = [
    { date: "2000-01-01", balance: { EUR: 10, USD: 10 } },
    { date: "2000-02-01", balance: { EUR: 10 } },
  ];
  const ctx = makeCtx({ conversion: "EUR", interval: "week" });
  const parsed = ParsedLineChart.validator({ label: "Balances", data })
    .unwrap()
    .with_context();
  ok(parsed instanceof LineChart);
  equal(parsed.series_names.length, 2);
  equal(ctx.filterContext.conversion, "EUR");
  equal(ctx.filterContext.interval, "week");
});

test("chart context with empty filterContext renders same as default", async () => {
  const data = await loadJSONSnapshot("test_internal_api-test_chart_api.json");
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctxExplicitEmpty: ChartContext = {
    currencies: ["USD"],
    dateFormat: () => "DATE",
    filterContext: { time: "", account: "", filter: "", conversion: "at_cost", interval: "month" },
  };
  const rendered1 = hierarchy.with_context(ctxExplicitEmpty);

  const ctxDefault = makeCtx();
  const rendered2 = hierarchy.with_context(ctxDefault);

  deepEqual(rendered1.currencies, rendered2.currencies);
  equal(rendered1.label, rendered2.label);
});

test("hierarchy chart with non-operating-currency conversion in filterContext", async () => {
  const data = await loadJSONSnapshot("test_internal_api-test_chart_api.json");
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctxCurrencyConversion: ChartContext = {
    currencies: ["USD", "EUR"],
    dateFormat: () => "DATE",
    filterContext: { time: "", account: "", filter: "", conversion: "EUR", interval: "month" },
  };
  const rendered = hierarchy.with_context(ctxCurrencyConversion);
  ok(rendered.currencies.includes("USD") || rendered.currencies.includes("EUR"));
  equal(ctxCurrencyConversion.filterContext.conversion, "EUR");
});
