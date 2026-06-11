<script lang="ts">
  import type { AccountBudget } from "../api/validators.ts";
  import type { AccountTreeNode } from "../charts/hierarchy.ts";
  import { _ } from "../i18n.ts";
  import type { NonEmptyArray } from "../lib/array.ts";
  import { is_empty } from "../lib/objects.ts";
  import { toggled_accounts } from "../stores/accounts.ts";
  import { ctx } from "../stores/format.ts";
  import { currency_name } from "../stores/index.ts";
  import AccountCell from "./AccountCell.svelte";
  import Diff from "./Diff.svelte";
  import { getTreeTableNotShownContext } from "./helpers.ts";
  import IntervalTreeTableNode from "./IntervalTreeTableNode.svelte";

  type Nodes = NonEmptyArray<AccountTreeNode>;

  type BudgetStatus = "ok" | "near" | "over";

  interface Props {
    nodes: Nodes;
    budgets: Record<string, AccountBudget[]>;
    filter_status?: BudgetStatus | "all";
  }

  let { nodes, budgets, filter_status = "all" }: Props = $props();

  const not_shown = getTreeTableNotShownContext();

  let [node] = $derived(nodes);
  let { account, children } = $derived(node);
  let account_budgets = $derived(budgets[account]);

  let is_toggled = $derived($toggled_accounts.has(account));

  function aggregate_status(
    ab: AccountBudget | undefined,
    use_children: boolean,
  ): BudgetStatus | null {
    if (!ab) return null;
    const status_map = use_children ? ab.status : {};
    let has_status = false;
    for (const key in status_map) {
      has_status = true;
      const s = status_map[key] as BudgetStatus;
      if (s === "over") return "over";
    }
    for (const key in status_map) {
      const s = status_map[key] as BudgetStatus;
      if (s === "near") return "near";
    }
    return has_status ? "ok" : null;
  }

  $: overall_status = $derived<BudgetStatus | null>(() => {
    if (!account_budgets || account_budgets.length === 0) return null;
    let result: BudgetStatus | null = null;
    for (const ab of account_budgets) {
      const s = aggregate_status(ab, !is_toggled);
      if (s === "over") return "over";
      if (s === "near") result = "near";
      else if (!result && s === "ok") result = "ok";
    }
    return result;
  });

  $: row_status_class = $derived(() => {
    if (overall_status === "over") return "row-over";
    if (overall_status === "near") return "row-near";
    return "";
  });

  $: is_visible_by_filter = $derived(() => {
    if (filter_status === "all") return true;
    if (overall_status === null) return filter_status === "all";
    return overall_status === filter_status;
  });
</script>

{#if is_visible_by_filter}
  <li class={row_status_class}>
    <p>
      <AccountCell {node} />
      {#if account_budgets?.[0]?.category}
        <span class="category-tag" title={_("Budget category")}>
          {account_budgets[0].category}
        </span>
      {/if}
      {#if overall_status === "over"}
        <span class="row-badge over" title={_("Over budget")}>!</span>
      {:else if overall_status === "near"}
        <span class="row-badge near" title={_("Near budget limit")}>~</span>
      {/if}
      {#each nodes as n, index (index)}
        {@const account_budget = account_budgets?.[index]}
        {@const has_balance =
          !is_empty(n.balance) ||
          (account_budget != null && !is_empty(account_budget.budget))}
        {@const show_balance = !is_toggled && has_balance}
        {@const shown_balance = show_balance ? n.balance : n.balance_children}
        {@const shown_budget = show_balance
          ? account_budget?.budget
          : account_budget?.budget_children}
        {@const shown_status = show_balance
          ? account_budget?.status
          : account_budget?.status}
        {@const shown_ratio = show_balance
          ? account_budget?.ratio
          : account_budget?.ratio}
        <span class="num other" class:dimmed={!is_toggled && !has_balance}>
          {#each Object.entries(shown_balance) as [currency, number] (currency)}
            {@const budget = shown_budget?.[currency]}
            {@const status = shown_status?.[currency] as BudgetStatus | undefined}
            {@const ratio = shown_ratio?.[currency]}
            <span title={$currency_name(currency)}>
              {$ctx.amount(number, currency)}
            </span>
            {#if budget}
              <Diff
                diff={budget - number}
                num={budget}
                {currency}
                {status}
                {ratio}
              />
            {/if}
            <br />
          {/each}
          {#if shown_budget}
            {#each Object.entries(shown_budget).filter(([c]) => !(shown_balance[c] ?? 0)) as [currency, budget] (currency)}
              {@const status = shown_status?.[currency] as BudgetStatus | undefined}
              {@const ratio = shown_ratio?.[currency]}
              <span title={$currency_name(currency)}>
                {$ctx.amount(0, currency)}
              </span>
              <Diff
                diff={budget}
                num={budget}
                {currency}
                {status}
                {ratio}
              />
              <br />
            {/each}
          {/if}
        </span>
      {/each}
    </p>
    {#if !is_toggled && children.some((n) => !$not_shown.has(n.account))}
      <ol>
        {#each children as child, index (child.account)}
          {#if !$not_shown.has(child.account)}
            <IntervalTreeTableNode
              nodes={nodes.map((n) => n.children[index]) as unknown as Nodes}
              {budgets}
              {filter_status}
            />
          {/if}
        {/each}
      </ol>
    {/if}
  </li>
{/if}

<style>
  .category-tag {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 8px;
    font-size: 0.75em;
    color: #31708f;
    background-color: #d9edf7;
    border: 1px solid #bce8f1;
    border-radius: 10px;
    vertical-align: middle;
  }

  .row-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    margin-left: 4px;
    border-radius: 50%;
    font-size: 0.7em;
    font-weight: 700;
    vertical-align: middle;
  }

  .row-badge.near {
    color: #8a6d3b;
    background-color: #fcf8e3;
    border: 1px solid #faebcc;
  }

  .row-badge.over {
    color: #a94442;
    background-color: #f2dede;
    border: 1px solid #ebccd1;
  }

  .row-near > p {
    background-color: rgba(252, 248, 227, 0.4);
  }

  .row-over > p {
    background-color: rgba(242, 222, 222, 0.5);
  }
</style>
