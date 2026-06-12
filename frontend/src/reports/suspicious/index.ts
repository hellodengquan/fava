import { get_suspicious_by_account, get_suspicious_by_time } from "../../api/index.ts";
import { _ } from "../../i18n.ts";
import { getURLFilters } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import Suspicious from "./Suspicious.svelte";

export interface SuspiciousReportProps {
  by_account: Awaited<ReturnType<typeof get_suspicious_by_account>>;
  by_time: Awaited<ReturnType<typeof get_suspicious_by_time>>;
  view_mode: "account" | "time";
  interval: string;
}

export const suspicious = new Route<SuspiciousReportProps>(
  "suspicious",
  Suspicious,
  async (url: URL) => {
    const filters = getURLFilters(url);
    const view_mode = (url.searchParams.get("view") as "account" | "time") || "account";
    const interval = url.searchParams.get("interval") || "month";

    const [by_account, by_time] = await Promise.all([
      get_suspicious_by_account(filters),
      view_mode === "time" ? get_suspicious_by_time({ ...filters, interval }) : Promise.resolve([]),
    ]);

    return {
      by_account,
      by_time,
      view_mode,
      interval,
    };
  },
  () => _("Suspicious Transactions"),
);
