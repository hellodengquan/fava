<script lang="ts">
  import { operating_currency } from "../../stores/options.ts";
  import { ctx } from "../../stores/format.ts";
  import { currency_name } from "../../stores/index.ts";
  import DiffTreeNode from "./DiffTreeNode.svelte";

  interface TreeNodeDiff {
    account: string;
    balance_diff: Record<string, number>;
    balance_children_diff: Record<string, number>;
    cost_diff: Record<string, number> | null;
    cost_children_diff: Record<string, number> | null;
    has_txns: boolean;
    children: TreeNodeDiff[];
  }

  interface Props {
    node: TreeNodeDiff;
    depth: number;
  }

  let { node, depth }: Props = $props();

  function has_any_diff(n: TreeNodeDiff): boolean {
    if (Object.keys(n.balance_diff).length > 0) return true;
    if (Object.keys(n.balance_children_diff).length > 0) return true;
    return n.children.some(has_any_diff);
  }

  function format_diff_value(diff: number, currency: string): string {
    const sign = diff > 0 ? "+" : "";
    return `${sign}${$ctx.num(diff, currency)}`;
  }
</script>

{#if has_any_diff(node)}
  <li>
    <p style="padding-left: {depth * 20}px">
      <span class="account-cell">{node.account}</span>
      {#each $operating_currency as currency (currency)}
        <span class="num">
          {#if node.balance_diff[currency] != null}
            <span class:positive={node.balance_diff[currency] > 0} class:negative={node.balance_diff[currency] < 0}>
              {format_diff_value(node.balance_diff[currency], currency)}
            </span>
          {/if}
        </span>
      {/each}
      <span class="num other">
        {#each Object.entries(node.balance_diff).filter(([c]) => !$operating_currency.includes(c)) as [currency, diff] (currency)}
          <span class:positive={diff > 0} class:negative={diff < 0}>
            {format_diff_value(diff, currency)} {$currency_name(currency)}
          </span><br />
        {/each}
      </span>
    </p>
    {#if node.children.length > 0}
      <ol>
        {#each node.children as child (child.account)}
          {#if has_any_diff(child)}
            <DiffTreeNode node={child} depth={depth + 1} />
          {/if}
        {/each}
      </ol>
    {/if}
  </li>
{/if}

<style>
  .account-cell {
    display: inline-block;
    min-width: 200px;
  }

  span.num {
    display: inline-block;
    min-width: 80px;
    text-align: right;
  }

  span.num.other {
    min-width: 120px;
  }

  .positive {
    color: var(--diff-positive, green);
  }

  .negative {
    color: var(--diff-negative, red);
  }
</style>
