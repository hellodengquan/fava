<script lang="ts">
  import { _ } from "../../i18n.ts";
  import type { HandledFilter, ViewMode } from "./index.ts";

  let {
    viewMode,
    handledFilter,
    accountFilter,
    searchQuery,
    transactionCount,
    accountCount,
  }: {
    viewMode: ViewMode;
    handledFilter: HandledFilter;
    accountFilter: string;
    searchQuery: string;
    transactionCount: number;
    accountCount: number;
  } = $props();
</script>

<section class="controls-section">
  <div class="controls-row">
    <div class="view-switcher">
      <button
        class={viewMode === "transactions" ? "active" : ""}
        onclick={() => (viewMode = "transactions")}
      >
        {_("By Transaction")}
        <span class="badge">{transactionCount}</span>
      </button>
      <button
        class={viewMode === "accounts" ? "active" : ""}
        onclick={() => (viewMode = "accounts")}
      >
        {_("By Account")}
        <span class="badge">{accountCount}</span>
      </button>
    </div>

    <div class="filters">
      <input
        type="search"
        placeholder={_("Search payee, narration, account...")}
        bind:value={searchQuery}
        class="search-input"
      />
      <input
        type="text"
        placeholder={_("Account filter (e.g. Expenses)")}
        bind:value={accountFilter}
        class="account-input"
      />
      {#if viewMode === "transactions"}
        <select
          bind:value={handledFilter}
          class="handled-select"
        >
          <option value="all">{_("All Items")}</option>
          <option value="unhandled">{_("Unhandled Only")}</option>
          <option value="handled">{_("Handled Only")}</option>
        </select>
      {/if}
    </div>
  </div>
</section>

<style>
  .controls-section {
    margin-bottom: 1rem;
  }

  .controls-row {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    justify-content: space-between;
    align-items: center;
  }

  .view-switcher {
    display: inline-flex;
    border: 1px solid var(--sidebar-border);
    border-radius: 6px;
    overflow: hidden;
    background: var(--sidebar-background);
  }

  .view-switcher button {
    background: transparent;
    border: none;
    padding: 0.5rem 1rem;
    cursor: pointer;
    font-size: 0.9rem;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: background 0.15s;
  }

  .view-switcher button:hover {
    background: var(--sidebar-border);
  }

  .view-switcher button.active {
    background: var(--primary-color, #1976d2);
    color: white;
  }

  .badge {
    background: rgba(0, 0, 0, 0.15);
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
    font-size: 0.75rem;
  }

  .view-switcher button.active .badge {
    background: rgba(255, 255, 255, 0.25);
  }

  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .filters input,
  .filters select {
    padding: 0.4rem 0.75rem;
    border: 1px solid var(--sidebar-border);
    border-radius: 4px;
    background: var(--body-background);
    font-size: 0.85rem;
  }

  .search-input {
    min-width: 240px;
  }
  .account-input {
    min-width: 200px;
  }

  @media (max-width: 768px) {
    .controls-row {
      flex-direction: column;
      align-items: stretch;
    }
    .view-switcher button {
      flex: 1;
      justify-content: center;
    }
    .filters {
      flex-direction: column;
    }
    .filters input,
    .filters select {
      width: 100%;
    }
  }
</style>
