<script lang="ts">
  import type { BudgetBreakdownAccount, BudgetBreakdownInterval } from "../../api/validators.ts";
  import { urlForAccount } from "../../helpers.ts";
  import {
    get_account_type,
    get_over_budget_label,
    get_over_budget_suggestion,
    get_amount_tier,
  } from "../../lib/budget_suggestions.ts";
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

  let account_type = $derived(get_account_type(node.account));

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

  function getOverBudgetPct(
    iv: BudgetBreakdownInterval,
    currency: string,
  ): number | null {
    const budget = iv.budget[currency];
    const diff = getDiff(iv, currency);
    if (budget == null || budget === 0 || diff == null) {
      return null;
    }
    return (diff / budget) * 100;
  }

  function getOverBudgetLabel(
    iv: BudgetBreakdownInterval,
    currency: string,
  ): string {
    const diff = getDiff(iv, currency);
    const pct = getOverBudgetPct(iv, currency);
    if (diff == null || diff <= 0) {
      return "";
    }
    return get_over_budget_label(pct, account_type);
  }

  function getOverBudgetSuggestion(
    iv: BudgetBreakdownInterval,
    currency: string,
  ): string {
    const budget = iv.budget[currency];
    const diff = getDiff(iv, currency);
    const pct = getOverBudgetPct(iv, currency);
    if (pct == null || diff == null || budget == null) {
      return "";
    }
    return get_over_budget_suggestion(
      pct,
      account_type,
      budget,
      diff,
      node.account,
    );
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

  type Severity = "severe" | "moderate" | "slight";

  function getSeverity(
    pct: number | null,
  ): Severity | null {
    if (pct == null) {
      return null;
    }
    if (pct > 50) {
      return "severe";
    }
    if (pct > 20) {
      return "moderate";
    }
    return "slight";
  }

  function getAccountTierBadge(iv: BudgetBreakdownInterval): string {
    const budgets = Object.values(iv.budget);
    if (budgets.length === 0) {
      return "";
    }
    const maxBudget = Math.max(...budgets.map(Math.abs));
    const tier = get_amount_tier(maxBudget);
    if (tier === "huge") {
      return "high-impact";
    }
    if (tier === "large") {
      return "significant";
    }
    return "";
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
          {@const pct = getOverBudgetPct(iv, currency)}
          {@const isOverBudget = diff != null && diff > 0 && budget != null && budget > 0}
          {@const severity = getSeverity(pct)}
          {@const overLabel = getOverBudgetLabel(iv, currency)}
          {@const overSuggestion = getOverBudgetSuggestion(iv, currency)}
          <span
            class="budget-row"
            class:over-budget={isOverBudget}
            title={isOverBudget ? `${overLabel}\n${overSuggestion}` : ""}
          >
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
            {#if isOverBudget && pct != null && severity != null}
              <span class="pct-val {severity}">
                +{pct.toFixed(0)}%
              </span>
            {/if}
            {#if change != null}
              <span class="change-val" class:positive={change <= 0} class:negative={change > 0}>
                Δ{change > 0 ? "+" : ""}{$ctx.num(Math.abs(change), currency)}
              </span>
            {/if}
          </span>
          {#if isOverBudget}
            <span class="over-budget-detail">
              <span class="over-budget-label {severity ?? 'slight'}">
                {overLabel}
              </span>
              <span class="over-budget-suggestion">{overSuggestion}</span>
            </span>
          {/if}
          <br />
        {/each}
        {#each Object.entries(iv.actual).filter(([c]) => !$operating_currency.includes(c)) as [currency] (currency)}
          {@const budget = iv.budget[currency]}
          {@const actual = iv.actual[currency]}
          {@const diff = getDiff(iv, currency)}
          {@const pct = getOverBudgetPct(iv, currency)}
          {@const isOverBudget = diff != null && diff > 0 && budget != null && budget > 0}
          {@const overLabel = getOverBudgetLabel(iv, currency)}
          {@const overSuggestion = getOverBudgetSuggestion(iv, currency)}
          <span
            class="budget-row"
            class:over-budget={isOverBudget}
            title={isOverBudget ? `${overLabel}\n${overSuggestion}` : $currency_name(currency)}
          >
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
            {#if isOverBudget && pct != null}
              <span class="pct-val {getSeverity(pct) ?? 'slight'}">
                +{pct.toFixed(0)}%
              </span>
            {/if}
          </span>
          {#if isOverBudget}
            <span class="over-budget-detail">
              <span class="over-budget-label {getSeverity(pct) ?? 'slight'}">
                {overLabel}
              </span>
              <span class="over-budget-suggestion">{overSuggestion}</span>
            </span>
          {/if}
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
    width: 20em;
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

  .pct-val {
    font-size: 0.8em;
    font-weight: bold;
    margin-left: 2px;
    white-space: nowrap;
  }

  .pct-val.slight {
    color: #b58900;
  }

  .pct-val.moderate {
    color: #cb4b16;
  }

  .pct-val.severe {
    color: #dc322f;
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

  .over-budget-detail {
    display: block;
    margin-top: 1px;
    margin-bottom: 2px;
    padding-left: 4px;
    border-left: 2px solid var(--diff-negative);
  }

  .over-budget-label {
    display: block;
    font-size: 0.78em;
    font-weight: 600;
    white-space: nowrap;
  }

  .over-budget-label.slight {
    color: #b58900;
    border-left-color: #b58900;
  }

  .over-budget-label.moderate {
    color: #cb4b16;
  }

  .over-budget-label.severe {
    color: #dc322f;
  }

  .over-budget-detail:has(.slight) {
    border-left-color: #b58900;
  }

  .over-budget-detail:has(.moderate) {
    border-left-color: #cb4b16;
  }

  .over-budget-detail:has(.severe) {
    border-left-color: #dc322f;
  }

  .over-budget-suggestion {
    display: block;
    font-size: 0.72em;
    color: var(--text-color-lighter);
    font-style: italic;
    white-space: nowrap;
  }
</style>
