<script lang="ts">
  import type { BudgetBreakdownAccount, BudgetBreakdownInterval } from "../../api/validators.ts";
  import { urlForAccount } from "../../helpers.ts";
  import { leaf } from "../../lib/account.ts";
  import { is_empty } from "../../lib/objects.ts";
  import { toggle_account, toggled_accounts } from "../../stores/accounts.ts";
  import { ctx } from "../../stores/format.ts";
  import { currency_name } from "../../stores/index.ts";
  import { operating_currency } from "../../stores/options.ts";

  interface Props {
    node: BudgetBreakdownAccount;
  }

  let { node }: Props = $props();

  let is_toggled = $derived($toggled_accounts.has(node.account));

  let has_data = $derived(
    node.intervals.some(
      (iv) => !is_empty(iv.actual) || !is_empty(iv.budget),
    ),
  );

  let show_detail = $derived(!is_toggled && has_data);

  function getDiff(
    iv: BudgetBreakdownInterval,
    currency: string,
  ): number | null {
    const budget = iv.budget[currency];
    const actual = iv.actual[currency];
    if (budget == null && actual == null) {
      return null;
    }
    return (actual ?? 0) - (budget ?? 0);
  }

  function getChange(
    intervals: BudgetBreakdownInterval[],
    idx: number,
    currency: string,
  ): number | null {
    if (idx <= 0) {
      return null;
    }
    const prevInterval = intervals[idx - 1];
    const currInterval = intervals[idx];
    if (!prevInterval || !currInterval) {
      return null;
    }
    const prev = prevInterval.actual[currency];
    const curr = currInterval.actual[currency];
    if (prev == null || curr == null) {
      return null;
    }
    return curr - prev;
  }
</script>

<li>
  <p>
    <span class="account-cell-wrapper">
      {#if node.children.length > 0}
        <button
          type="button"
          class="unset toggle-btn"
          onclick={(event) => {
            toggle_account(node.account, event);
          }}
        >
          {is_toggled ? "▸" : "▾"}
        </button>
      {/if}
      <a href={$urlForAccount(node.account)} class="account-link">
        {leaf(node.account)}
      </a>
    </span>
    {#each node.intervals as iv, idx (idx)}
      <span class="num interval-col" class:dimmed={!show_detail && !is_toggled}>
        {#each $operating_currency as currency (currency)}
          {@const budget = iv.budget[currency]}
          {@const actual = iv.actual[currency]}
          {@const diff = getDiff(iv, currency)}
          {@const change = getChange(node.intervals, idx, currency)}
          {@const isOverBudget = diff != null && diff > 0 && budget != null && budget > 0}
          <span class="budget-row" class:over-budget={isOverBudget}>
            {#if actual != null}
              <span class="actual-val">{$ctx.amount(actual, currency)}</span>
            {:else if budget != null}
              <span class="actual-val muted">{$ctx.amount(0, currency)}</span>
            {/if}
            {#if budget != null}
              <span class="budget-val">/ {$ctx.amount(budget, currency)}</span>
            {/if}
            {#if diff != null && budget != null}
              <span class="diff-val" class:positive={diff <= 0} class:negative={diff > 0}>
                ({diff > 0 ? "+" : ""}{$ctx.num(Math.abs(diff), currency)})
              </span>
            {/if}
            {#if change != null}
              <span class="change-val" class:positive={change <= 0} class:negative={change > 0}>
                Δ{change > 0 ? "+" : ""}{$ctx.num(Math.abs(change), currency)}
              </span>
            {/if}
          </span>
          <br />
        {/each}
        {#each Object.entries(iv.actual).filter(([c]) => !$operating_currency.includes(c)) as [currency] (currency)}
          {@const budget = iv.budget[currency]}
          {@const actual = iv.actual[currency]}
          {@const diff = getDiff(iv, currency)}
          {@const isOverBudget = diff != null && diff > 0 && budget != null && budget > 0}
          <span class="budget-row" class:over-budget={isOverBudget} title={$currency_name(currency)}>
            {#if actual != null}
              <span class="actual-val">{$ctx.amount(actual, currency)}</span>
            {/if}
            {#if budget != null}
              <span class="budget-val">/ {$ctx.amount(budget, currency)}</span>
            {/if}
            {#if diff != null && budget != null}
              <span class="diff-val" class:positive={diff <= 0} class:negative={diff > 0}>
                ({diff > 0 ? "+" : ""}{$ctx.num(Math.abs(diff), currency)})
              </span>
            {/if}
          </span>
          <br />
        {/each}
      </span>
    {/each}
  </p>
  {#if !is_toggled && node.children.length > 0}
    <ol>
      {#each node.children as child (child.account)}
        <svelte:self node={child} />
      {/each}
    </ol>
  {/if}
</li>

<style>
  .account-cell-wrapper {
    display: flex;
    flex: 1;
    align-items: center;
    min-width: 14em;
    max-width: 30em;
  }

  .toggle-btn {
    position: absolute;
    padding: 0 3px;
    color: var(--treetable-expander);
  }

  .account-link {
    margin-left: 1em;
  }

  ol .account-cell-wrapper {
    --account-indent: 1em;
  }

  ol ol .account-cell-wrapper {
    --account-indent: 2em;
  }

  ol ol ol .account-cell-wrapper {
    --account-indent: 3em;
  }

  ol ol ol ol .account-cell-wrapper {
    --account-indent: 4em;
  }

  ol ol ol ol ol .account-cell-wrapper {
    --account-indent: 5em;
  }

  .interval-col {
    width: 14em;
    font-size: 0.9em;
  }

  .dimmed {
    opacity: 0.5;
  }

  .budget-row {
    display: inline;
  }

  .over-budget {
    background: rgba(220, 50, 47, 0.08);
    border-radius: 2px;
    padding: 0 2px;
  }

  .budget-val {
    color: var(--text-color-lighter);
    font-size: 0.85em;
  }

  .actual-val {
    font-weight: 500;
  }

  .muted {
    color: var(--text-color-lighter);
  }

  .diff-val {
    font-size: 0.85em;
    color: var(--diff-negative);
    white-space: nowrap;
  }

  .diff-val.positive {
    color: var(--diff-positive);
  }

  .change-val {
    font-size: 0.8em;
    margin-left: 2px;
    color: var(--diff-negative);
    white-space: nowrap;
  }

  .change-val.positive {
    color: var(--diff-positive);
  }
</style>
