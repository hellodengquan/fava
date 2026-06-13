<script lang="ts">
  import { _ } from "../../i18n.ts";
  import { operating_currency } from "../../stores/options.ts";
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
    tree: TreeNodeDiff;
  }

  let { tree }: Props = $props();
</script>

<ol class="flex-table tree-table-new" class:wider={$operating_currency.length > 1}>
  <li class="head">
    <p>
      <span class="account-cell">{_("Account")}</span>
      {#each $operating_currency as currency (currency)}
        <span class="num" title={$currency_name(currency)}>{currency}</span>
      {/each}
      <span class="num other">{_("Other")}</span>
    </p>
  </li>
  {#each tree.children as node (node.account)}
    <DiffTreeNode {node} depth={1} />
  {/each}
</ol>

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

  .wider {
    font-size: 0.9em;
  }
</style>
