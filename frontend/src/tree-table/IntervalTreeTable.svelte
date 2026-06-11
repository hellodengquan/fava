<script lang="ts">
  import { intersection, min } from "d3-array";
  import { writable } from "svelte/store";

  import type { AccountBudget } from "../api/validators.ts";
  import type { AccountTreeNode } from "../charts/hierarchy.ts";
  import { urlForAccount } from "../helpers.ts";
  import { _ } from "../i18n.ts";
  import type { NonEmptyArray } from "../lib/array.ts";
  import { currentTimeFilterDateFormat } from "../stores/format.ts";
  import AccountCellHeader from "./AccountCellHeader.svelte";
  import { get_not_shown, setTreeTableNotShownContext } from "./helpers.ts";
  import IntervalTreeTableNode from "./IntervalTreeTableNode.svelte";

  type BudgetStatus = "ok" | "near" | "over";

  interface Props {
    trees: NonEmptyArray<AccountTreeNode>;
    dates: { begin: Date; end: Date }[];
    budgets: Record<string, AccountBudget[]>;
    accumulate: boolean;
    filter_status?: BudgetStatus | "all";
    filter_category?: string | "all";
  }

  let {
    trees,
    dates,
    budgets,
    accumulate,
    filter_status = "all",
    filter_category = "all",
  }: Props = $props();

  const not_shown = writable(new Set<string>());
  setTreeTableNotShownContext(not_shown);

  $effect(() => {
    $not_shown = intersection(
      ...trees.map((n, index) => $get_not_shown(n, dates[index]?.end ?? null)),
    );
  });

  let account = $derived(trees[0].account);
  let start_date = $derived(
    accumulate ? min(dates, (d) => d.begin) : undefined,
  );
  let start_date_filter = $derived(
    start_date ? $currentTimeFilterDateFormat(start_date) : undefined,
  );
  let time_filters = $derived(
    dates.map((date_range): [string, string] => {
      const title = $currentTimeFilterDateFormat(date_range.begin);
      return start_date_filter != null
        ? [title, `${start_date_filter}-${title}`]
        : [title, title];
    }),
  );

  let filtered_budgets = $derived(() => {
    if (filter_category === "all") return budgets;
    const result: Record<string, AccountBudget[]> = {};
    for (const [acc, arr] of Object.entries(budgets)) {
      const cat = arr?.[0]?.category;
      if (cat === filter_category) {
        result[acc] = arr;
      }
    }
    return result;
  });
</script>

<ol class="flex-table tree-table-new">
  <li class="head">
    <p>
      <AccountCellHeader {account} />
      {#each time_filters as [title, time] (time)}
        <span class="num other">
          <a href={$urlForAccount(account, { time })}>
            {title}
          </a>
        </span>
      {/each}
    </p>
  </li>
  <IntervalTreeTableNode nodes={trees} budgets={filtered_budgets} filter_status={filter_status} />
</ol>

<style>
  ol {
    overflow-x: auto;
  }
</style>
