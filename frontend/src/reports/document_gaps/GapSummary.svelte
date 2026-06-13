<script lang="ts">
  import { _ } from "../../i18n.ts";
  import type { DocumentGapStats } from "./index.ts";

  let { stats }: { stats: DocumentGapStats } = $props();

  function pct(value: number, total: number): string {
    if (total === 0) return "0%";
    return `${((value / total) * 100).toFixed(1)}%`;
  }

  const docCoveragePct = $derived(
    pct(stats.transactions_with_docs, stats.total_transactions),
  );
</script>

<section class="stats-section">
  <h2>{_("Statistics Summary")}</h2>
  <div class="stats-grid">
    <div class="stat-card total">
      <div class="stat-value">{stats.total_transactions}</div>
      <div class="stat-label">{_("Total Transactions")}</div>
    </div>
    <div class="stat-card with-docs">
      <div class="stat-value">
        {stats.transactions_with_docs}
        <span class="stat-sub">({docCoveragePct})</span>
      </div>
      <div class="stat-label">{_("With Documents")}</div>
    </div>
    <div class="stat-card missing">
      <div class="stat-value">{stats.transactions_without_docs}</div>
      <div class="stat-label">{_("Missing Documents")}</div>
    </div>
    <div class="stat-card handled">
      <div class="stat-value">{stats.handled_count}</div>
      <div class="stat-label">{_("Marked Handled")}</div>
    </div>
    <div class="stat-card unhandled warn">
      <div class="stat-value">{stats.unhandled_count}</div>
      <div class="stat-label">{_("Unhandled Gaps")}</div>
    </div>
    <div class="stat-card accounts">
      <div class="stat-value">
        {stats.accounts_with_gaps}/{stats.total_accounts}
      </div>
      <div class="stat-label">{_("Accounts with Gaps")}</div>
    </div>
  </div>
  {#if stats.missing_amount || stats.total_amount}
    <div class="amount-row">
      <span class="amount-label">{_("Missing Amount")}:</span>
      <span class="amount-value missing-amount">
        {stats.missing_amount || "-"}
      </span>
      <span class="amount-sep">/</span>
      <span class="amount-label">{_("Total Amount")}:</span>
      <span class="amount-value">{stats.total_amount || "-"}</span>
    </div>
  {/if}
</section>

<style>
  .stats-section {
    background: var(--sidebar-background);
    border: 1px solid var(--sidebar-border);
    border-radius: 8px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
  }

  h2 {
    margin: 0 0 1rem 0;
    font-size: 1.25rem;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .stat-card {
    background: var(--body-background);
    border-radius: 6px;
    padding: 1rem;
    text-align: center;
    border: 1px solid var(--sidebar-border);
  }

  .stat-value {
    font-size: 1.75rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
  }

  .stat-sub {
    font-size: 0.8rem;
    font-weight: 400;
    opacity: 0.8;
  }

  .stat-label {
    font-size: 0.8rem;
    opacity: 0.8;
  }

  .stat-card.total .stat-value {
    color: var(--sidebar-color);
  }
  .stat-card.with-docs .stat-value {
    color: #2e7d32;
  }
  .stat-card.missing .stat-value {
    color: #c62828;
  }
  .stat-card.handled .stat-value {
    color: #1565c0;
  }
  .stat-card.unhandled.warn .stat-value {
    color: #e65100;
    font-weight: 800;
  }
  .stat-card.accounts .stat-value {
    font-size: 1.25rem;
  }

  .amount-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--sidebar-border);
    font-size: 0.95rem;
  }
  .amount-label {
    opacity: 0.8;
  }
  .amount-value {
    font-weight: 600;
  }
  .missing-amount {
    color: #c62828;
  }
  .amount-sep {
    opacity: 0.4;
    margin: 0 0.5rem;
  }
</style>
