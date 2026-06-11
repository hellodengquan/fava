<script lang="ts">
  import ChartSwitcher from "../../charts/ChartSwitcher.svelte";
  import { ParsedHierarchyChart } from "../../charts/hierarchy.ts";
  import { urlForAccount } from "../../helpers.ts";
  import { _ } from "../../i18n.ts";
  import { is_non_empty } from "../../lib/array.ts";
  import { intervalLabel } from "../../lib/interval.ts";
  import { currentTimeFilterDateFormat } from "../../stores/format.ts";
  import { interval } from "../../stores/url.ts";
  import IntervalTreeTable from "../../tree-table/IntervalTreeTable.svelte";
  import JournalTable from "../journal/JournalTable.svelte";
  import type { AccountReportProps } from "./index.ts";

  type BudgetStatus = "ok" | "near" | "over" | "all";

  let {
    account,
    report_type,
    charts,
    journal,
    interval_balances,
    dates,
    budgets,
    budget_categories,
  }: AccountReportProps = $props();

  let accumulate = $derived(report_type === "balances");
  let interval_label = $derived(intervalLabel($interval).toLowerCase());

  let filter_status: BudgetStatus = "all";
  let filter_category: string = "all";

  function compute_summary(): {
    total: number;
    ok: number;
    near: number;
    over: number;
  } {
    if (!budgets) return { total: 0, ok: 0, near: 0, over: 0 };
    let total = 0;
    let ok = 0;
    let near = 0;
    let over = 0;
    for (const arr of Object.values(budgets)) {
      if (!arr || arr.length === 0) continue;
      total++;
      const ab = arr[0];
      let worst: BudgetStatus = "ok";
      for (const s of Object.values(ab.status ?? {})) {
        if (s === "over") {
          worst = "over";
          break;
        }
        if (s === "near" && worst !== "over") worst = "near";
      }
      if (worst === "over") over++;
      else if (worst === "near") near++;
      else ok++;
    }
    return { total, ok, near, over };
  }

  let summary = $derived(compute_summary());

  let all_charts = $derived(
    interval_balances && dates
      ? [
          ...charts,
          ...interval_balances
            .slice(0, 3)
            .map(
              (node, index) =>
                new ParsedHierarchyChart(
                  $currentTimeFilterDateFormat(
                    dates[index]?.begin ?? new Date(),
                  ),
                  node,
                ),
            ),
        ]
      : charts,
  );
</script>

<ChartSwitcher charts={all_charts} />

<div class="droptarget" data-account-name={account}>
  <div class="headerline">
    <h3>
      {#if report_type !== "journal"}
        <a
          href={$urlForAccount(account)}
          title={_("Journal of all entries for this Account and Sub-Accounts")}
        >
          {_("Account Journal")}
        </a>
      {:else}
        {_("Account Journal")}
      {/if}
    </h3>
    <h3>
      {#if report_type !== "changes"}
        <a href={$urlForAccount(account, { r: "changes" })}>
          {_("Changes")} ({interval_label})
        </a>
      {:else}
        {_("Changes")} ({interval_label})
      {/if}
    </h3>
    <h3>
      {#if report_type !== "balances"}
        <a href={$urlForAccount(account, { r: "balances" })}>
          {_("Balances")} ({interval_label})
        </a>
      {:else}
        {_("Balances")} ({interval_label})
      {/if}
    </h3>
  </div>

  {#if report_type !== "journal" && interval_balances && budgets && dates && summary.total > 0}
    <div class="budget-toolbar">
      <div class="budget-summary" role="group" aria-label={_("Budget summary")}>
        <span class="summary-item total" title={_("Accounts with budgets")}>
          <span class="count">{summary.total}</span>
          <span class="label">{_("总预算项")}</span>
        </span>
        <button
          type="button"
          class={`summary-item ${filter_status === "ok" ? "active" : ""}`}
          class:ok
          on:click={() => (filter_status = filter_status === "ok" ? "all" : "ok")}
          title={_("Click to filter by normal budgets")}
        >
          <span class="count">{summary.ok}</span>
          <span class="label">{_("正常")}</span>
        </button>
        <button
          type="button"
          class={`summary-item ${filter_status === "near" ? "active" : ""}`}
          class:near
          on:click={() => (filter_status = filter_status === "near" ? "all" : "near")}
          title={_("Click to filter by near-overspent budgets")}
        >
          <span class="count">{summary.near}</span>
          <span class="label">{_("接近超支")}</span>
        </button>
        <button
          type="button"
          class={`summary-item ${filter_status === "over" ? "active" : ""}`}
          class:over
          on:click={() => (filter_status = filter_status === "over" ? "all" : "over")}
          title={_("Click to filter by overspent budgets")}
        >
          <span class="count">{summary.over}</span>
          <span class="label">{_("已超支")}</span>
        </button>
      </div>

      {#if budget_categories && budget_categories.length > 0}
        <div class="category-filter">
          <label for="category-select">{_("分类:")}</label>
          <select
            id="category-select"
            bind:value={filter_category}
            class="category-select"
          >
            <option value="all">{_("全部")}</option>
            {#each budget_categories as cat (cat)}
              <option value={cat}>{cat}</option>
            {/each}
          </select>
        </div>
      {/if}

      {#if filter_status !== "all" || filter_category !== "all"}
        <button
          type="button"
          class="reset-filter"
          on:click={() => {
            filter_status = "all";
            filter_category = "all";
          }}
        >
          {_("清除筛选")}
        </button>
      {/if}
    </div>
  {/if}

  {#if report_type === "journal" && journal != null}
    <JournalTable
      {journal}
      initial_sort={["date", "desc"]}
      show_change_and_balance={true}
    />
  {:else if interval_balances && is_non_empty(interval_balances) && budgets && dates}
    <IntervalTreeTable
      trees={interval_balances}
      {dates}
      {budgets}
      {accumulate}
      filter_status={filter_status}
      filter_category={filter_category}
    />
  {/if}
</div>

<style>
  .budget-toolbar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    padding: 12px 16px;
    margin: 8px 0 16px;
    background-color: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 6px;
  }

  .budget-summary {
    display: flex;
    gap: 0;
    border: 1px solid #dee2e6;
    border-radius: 6px;
    overflow: hidden;
  }

  .summary-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 8px 16px;
    background: white;
    border: none;
    cursor: default;
    min-width: 72px;
    transition: background-color 0.15s;
  }

  button.summary-item {
    cursor: pointer;
    border-left: 1px solid #dee2e6;
  }

  button.summary-item:hover {
    background-color: #e9ecef;
  }

  button.summary-item.active {
    background-color: #007bff;
    color: white;
  }

  button.summary-item.active.ok {
    background-color: #28a745;
  }

  button.summary-item.active.near {
    background-color: #f0ad4e;
    color: #5a3d00;
  }

  button.summary-item.active.over {
    background-color: #d9534f;
  }

  .summary-item .count {
    font-size: 1.25em;
    font-weight: 700;
    line-height: 1.2;
  }

  .summary-item .label {
    font-size: 0.75em;
    line-height: 1.2;
    margin-top: 2px;
    opacity: 0.85;
  }

  .summary-item.ok {
    color: #28a745;
  }

  .summary-item.near {
    color: #f0ad4e;
  }

  .summary-item.over {
    color: #d9534f;
  }

  .category-filter {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .category-filter label {
    font-size: 0.875em;
    color: #495057;
    font-weight: 500;
  }

  .category-select {
    padding: 6px 10px;
    font-size: 0.875em;
    border: 1px solid #ced4da;
    border-radius: 4px;
    background-color: white;
    cursor: pointer;
  }

  .category-select:focus {
    outline: none;
    border-color: #80bdff;
    box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
  }

  .reset-filter {
    padding: 6px 14px;
    font-size: 0.875em;
    color: #007bff;
    background-color: transparent;
    border: 1px solid #007bff;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .reset-filter:hover {
    background-color: #007bff;
    color: white;
  }
</style>
