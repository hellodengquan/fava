<script lang="ts">
  import type { ConsolidatedBudgetReport } from "../../api/validators.ts";
  import { _ } from "../../i18n.ts";
  import { type Interval, intervalLabel } from "../../lib/interval.ts";
  import { router } from "../../router.ts";
  import { interval as urlInterval } from "../../stores/url.ts";
  import ConsolidatedBudgetNode from "./ConsolidatedBudgetNode.svelte";

  interface Props {
    data: ConsolidatedBudgetReport;
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

<div class="consolidated-budget">
  <div class="consolidated-header">
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

    {#if data.ledgers.length > 0}
      <div class="ledger-info">
        <span class="info-label">{_("Consolidated from")}:</span>
        {#each data.ledgers as ledger (ledger.slug)}
          <span class="ledger-tag">{ledger.title}</span>
        {/each}
      </div>
    {/if}
  </div>

  <div class="scope-note">
    <span class="info-icon">ℹ</span>
    {_("Budget data is aggregated across all ledgers. Accounts are matched by name and amounts are summed.")}
    <br />
    <span class="info-icon">⚠</span>
    {_("Performance note: this report computes interval balances for each ledger, so it may be slower with many or large ledgers.")}
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
          <ConsolidatedBudgetNode node={child} />
        {/each}
      {:else}
        <ConsolidatedBudgetNode node={data.root} />
      {/if}
    </ol>
  {/if}
</div>

<style>
  .consolidated-budget {
    margin-top: 1em;
  }

  .consolidated-header {
    margin-bottom: 0.5em;
  }

  .interval-switcher {
    display: flex;
    align-items: center;
    gap: 0.5em;
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

  .ledger-info {
    display: flex;
    align-items: center;
    gap: 0.4em;
    flex-wrap: wrap;
    padding: 0.3em 0;
    font-size: 0.85em;
  }

  .info-label {
    color: var(--text-color-lighter);
    font-weight: 500;
  }

  .ledger-tag {
    background: var(--background-button);
    padding: 0.15em 0.5em;
    border-radius: 3px;
    font-size: 0.9em;
    border: 1px solid var(--table-border);
  }

  .scope-note {
    font-size: 0.8em;
    color: var(--text-color-lighter);
    padding: 0.5em 0.8em;
    margin-bottom: 0.5em;
    background: rgba(0, 0, 0, 0.02);
    border-radius: 3px;
    line-height: 1.6;
  }

  .info-icon {
    font-size: 1em;
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
    width: 20em;
    font-weight: bold;
    text-align: right;
  }
</style>
