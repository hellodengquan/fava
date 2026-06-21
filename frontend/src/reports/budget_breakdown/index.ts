import { get_budget_breakdown, get_consolidated_budget } from "../../api/index.ts";
import type { BudgetBreakdownReport, ConsolidatedBudgetReport } from "../../api/validators.ts";
import { _ } from "../../i18n.ts";
import { getURLFilters } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import BudgetBreakdown from "./BudgetBreakdown.svelte";
import ConsolidatedBudget from "./ConsolidatedBudget.svelte";

export interface BudgetBreakdownProps {
  data: BudgetBreakdownReport;
}

export interface ConsolidatedBudgetProps {
  data: ConsolidatedBudgetReport;
}

export const budget_breakdown = new Route<BudgetBreakdownProps>(
  "budget_breakdown",
  BudgetBreakdown,
  async (url) => {
    const account = url.searchParams.get("a") ?? "";
    const data = await get_budget_breakdown({
      ...getURLFilters(url),
      a: account,
    });
    return { data };
  },
  () => _("Budget Breakdown"),
);

export const consolidated_budget = new Route<ConsolidatedBudgetProps>(
  "consolidated_budget",
  ConsolidatedBudget,
  async (url) => {
    const account = url.searchParams.get("a") ?? "";
    const data = await get_consolidated_budget({
      ...getURLFilters(url),
      a: account,
    });
    return { data };
  },
  () => _("Consolidated Budget"),
);
