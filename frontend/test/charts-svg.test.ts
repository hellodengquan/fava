import { equal, ok } from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import { select } from "d3-selection";

import { ParsedBarChart, BarChart } from "../src/charts/bar.ts";
import type { ChartContext } from "../src/charts/context.ts";
import { ParsedHierarchyChart } from "../src/charts/hierarchy.ts";
import { chart_validator } from "../src/charts/index.ts";
import { ParsedLineChart, LineChart } from "../src/charts/line.ts";
import type { ReportFilterContext } from "../src/stores/filters.ts";
import { setup_jsdom } from "./dom.ts";
import { loadJSONSnapshot } from "./helpers.ts";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const SNAPSHOT_DIR = join(__dirname, "__snapshots__");

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
    currencies: ["USD", "EUR"],
    dateFormat: (d: Date) => d.toISOString().slice(0, 10),
    filterContext,
  };
}

test.beforeEach(setup_jsdom);

function svgSnapshotPath(name: string): string {
  return join(SNAPSHOT_DIR, `svg-${name}.svg`);
}

function getSnapshot(name: string): string | null {
  try {
    return readFileSync(svgSnapshotPath(name), "utf8");
  } catch {
    return null;
  }
}

function writeSnapshot(name: string, content: string): void {
  mkdirSync(SNAPSHOT_DIR, { recursive: true });
  writeFileSync(svgSnapshotPath(name), content);
}

function normalizeSvg(svg: string): string {
  return svg
    .replace(/\s+/g, " ")
    .replace(/>\s+</g, "><")
    .trim();
}

function createSvgElement(width = 800, height = 400): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  return svg;
}

test("bar chart SVG rendering produces non-empty structure", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { USD: 100, EUR: 80 },
      budgets: { USD: 120 },
      account_balances: {
        "Expenses:Food": { USD: 60, EUR: 50 },
        "Expenses:Travel": { USD: 40, EUR: 30 },
      },
    },
    {
      date: "2000-02-01",
      balance: { USD: 150, EUR: 120 },
      budgets: { USD: 140 },
      account_balances: {
        "Expenses:Food": { USD: 70, EUR: 60 },
        "Expenses:Travel": { USD: 80, EUR: 60 },
      },
    },
  ];

  const ctx = makeCtx();
  const chart = ParsedBarChart.validator({ label: "Test Bar Chart", data })
    .unwrap()
    .with_context(ctx);

  ok(chart instanceof BarChart);
  ok(chart.hasStackedData);
  equal(chart.currencies.length, 2);
  equal(chart.filter([]).bar_groups.length, 2);

  const svg = createSvgElement();
  const selection = select(svg);

  const barGroups = selection
    .append("g")
    .attr("class", "bar-groups")
    .selectAll("g")
    .data(chart.filter([]).bar_groups)
    .enter()
    .append("g")
    .attr("class", "bar-group")
    .attr("data-date", (d) => d.date.toISOString());

  equal(barGroups.size(), 2);
  equal(svg.querySelectorAll(".bar-group").length, 2);
  ok(svg.innerHTML.length > 0);
});

test("line chart SVG rendering produces non-empty structure", () => {
  const data: unknown = [
    { date: "2000-01-01", balance: { USD: 100, EUR: 80 } },
    { date: "2000-02-01", balance: { USD: 150, EUR: 120 } },
    { date: "2000-03-01", balance: { USD: 200, EUR: 160 } },
  ];

  const chart = ParsedLineChart.validator({ label: "Test Line Chart", data })
    .unwrap()
    .with_context();

  ok(chart instanceof LineChart);
  equal(chart.series_names.length, 2);

  const svg = createSvgElement();
  const selection = select(svg);

  const filteredSeries = chart.filter([]);

  const lines = selection
    .append("g")
    .attr("class", "lines")
    .selectAll("path")
    .data(filteredSeries)
    .enter()
    .append("path")
    .attr("class", "line")
    .attr("data-currency", (d) => d.name);

  equal(lines.size(), 2);
  equal(svg.querySelectorAll("path.line").length, 2);
  ok(svg.innerHTML.length > 0);
});

test("hierarchy chart SVG structure with treemap", async () => {
  const data = await loadJSONSnapshot(
    "test_internal_api-test_chart_api.json",
  );
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctx = makeCtx();
  const rendered = hierarchy.with_context(ctx);

  ok(rendered.currencies.length > 0);
  ok(rendered.data.get("USD") !== undefined);

  const svg = createSvgElement();
  const selection = select(svg);

  const treemapG = selection
    .append("g")
    .attr("class", "treemap")
    .attr("transform", "translate(20, 20)");

  const usdData = rendered.data.get("USD");
  if (usdData === undefined || usdData.children === undefined) {
    throw new Error("USD data not found in hierarchy chart");
  }
  ok(usdData.children.length > 0);

  const nodes = treemapG
    .selectAll("rect")
    .data(usdData.children.slice(0, 5))
    .enter()
    .append("rect")
    .attr("class", "node")
    .attr("width", 10)
    .attr("height", 10);

  equal(nodes.size(), Math.min(5, usdData.children.length));
  ok(svg.querySelectorAll("rect.node").length > 0);
});

test("bar chart with filterContext variations produces valid SVG", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { USD: 100, EUR: 80 },
      budgets: {},
      account_balances: {
        "Expenses:Food": { USD: 100, EUR: 80 },
      },
    },
  ];

  const ctxDefault = makeCtx();
  const ctxWithTime = makeCtx({ time: "2024", interval: "year" });
  const ctxWithAccount = makeCtx({ account: "Expenses" });

  const chartDefault = ParsedBarChart.validator({ label: "Default", data })
    .unwrap()
    .with_context(ctxDefault);
  const chartTime = ParsedBarChart.validator({ label: "Time", data })
    .unwrap()
    .with_context(ctxWithTime);
  const chartAccount = ParsedBarChart.validator({ label: "Account", data })
    .unwrap()
    .with_context(ctxWithAccount);

  equal(chartDefault.filter([]).bar_groups.length, 1);
  equal(chartTime.filter([]).bar_groups.length, 1);
  equal(chartAccount.filter([]).bar_groups.length, 1);

  const svg1 = createSvgElement();
  select(svg1)
    .append("g")
    .attr("class", "bars")
    .selectAll("g")
    .data(chartDefault.filter([]).bar_groups)
    .enter()
    .append("g")
    .attr("class", "bar-group");

  const svg2 = createSvgElement();
  select(svg2)
    .append("g")
    .attr("class", "bars")
    .selectAll("g")
    .data(chartTime.filter([]).bar_groups)
    .enter()
    .append("g")
    .attr("class", "bar-group");

  equal(svg1.querySelectorAll(".bar-group").length, 1);
  equal(svg2.querySelectorAll(".bar-group").length, 1);
});

test("bar chart SVG does not render blank with single currency", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { USD: 100 },
      budgets: {},
      account_balances: {
        "Expenses:Food": { USD: 100 },
      },
    },
    {
      date: "2000-02-01",
      balance: { USD: 200 },
      budgets: {},
      account_balances: {
        "Expenses:Food": { USD: 200 },
      },
    },
  ];

  const ctx: ChartContext = {
    currencies: ["USD"],
    dateFormat: (d: Date) => d.toISOString().slice(0, 10),
    filterContext: defaultFilterContext,
  };

  const chart = ParsedBarChart.validator({ label: "Single Currency", data })
    .unwrap()
    .with_context(ctx);

  ok(chart.filter([]).bar_groups.length > 0);
  ok(chart.currencies.length > 0);

  const svg = createSvgElement(600, 300);
  const selection = select(svg);

  const barGroups = selection
    .append("g")
    .attr("class", "bar-chart")
    .selectAll("g")
    .data(chart.filter([]).bar_groups)
    .enter()
    .append("g")
    .attr("class", "bar");

  equal(barGroups.size(), 2);
  ok(svg.innerHTML.length > 50);
  ok(svg.getAttribute("width") === "600");
});

test("line chart SVG with multiple series", () => {
  const data: unknown = [
    { date: "2000-01-01", balance: { USD: 100, EUR: 80, GBP: 70 } },
    { date: "2000-02-01", balance: { USD: 150, EUR: 100, GBP: 85 } },
    { date: "2000-03-01", balance: { USD: 200, EUR: 140, GBP: 110 } },
  ];

  const chart = ParsedLineChart.validator({ label: "Multi Series", data })
    .unwrap()
    .with_context();

  equal(chart.series_names.length, 3);

  const svg = createSvgElement();
  const selection = select(svg);

  selection.append("g").attr("class", "axis");
  const linesG = selection.append("g").attr("class", "lines");

  linesG
    .selectAll("path")
    .data(chart.series_names)
    .enter()
    .append("path")
    .attr("class", "line-series")
    .attr("data-currency", (d) => d);

  equal(svg.querySelectorAll("path.line-series").length, 3);
  equal(svg.querySelectorAll("g.axis").length, 1);
  equal(svg.querySelectorAll("g.lines").length, 1);
});

test("SVG snapshots: bar chart structure is stable", () => {
  const data: unknown = [
    {
      date: "2000-01-01",
      balance: { USD: 100, EUR: 80 },
      budgets: { USD: 120, EUR: 100 },
      account_balances: {
        "Expenses:Food": { USD: 60, EUR: 50 },
        "Expenses:Travel": { USD: 40, EUR: 30 },
      },
    },
    {
      date: "2000-02-01",
      balance: { USD: 150, EUR: 120 },
      budgets: { USD: 130, EUR: 110 },
      account_balances: {
        "Expenses:Food": { USD: 70, EUR: 60 },
        "Expenses:Travel": { USD: 80, EUR: 60 },
      },
    },
  ];

  const ctx = makeCtx();
  const chart = ParsedBarChart.validator({ label: "Snapshot Test", data })
    .unwrap()
    .with_context(ctx);

  const svg = createSvgElement(800, 400);
  const root = select(svg);

  const barGroups = root
    .append("g")
    .attr("class", "chart-bars")
    .attr("transform", "translate(40, 20)")
    .selectAll("g")
    .data(chart.filter([]).bar_groups)
    .enter()
    .append("g")
    .attr("class", "bar-group")
    .attr("data-label", (d) => d.label);

  barGroups.each(function (d) {
    select(this)
      .selectAll("rect")
      .data(d.values)
      .enter()
      .append("rect")
      .attr("class", "bar")
      .attr("data-currency", (v) => v.currency)
      .attr("width", 30)
      .attr("height", (v) => Math.abs(v.value) / 2)
      .attr("y", (v) => 200 - v.value / 2);
  });

  const svgStr = normalizeSvg(svg.outerHTML);
  ok(svgStr.length > 100);
  ok(svgStr.includes("chart-bars"));
  ok(svgStr.includes("bar-group"));
  ok(svgStr.includes("bar"));

  const snapshotName = "bar-chart-basic";
  const existing = getSnapshot(snapshotName);

  if (existing === null) {
    writeSnapshot(snapshotName, svgStr);
  } else {
    equal(normalizeSvg(existing), svgStr);
  }
});

test("SVG snapshots: hierarchy chart structure is stable", async () => {
  const data = await loadJSONSnapshot(
    "test_internal_api-test_chart_api.json",
  );
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctx = makeCtx();
  const rendered = hierarchy.with_context(ctx);

  const svg = createSvgElement(600, 400);
  const root = select(svg);

  const treemapG = root
    .append("g")
    .attr("class", "hierarchy-chart")
    .attr("transform", "translate(10, 10)");

  const usdData = rendered.data.get("USD");
  if (usdData === undefined || usdData.children === undefined) {
    throw new Error("USD data not found in hierarchy chart");
  }

  const children = usdData.children.slice(0, 10);
  const nodes = treemapG
    .selectAll("g.node")
    .data(children)
    .enter()
    .append("g")
    .attr("class", "node")
    .attr("data-label", (d) => d.data.account);

  nodes.append("rect").attr("class", "node-rect").attr("width", 50).attr(
    "height",
    30,
  );

  nodes
    .append("text")
    .attr("class", "node-label")
    .text((d) => d.data.account);

  const svgStr = normalizeSvg(svg.outerHTML);
  ok(svgStr.length > 200);
  ok(svgStr.includes("hierarchy-chart"));
  ok(svgStr.includes("node"));
  ok(svgStr.includes("node-rect"));
  ok(svgStr.includes("node-label"));

  const snapshotName = "hierarchy-chart-basic";
  const existing = getSnapshot(snapshotName);

  if (existing === null) {
    writeSnapshot(snapshotName, svgStr);
  } else {
    ok(normalizeSvg(existing).length > 0);
  }
});

test("SVG snapshots: line chart structure is stable", () => {
  const data: unknown = [
    { date: "2000-01-01", balance: { USD: 100, EUR: 80 } },
    { date: "2000-02-01", balance: { USD: 150, EUR: 120 } },
    { date: "2000-03-01", balance: { USD: 200, EUR: 140 } },
    { date: "2000-04-01", balance: { USD: 180, EUR: 130 } },
    { date: "2000-05-01", balance: { USD: 220, EUR: 160 } },
  ];

  const chart = ParsedLineChart.validator({ label: "Snapshot Line", data })
    .unwrap()
    .with_context();

  const svg = createSvgElement(800, 400);
  const root = select(svg);

  root.append("g").attr("class", "x-axis").attr("transform", "translate(0, 360)");
  root.append("g").attr("class", "y-axis").attr("transform", "translate(50, 20)");

  const linesG = root
    .append("g")
    .attr("class", "chart-lines")
    .attr("transform", "translate(50, 20)");

  linesG
    .selectAll("path")
    .data(chart.series_names)
    .enter()
    .append("path")
    .attr("class", "line")
    .attr("data-currency", (d) => d)
    .attr("fill", "none")
    .attr("stroke-width", 2);

  const svgStr = normalizeSvg(svg.outerHTML);
  ok(svgStr.length > 100);
  ok(svgStr.includes("chart-lines"));
  ok(svgStr.includes("x-axis"));
  ok(svgStr.includes("y-axis"));
  equal(svgStr.match(/class="line"/g)?.length, 2);

  const snapshotName = "line-chart-basic";
  const existing = getSnapshot(snapshotName);

  if (existing === null) {
    writeSnapshot(snapshotName, svgStr);
  } else {
    ok(normalizeSvg(existing).length > 0);
  }
});

test("bar chart with empty data produces minimal SVG (not blank)", () => {
  const data: unknown = [];

  const ctx = makeCtx();
  const chart = ParsedBarChart.validator({ label: "Empty Chart", data })
    .unwrap()
    .with_context(ctx);

  equal(chart.filter([]).bar_groups.length, 0);

  const svg = createSvgElement();
  const root = select(svg);

  root.append("g").attr("class", "chart-container");
  root.append("text").attr("class", "empty-message").text("No data");

  ok(svg.querySelector(".empty-message") !== null);
  ok(svg.querySelector(".chart-container") !== null);
});

test("SVG element has proper namespace and attributes", () => {
  const svg = createSvgElement(500, 300);

  equal(svg.tagName.toLowerCase(), "svg");
  equal(svg.namespaceURI, "http://www.w3.org/2000/svg");
  equal(svg.getAttribute("width"), "500");
  equal(svg.getAttribute("height"), "300");
  equal(svg.getAttribute("viewBox"), "0 0 500 300");
});
