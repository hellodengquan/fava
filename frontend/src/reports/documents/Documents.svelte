<script lang="ts">
  import { group } from "d3-array";
  import { onMount } from "svelte";

  import { move_document, get_journal } from "../../api/index.ts";
  import type { Document, Transaction, Entry } from "../../entries/index.ts";
  import AccountInput from "../../entry-forms/AccountInput.svelte";
  import { _ } from "../../i18n.ts";
  import { basename } from "../../lib/paths.ts";
  import { stratifyAccounts } from "../../lib/tree.ts";
  import ModalBase from "../../modals/ModalBase.svelte";
  import { router } from "../../router.ts";
  import { reviewDocuments, reviewTransactions } from "../../stores/review.ts";
  import Accounts from "./Accounts.svelte";
  import DocumentPreview from "./DocumentPreview.svelte";
  import type { DocumentsReportProps } from "./index.ts";
  import Table from "./Table.svelte";
  import ReviewQueue from "./ReviewQueue.svelte";

  let { documents }: DocumentsReportProps = $props();

  type ViewMode = "list" | "review";
  let viewMode: ViewMode = $state("list");

  interface MoveDetails {
    account: string;
    filename: string;
    newName: string;
  }

  let grouped = $derived(group(documents, (d) => d.account));
  let node = $derived(
    stratifyAccounts(
      grouped.entries(),
      ([s]) => s,
      (name, d) => ({ name, count: d?.[1].length ?? 0 }),
    ),
  );

  let selected: Document | null = $state(null);
  let moving: MoveDetails | null = $state(null);
  let isLoadingTransactions = $state(false);

  onMount(async () => {
    $reviewDocuments = documents;
    await loadTransactions();
  });

  $effect(() => {
    $reviewDocuments = documents;
  });

  async function loadTransactions() {
    isLoadingTransactions = true;
    try {
      const entries: Entry[] = await get_journal({});
      const transactions = entries.filter(
        (e): e is Transaction => e.t === "Transaction",
      );
      $reviewTransactions = transactions;
    } catch (error) {
      console.error("Failed to load transactions:", error);
    } finally {
      isLoadingTransactions = false;
    }
  }

  /**
   * Rename the selected document with <F2>.
   */
  function keyup(ev: KeyboardEvent) {
    if (ev.key === "F2" && selected && !moving) {
      moving = {
        account: selected.account,
        filename: selected.filename,
        newName: basename(selected.filename),
      };
    }
  }

  async function move(event: SubmitEvent) {
    event.preventDefault();
    if (moving) {
      const moved = await move_document(
        moving.filename,
        moving.account,
        moving.newName,
      );
      if (moved) {
        moving = null;
        router.reload();
      }
    }
  }
</script>

<svelte:window onkeyup={keyup} />
{#if moving}
  <ModalBase
    shown={true}
    closeHandler={() => {
      moving = null;
    }}
  >
    <form onsubmit={move}>
      <h3>{_("Move or rename document")}</h3>
      <p><code>{moving.filename}</code></p>
      <p>
        <AccountInput bind:value={moving.account} />
        <input size={40} bind:value={moving.newName} />
        <button type="submit">{_("Move")}</button>
      </p>
    </form>
  </ModalBase>
{/if}
<div class="fixed-fullsize-container">
  <Accounts
    {node}
    move={(arg: { account: string; filename: string }) => {
      moving = { ...arg, newName: basename(arg.filename) };
    }}
  />
  <div class="main-content">
    <div class="view-tabs">
      <button
        class={["view-tab", { active: viewMode === "list" }]}
        onclick={() => (viewMode = "list")}
      >
        {_("文档列表")}
      </button>
      <button
        class={["view-tab", { active: viewMode === "review" }]}
        onclick={() => (viewMode = "review")}
      >
        {_("待复核队列")}
        {#if isLoadingTransactions}
          <span class="loading-indicator">...</span>
        {/if}
      </button>
    </div>

    {#if viewMode === "list"}
      <Table bind:selected data={documents} />
    {:else}
      {#if isLoadingTransactions}
        <div class="loading-state">{_("加载交易数据中...")}</div>
      {:else}
        <ReviewQueue />
      {/if}
    {/if}
  </div>
  {#if selected}
    <DocumentPreview filename={selected.filename} />
  {/if}
</div>

<style>
  .fixed-fullsize-container {
    display: grid;
    grid-template-columns: 1fr 2fr 3fr;
  }

  .fixed-fullsize-container > :global(*) {
    height: 100%;
    overflow: auto;
    resize: horizontal;
  }

  .fixed-fullsize-container > :global(* + *) {
    border-left: thin solid var(--sidebar-border);
  }

  .main-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .view-tabs {
    display: flex;
    border-bottom: 1px solid var(--sidebar-border);
    padding: 0 16px;
    background: var(--entry-background);
  }

  .view-tab {
    padding: 12px 20px;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 14px;
    color: var(--dim-text);
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .view-tab:hover {
    color: var(--text-color);
  }

  .view-tab.active {
    color: var(--text-color);
    border-bottom-color: var(--selected-border);
    font-weight: 500;
  }

  .loading-indicator {
    font-size: 12px;
    animation: pulse 1s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .loading-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--dim-text);
    font-size: 14px;
  }
</style>
