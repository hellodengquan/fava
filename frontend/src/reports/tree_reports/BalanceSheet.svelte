<script lang="ts">
  import ChartSwitcher from "../../charts/ChartSwitcher.svelte";
  import SaveSnapshotButton from "../snapshots/SaveSnapshotButton.svelte";
  import TreeTable from "../../tree-table/TreeTable.svelte";
  import type { TreeReportProps } from "./index.ts";

  let { charts, trees, date_range }: TreeReportProps = $props();
  let end = $derived(date_range?.end ?? null);
</script>

<div class="snapshot-header">
  <SaveSnapshotButton report_type="balance_sheet" />
</div>

<ChartSwitcher {charts} />

<div class="row">
  <div class="column">
    {#each trees.slice(0, 1) as tree (tree.account)}
      <TreeTable {tree} {end} />
    {/each}
  </div>
  <div class="column">
    {#each trees.slice(1) as tree (tree.account)}
      <TreeTable {tree} {end} />
    {/each}
  </div>
</div>
