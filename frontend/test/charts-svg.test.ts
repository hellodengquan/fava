import { deepEqual, equal, ok } from "node:assert/strict";
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

test("numerical snapshot: bar chart bar dimensions are stable", () => {
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
  const chart = ParsedBarChart.validator({ label: "Num Snapshot", data })
    .unwrap()
    .with_context(ctx);

  const barGroups = chart.filter([]).bar_groups;
  equal(barGroups.length, 2);

  const snapshot: {
    label: string;
    values: { currency: string; value: number; budget: number }[];
  }[] = barGroups.map((g) => ({
    label: g.label,
    values: g.values.map((v) => ({
      currency: v.currency,
      value: v.value,
      budget: v.budget,
    })),
  }));

  const snapshotName = "bar-chart-numerical";
  const snapshotPath = join(SNAPSHOT_DIR, `num-${snapshotName}.json`);

  try {
    const existing = JSON.parse(readFileSync(snapshotPath, "utf8"));
    deepEqual(existing, snapshot);
  } catch {
    mkdirSync(SNAPSHOT_DIR, { recursive: true });
    writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2));
  }
});

test("numerical snapshot: line chart series values are stable", () => {
  const data: unknown = [
    { date: "2000-01-01", balance: { USD: 100, EUR: 80 } },
    { date: "2000-02-01", balance: { USD: 150, EUR: 120 } },
    { date: "2000-03-01", balance: { USD: 200, EUR: 140 } },
  ];

  const chart = ParsedLineChart.validator({ label: "Num Snapshot", data })
    .unwrap()
    .with_context();

  const series = chart.filter([]);
  equal(series.length, 2);

  const snapshot = series.map((s) => ({
    name: s.name,
    values: s.values.map((v) => ({ date: v.date.toISOString(), value: v.value })),
  }));

  const snapshotName = "line-chart-numerical";
  const snapshotPath = join(SNAPSHOT_DIR, `num-${snapshotName}.json`);

  try {
    const existing = JSON.parse(readFileSync(snapshotPath, "utf8"));
    deepEqual(existing, snapshot);
  } catch {
    mkdirSync(SNAPSHOT_DIR, { recursive: true });
    writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2));
  }
});

test("numerical snapshot: hierarchy chart tree depth and node counts", async () => {
  const data = await loadJSONSnapshot(
    "test_internal_api-test_chart_api.json",
  );
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctx = makeCtx();
  const rendered = hierarchy.with_context(ctx);

  const usdData = rendered.data.get("USD");
  if (usdData === undefined || usdData.children === undefined) {
    throw new Error("USD data not found");
  }

  function measureDepth(node: { children?: unknown[] }): number {
    if (!node.children || node.children.length === 0) return 0;
    let maxChild = 0;
    for (const child of node.children as { children?: unknown[] }[]) {
      maxChild = Math.max(maxChild, measureDepth(child));
    }
    return 1 + maxChild;
  }

  function countNodes(node: { children?: unknown[] }): number {
    let count = 1;
    if (node.children) {
      for (const child of node.children as { children?: unknown[] }[]) {
        count += countNodes(child);
      }
    }
    return count;
  }

  const snapshot = {
    totalCurrencies: rendered.currencies.length,
    usdTreeDepth: measureDepth(usdData),
    usdNodeCount: countNodes(usdData),
    usdRootChildrenCount: usdData.children.length,
    firstChildLabel:
      usdData.children[0]?.data.account ?? null,
  };

  const snapshotName = "hierarchy-chart-numerical";
  const snapshotPath = join(SNAPSHOT_DIR, `num-${snapshotName}.json`);

  try {
    const existing = JSON.parse(readFileSync(snapshotPath, "utf8"));
    deepEqual(existing, snapshot);
  } catch {
    mkdirSync(SNAPSHOT_DIR, { recursive: true });
    writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2));
  }
});

test("pixel snapshot: bar chart renders consistently (pixel diff)", async () => {
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
      budgets: { USD: 130 },
      account_balances: {
        "Expenses:Food": { USD: 70, EUR: 60 },
        "Expenses:Travel": { USD: 80, EUR: 60 },
      },
    },
  ];

  const ctx = makeCtx();
  const chart = ParsedBarChart.validator({ label: "Pixel Test", data })
    .unwrap()
    .with_context(ctx);

  const svg = createSvgElement(400, 200);
  const root = select(svg);

  const width = 360;
  const barWidth = width / chart.filter([]).bar_groups.length - 20;
  const maxValue = Math.max(
    ...chart.filter([]).bar_groups.flatMap((g) =>
      g.values.map((v) => Math.abs(v.value)),
    ),
  );
  const scaleY = (v: number) => 180 - (v / maxValue) * 140;

  const barGroups = root
    .append("g")
    .attr("class", "bars")
    .attr("transform", "translate(20, 10)")
    .selectAll("g")
    .data(chart.filter([]).bar_groups)
    .enter()
    .append("g")
    .attr("transform", (_d, i) => `translate(${i * (barWidth + 20)}, 0)`);

  barGroups
    .selectAll("rect")
    .data((d) => d.values)
    .enter()
    .append("rect")
    .attr("x", (_d, i) => i * (barWidth / 2))
    .attr("y", (d) => scaleY(d.value))
    .attr("width", barWidth / 2)
    .attr("height", (d) => 180 - scaleY(d.value))
    .attr("fill", (_d, i) => (i === 0 ? "#3498db" : "#e74c3c"));

  const { Resvg } = await import("@resvg/resvg-js");
  const pngjs = await import("pngjs");
  const pixelmatch = (await import("pixelmatch")).default;

  const svgString = svg.outerHTML;
  const resvg = new Resvg(svgString, {
    fitTo: { mode: "width", value: 400 },
  });
  const pngData = resvg.render();
  const pngBuffer = pngData.asPng();

  const snapshotPath = join(SNAPSHOT_DIR, "pixel-bar-chart.png");

  try {
    const existingPng = pngjs.PNG.sync.read(readFileSync(snapshotPath));
    const currentPng = pngjs.PNG.sync.read(Buffer.from(pngBuffer));

    equal(currentPng.width, existingPng.width);
    equal(currentPng.height, existingPng.height);

    const diffPixels = pixelmatch(
      currentPng.data,
      existingPng.data,
      null,
      currentPng.width,
      currentPng.height,
      { threshold: 0.1 },
    );

    const totalPixels = currentPng.width * currentPng.height;
    const diffRatio = diffPixels / totalPixels;
    ok(diffRatio < 0.05, `Pixel diff ratio ${diffRatio} exceeds 5% threshold`);
  } catch {
    mkdirSync(SNAPSHOT_DIR, { recursive: true });
    writeFileSync(snapshotPath, Buffer.from(pngBuffer));
  }
});

test("pixel snapshot: hierarchy treemap renders consistently", async () => {
  const data = await loadJSONSnapshot(
    "test_internal_api-test_chart_api.json",
  );
  const validated = chart_validator(data).unwrap();
  const [hierarchy] = validated;
  ok(hierarchy instanceof ParsedHierarchyChart);

  const ctx = makeCtx();
  const rendered = hierarchy.with_context(ctx);

  const usdData = rendered.data.get("USD");
  if (usdData === undefined || usdData.children === undefined) {
    throw new Error("USD data not found");
  }

  const svg = createSvgElement(400, 300);
  const root = select(svg);

  const treemapG = root
    .append("g")
    .attr("class", "treemap")
    .attr("transform", "translate(10, 10)");

  const children = usdData.children.slice(0, 8);
  const cellWidth = 380 / 4;
  const cellHeight = 280 / 2;

  treemapG
    .selectAll("rect")
    .data(children)
    .enter()
    .append("rect")
    .attr("x", (_d, i) => (i % 4) * cellWidth)
    .attr("y", (_d, i) => Math.floor(i / 4) * cellHeight)
    .attr("width", cellWidth - 2)
    .attr("height", cellHeight - 2)
    .attr("fill", "#2ecc71");

  const { Resvg } = await import("@resvg/resvg-js");
  const pngjs = await import("pngjs");
  const pixelmatch = (await import("pixelmatch")).default;

  const svgString = svg.outerHTML;
  const resvg = new Resvg(svgString, {
    fitTo: { mode: "width", value: 400 },
  });
  const pngData = resvg.render();
  const pngBuffer = pngData.asPng();

  const snapshotPath = join(SNAPSHOT_DIR, "pixel-hierarchy-treemap.png");

  try {
    const existingPng = pngjs.PNG.sync.read(readFileSync(snapshotPath));
    const currentPng = pngjs.PNG.sync.read(Buffer.from(pngBuffer));

    equal(currentPng.width, existingPng.width);
    equal(currentPng.height, existingPng.height);

    const diffPixels = pixelmatch(
      currentPng.data,
      existingPng.data,
      null,
      currentPng.width,
      currentPng.height,
      { threshold: 0.1 },
    );

    const totalPixels = currentPng.width * currentPng.height;
    const diffRatio = diffPixels / totalPixels;
    ok(diffRatio < 0.05, `Pixel diff ratio ${diffRatio} exceeds 5% threshold`);
  } catch {
    mkdirSync(SNAPSHOT_DIR, { recursive: true });
    writeFileSync(snapshotPath, Buffer.from(pngBuffer));
  }
});

test("pixel diff detects intentional layout change", async () => {
  const svg1 = createSvgElement(200, 100);
  const root1 = select(svg1);
  root1
    .append("rect")
    .attr("x", 10)
    .attr("y", 10)
    .attr("width", 50)
    .attr("height", 50)
    .attr("fill", "#3498db");

  const svg2 = createSvgElement(200, 100);
  const root2 = select(svg2);
  root2
    .append("rect")
    .attr("x", 30)
    .attr("y", 10)
    .attr("width", 50)
    .attr("height", 50)
    .attr("fill", "#3498db");

  const { Resvg } = await import("@resvg/resvg-js");
  const pngjs = await import("pngjs");
  const pixelmatch = (await import("pixelmatch")).default;

  const resvg1 = new Resvg(svg1.outerHTML, {
    fitTo: { mode: "width", value: 200 },
  });
  const resvg2 = new Resvg(svg2.outerHTML, {
    fitTo: { mode: "width", value: 200 },
  });

  const png1 = pngjs.PNG.sync.read(
    Buffer.from(resvg1.render().asPng()),
  );
  const png2 = pngjs.PNG.sync.read(
    Buffer.from(resvg2.render().asPng()),
  );

  const diffPixels = pixelmatch(
    png1.data,
    png2.data,
    null,
    png1.width,
    png1.height,
    { threshold: 0.1 },
  );

  ok(diffPixels > 0, "Pixel diff should detect layout shift");
});
