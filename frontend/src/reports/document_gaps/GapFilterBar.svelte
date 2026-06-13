<script lang="ts">
  import { _ } from "../../i18n.ts";
  import { router } from "../../router.ts";
  import { mark_all_document_gaps } from "../../api/index.ts";
  import type { HandledFilter, ViewMode } from "./index.ts";

  let {
    viewMode,
    handledFilter,
    accountFilter,
    searchQuery,
    transactionCount,
    accountCount,
    unhandledCount,
    onViewModeChange,
    onHandledFilterChange,
    onAccountFilterChange,
    onSearchQueryChange,
  }: {
    viewMode: ViewMode;
    handledFilter: HandledFilter;
    accountFilter: string;
    searchQuery: string;
    transactionCount: number;
    accountCount: number;
    unhandledCount: number;
    onViewModeChange: (mode: ViewMode) => void;
    onHandledFilterChange: (filter: HandledFilter) => void;
    onAccountFilterChange: (value: string) => void;
    onSearchQueryChange: (value: string) => void;
  } = $props();

  let markingAll = $state(false);

  async function handleMarkAllHandled() {
    if (markingAll || unhandledCount === 0) return;
    if (
      !confirm(
        _("Are you sure you want to mark all {n} unhandled gaps as handled?", {
          n: unhandledCount,
        }),
      )
    ) {
      return;
    }

    markingAll = true;
    try {
      const count = await mark_all_document_gaps(true, true);
      if (count > 0) {
        router.reload();
      }
    } finally {
      markingAll = false;
    }
  }
</script>

<section class="controls-section">
  <div class="controls-row">
    <div class="view-switcher">
      <button
        class={viewMode === "transactions" ? "active" : ""}
        onclick={() => onViewModeChange("transactions")}
      >
        {_("By Transaction")}
        <span class="badge">{transactionCount}</span>
      </button>
      <button
        class={viewMode === "accounts" ? "active" : ""}
        onclick={() => onViewModeChange("accounts")}
      >
        {_("By Account")}
        <span class="badge">{accountCount}</span>
      </button>
    </div>

    <div class="filters">
      <input
        type="search"
        placeholder={_("Search payee, narration, account...")}
        value={searchQuery}
        oninput={(e) =>
          onSearchQueryChange((e.target as HTMLInputElement).value)}
        class="search-input"
      />
      <input
        type="text"
        placeholder={_("Account filter (e.g. Expenses)")}
        value={accountFilter}
        oninput={(e) =>
          onAccountFilterChange((e.target as HTMLInputElement).value)}
        class="account-input"
      />
      {#if viewMode === "transactions"}
        <select
          value={handledFilter}
          onchange={(e) =>
            onHandledFilterChange(
              (e.target as HTMLSelectElement).value as HandledFilter,
            )}
          class="handled-select"
        >
          <option value="all">{_("All Items")}</option>
          <option value="unhandled">{_("Unhandled Only")}</option>
          <option value="handled">{_("Handled Only")}</option>
        </select>
        <button
          class="batch-handle-btn"
          disabled={markingAll || unhandledCount === 0}
          onclick={handleMarkAllHandled}
        >
          {markingAll
            ? _("Processing...")
            : _("Mark all unhandled as handled")}
        </button>
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

  .batch-handle-btn {
    padding: 0.4rem 1rem;
    border: 1px solid var(--sidebar-border);
    border-radius: 4px;
    background: var(--primary-color, #1976d2);
    color: white;
    font-size: 0.85rem;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .batch-handle-btn:hover:not(:disabled) {
    opacity: 0.9;
  }

  .batch-handle-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
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
