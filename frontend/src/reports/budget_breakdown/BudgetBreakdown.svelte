<script lang="ts">
  import type { BudgetBreakdownReport } from "../../api/validators.ts";
  import { _ } from "../../i18n.ts";
  import { type Interval,intervalLabel } from "../../lib/interval.ts";
  import { router } from "../../router.ts";
  import { interval as urlInterval } from "../../stores/url.ts";
  import BudgetBreakdownNode from "./BudgetBreakdownNode.svelte";

  interface Props {
    data: BudgetBreakdownReport;
  }

  let { data }: Props = $props();

  let current_interval = $derived($urlInterval);

  let interval_options: { value: Interval; label: string }[] = [
    { value: "month", label: intervalLabel("month") },
    { value: "quarter", label: intervalLabel("quarter") },
    { value: "year", label: intervalLabel("year") },
  ];

  function set_interval(iv: Interval) {
    router.set_search_param("interval", iv === "month" ? "" : iv);
  }
</script>

<div class="budget-breakdown">
  <div class="interval-switcher">
    <span class="switcher-label">{_("Interval")}:</span>
    {#each interval_options as opt (opt.value)}
      <button
        type="button"
        class="unset interval-btn"
        class:active={current_interval === opt.value}
        onclick={() => {
          set_interval(opt.value);
        }}
      >
        {opt.label}
      </button>
    {/each}
  </div>

  {#if data.root.intervals.length === 0}
    <p class="no-data">{_("No budget data available for this account.")}</p>
  {:else}
    <ol class="flex-table tree-table-new budget-tree">
      <li class="head">
        <p>
          <span class="account-header">{_("Account")}</span>
          {#each data.root.intervals as iv (iv.label)}
            <span class="num interval-col-header">{iv.label}</span>
          {/each}
        </p>
      </li>
      {#if data.root.children.length > 0}
        {#each data.root.children as child (child.account)}
          <BudgetBreakdownNode node={child} />
        {/each}
      {:else}
        <BudgetBreakdownNode node={data.root} />
      {/if}
    </ol>
  {/if}
</div>

<style>
  .budget-breakdown {
    margin-top: 1em;
  }

  .interval-switcher {
    display: flex;
    align-items: center;
    gap: 0.5em;
    margin-bottom: 1em;
    padding: 0.5em 0;
    border-bottom: 1px solid var(--table-border);
  }

  .switcher-label {
    font-weight: bold;
    margin-right: 0.5em;
    color: var(--text-color-lighter);
  }

  .interval-btn {
    padding: 0.3em 0.8em;
    border: 1px solid var(--table-border);
    border-radius: 3px;
    color: var(--text-color-lighter);
    background: transparent;
    cursor: pointer;
    transition: all 0.2s;
  }

  .interval-btn:hover {
    color: var(--text-color);
    border-color: var(--text-color-lighter);
  }

  .interval-btn.active {
    color: var(--text-color);
    background: var(--background-button);
    border-color: var(--treetable-expander);
    font-weight: bold;
  }

  .no-data {
    color: var(--text-color-lighter);
    font-style: italic;
    padding: 2em;
    text-align: center;
  }

  .budget-tree {
    overflow-x: auto;
  }

  .account-header {
    flex: 1;
    min-width: 14em;
    max-width: 30em;
    font-weight: bold;
  }

  .interval-col-header {
    width: 14em;
    font-weight: bold;
    text-align: right;
  }
</style>
