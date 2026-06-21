import { get_budget_breakdown } from "../../api/index.ts";
import type { BudgetBreakdownReport } from "../../api/validators.ts";
import { _ } from "../../i18n.ts";
import { getURLFilters } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import BudgetBreakdown from "./BudgetBreakdown.svelte";

export interface BudgetBreakdownProps {
  data: BudgetBreakdownReport;
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
