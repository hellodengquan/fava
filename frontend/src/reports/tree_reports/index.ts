import {
  get_balance_sheet,
  get_income_statement,
  get_trial_balance,
} from "../../api/index.ts";
import {
  type AccountTreeNode,
  ParsedHierarchyChart,
} from "../../charts/hierarchy.ts";
import type { ParsedFavaChart } from "../../charts/index.ts";
import { _ } from "../../i18n.ts";
import { getURLFilters } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import BalanceSheet from "./BalanceSheet.svelte";
import IncomeStatement from "./IncomeStatement.svelte";
import TrialBalance from "./TrialBalance.svelte";

export interface TreeReportProps {
  charts: ParsedFavaChart[];
  trees: AccountTreeNode[];
  date_range: { begin: Date; end: Date } | null;
}

interface TreeReportData {
  charts: ParsedFavaChart[];
  trees: AccountTreeNode[];
  date_range: { begin: Date; end: Date } | null;
}

function buildIncomeStatementCharts(
  trees: AccountTreeNode[],
): ParsedFavaChart[] {
  const [income, _profit, expenses] = trees;
  const charts: ParsedFavaChart[] = [];
  if (income && expenses) {
    charts.push(
      ParsedHierarchyChart.from_node(income),
      ParsedHierarchyChart.from_node(expenses),
    );
  }
  return charts;
}

function buildBalanceSheetCharts(
  trees: AccountTreeNode[],
): ParsedFavaChart[] {
  return trees.map(ParsedHierarchyChart.from_node);
}

function buildTrialBalanceCharts(
  trees: AccountTreeNode[],
): ParsedFavaChart[] {
  const root = trees[0];
  if (root) {
    return root.children.map(ParsedHierarchyChart.from_node);
  }
  return [];
}

async function loadIncomeStatement(
  url: URL,
): Promise<TreeReportData> {
  const report = await get_income_statement(getURLFilters(url));
  return report;
}

async function loadBalanceSheet(
  url: URL,
): Promise<TreeReportData> {
  const report = await get_balance_sheet(getURLFilters(url));
  return report;
}

async function loadTrialBalance(
  url: URL,
): Promise<TreeReportData> {
  const report = await get_trial_balance(getURLFilters(url));
  return report;
}

export const income_statement = new Route<TreeReportProps>(
  "income_statement",
  IncomeStatement,
  async (url) => {
    const report = await loadIncomeStatement(url);
    report.charts.push(...buildIncomeStatementCharts(report.trees));
    return report;
  },
  () => _("Income Statement"),
);

export const balance_sheet = new Route<TreeReportProps>(
  "balance_sheet",
  BalanceSheet,
  async (url) => {
    const report = await loadBalanceSheet(url);
    report.charts.push(...buildBalanceSheetCharts(report.trees));
    return report;
  },
  () => _("Balance Sheet"),
);

export const trial_balance = new Route<TreeReportProps>(
  "trial_balance",
  TrialBalance,
  async (url) => {
    const report = await loadTrialBalance(url);
    report.charts.push(...buildTrialBalanceCharts(report.trees));
    return report;
  },
  () => _("Trial Balance"),
);
