<script lang="ts">
  import { _ } from "../../i18n.ts";
  import { router } from "../../router.ts";
  import { mark_document_gap } from "../../api/index.ts";
  import type {
    AccountGapSummary,
    TransactionGap,
    ViewMode,
  } from "./index.ts";

  let {
    viewMode,
    transactionGaps,
    accountSummaries,
    onAccountFilter,
  }: {
    viewMode: ViewMode;
    transactionGaps: TransactionGap[];
    accountSummaries: AccountGapSummary[];
    onAccountFilter: (account: string) => void;
  } = $props();

  function pct(value: number, total: number): string {
    if (total === 0) return "0%";
    return `${((value / total) * 100).toFixed(1)}%`;
  }

  async function toggleHandled(gap: TransactionGap) {
    const ok = await mark_document_gap(gap.entry_hash, !gap.handled);
    if (ok) {
      router.reload();
    }
  }

  function jumpToTransaction(entryHash: string) {
    router.go(`journal/?filter=entry_hash:${entryHash}`);
  }

  function jumpToAccount(account: string) {
    router.go(`account/${account}/journal/`);
  }
</script>

{#if viewMode === "transactions"}
  <section class="transactions-section">
    {#if transactionGaps.length === 0}
      <div class="empty-state">
        <p>🎉 {_("No missing documents found for the current filters!")}</p>
      </div>
    {:else}
      <div class="table-wrapper">
        <table class="gap-table transactions-table">
          <thead>
            <tr>
              <th>{_("Date")}</th>
              <th>{_("Payee")}</th>
              <th>{_("Narration")}</th>
              <th>{_("Accounts")}</th>
              <th>{_("Amount")}</th>
              <th>{_("Tags/Links")}</th>
              <th>{_("Status")}</th>
              <th>{_("Actions")}</th>
            </tr>
          </thead>
          <tbody>
            {#each transactionGaps as gap (gap.entry_hash)}
              <tr class:handled-row={gap.handled}>
                <td class="date-cell">{gap.date}</td>
                <td class="payee-cell">{gap.payee || "-"}</td>
                <td class="narration-cell">{gap.narration || "-"}</td>
                <td class="accounts-cell">
                  <ul class="accounts-list">
                    {#each gap.accounts.slice(0, 3) as acc}
                      <li>
                        <a
                          href="#"
                          onclick|preventDefault={() => jumpToAccount(acc)}
                        >
                          {acc}
                        </a>
                      </li>
                    {/each}
                    {#if gap.accounts.length > 3}
                      <li class="more-acc">
                        +{gap.accounts.length - 3} {_("more")}
                      </li>
                    {/if}
                  </ul>
                </td>
                <td class="amount-cell">{gap.total_amount || "-"}</td>
                <td class="tags-cell">
                  {#if gap.tag_count > 0 || gap.link_count > 0}
                    <span class="tag-pill">
                      #{gap.tag_count} / ^{gap.link_count}
                    </span>
                  {/if}
                </td>
                <td class="status-cell">
                  {#if gap.handled}
                    <span class="status-badge handled-badge">
                      ✓ {_("Handled")}
                    </span>
                  {:else}
                    <span class="status-badge unhandled-badge">
                      ⚠ {_("Missing")}
                    </span>
                  {/if}
                </td>
                <td class="actions-cell">
                  <button
                    class="action-btn jump-btn"
                    title={_("View in Journal")}
                    onclick={() => jumpToTransaction(gap.entry_hash)}
                  >
                    🔍
                  </button>
                  <button
                    class="action-btn handle-btn"
                    title={
                      gap.handled
                        ? _("Mark as Unhandled")
                        : _("Mark as Handled")
                    }
                    onclick={() => toggleHandled(gap)}
                  >
                    {gap.handled ? "↩️" : "✓"}
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
{:else}
  <section class="accounts-section">
    {#if accountSummaries.length === 0}
      <div class="empty-state">
        <p>🎉 {_("No accounts with missing documents!")}</p>
      </div>
    {:else}
      <div class="table-wrapper">
        <table class="gap-table accounts-table">
          <thead>
            <tr>
              <th>{_("Account")}</th>
              <th class="num">{_("Total Txns")}</th>
              <th class="num">{_("With Docs")}</th>
              <th class="num">{_("Missing Docs")}</th>
              <th class="num">{_("Handled")}</th>
              <th>{_("Coverage")}</th>
              <th>{_("Missing Amount")}</th>
              <th>{_("Actions")}</th>
            </tr>
          </thead>
          <tbody>
            {#each accountSummaries as acc (acc.account)}
              {@const coverage = pct(
                acc.transactions_with_docs,
                acc.total_transactions,
              )}
              {@const coverageNum =
                acc.total_transactions > 0
                  ? (acc.transactions_with_docs / acc.total_transactions) *
                    100
                  : 0}
              <tr>
                <td class="account-name-cell">
                  <a
                    href="#"
                    onclick|preventDefault={() => jumpToAccount(acc.account)}
                  >
                    {acc.account}
                  </a>
                </td>
                <td class="num-cell">{acc.total_transactions}</td>
                <td class="num-cell ok">{acc.transactions_with_docs}</td>
                <td class="num-cell warn">{acc.transactions_without_docs}</td>
                <td class="num-cell info">{acc.handled_count}</td>
                <td class="coverage-cell">
                  <div class="coverage-bar-wrapper">
                    <div
                      class="coverage-bar"
                      style="width: {coverageNum}%"
                      class:low={coverageNum < 50}
                      class:mid={coverageNum >= 50 && coverageNum < 80}
                      class:high={coverageNum >= 80}
                    />
                  </div>
                  <span class="coverage-text">{coverage}</span>
                </td>
                <td class="amount-cell">{acc.missing_amount || "-"}</td>
                <td class="actions-cell">
                  <button
                    class="action-btn jump-btn"
                    title={_("View Account")}
                    onclick={() => jumpToAccount(acc.account)}
                  >
                    📁
                  </button>
                  <button
                    class="action-btn filter-btn"
                    title={_("Filter by this Account")}
                    onclick={() => onAccountFilter(acc.account)}
                  >
                    🔗
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
{/if}

<style>
  .table-wrapper {
    overflow-x: auto;
    border: 1px solid var(--sidebar-border);
    border-radius: 6px;
  }

  .gap-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }

  .gap-table th {
    background: var(--sidebar-background);
    padding: 0.75rem 0.75rem;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid var(--sidebar-border);
    position: sticky;
    top: 0;
  }

  .gap-table td {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--sidebar-border);
    vertical-align: top;
  }

  .gap-table tbody tr:hover {
    background: var(--sidebar-background);
  }

  .gap-table tbody tr.handled-row {
    opacity: 0.6;
  }

  .num,
  .num-cell {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .num-cell.ok {
    color: #2e7d32;
  }
  .num-cell.warn {
    color: #c62828;
    font-weight: 600;
  }
  .num-cell.info {
    color: #1565c0;
  }

  .accounts-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .accounts-list li {
    padding: 0.1rem 0;
  }

  .accounts-list a {
    color: var(--primary-color, #1976d2);
    text-decoration: none;
    font-size: 0.8rem;
  }
  .accounts-list a:hover {
    text-decoration: underline;
  }

  .more-acc {
    font-size: 0.75rem;
    opacity: 0.6;
    font-style: italic;
  }

  .tag-pill {
    display: inline-block;
    background: var(--sidebar-border);
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    font-size: 0.75rem;
  }

  .status-badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 500;
  }

  .handled-badge {
    background: rgba(46, 125, 50, 0.15);
    color: #2e7d32;
  }
  .unhandled-badge {
    background: rgba(198, 40, 40, 0.15);
    color: #c62828;
  }

  .actions-cell {
    white-space: nowrap;
  }

  .action-btn {
    background: transparent;
    border: 1px solid var(--sidebar-border);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    cursor: pointer;
    margin-right: 0.25rem;
    font-size: 0.9rem;
    transition: all 0.15s;
  }

  .action-btn:hover {
    background: var(--sidebar-border);
  }

  .account-name-cell a {
    font-weight: 500;
    color: inherit;
    text-decoration: none;
  }
  .account-name-cell a:hover {
    color: var(--primary-color, #1976d2);
  }

  .coverage-cell {
    min-width: 140px;
  }

  .coverage-bar-wrapper {
    width: 100%;
    height: 6px;
    background: var(--sidebar-border);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 0.25rem;
  }

  .coverage-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s;
  }

  .coverage-bar.low {
    background: #c62828;
  }
  .coverage-bar.mid {
    background: #f9a825;
  }
  .coverage-bar.high {
    background: #2e7d32;
  }

  .coverage-text {
    font-size: 0.75rem;
    opacity: 0.8;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--sidebar-color);
    opacity: 0.8;
  }

  .empty-state p {
    font-size: 1rem;
    margin: 0;
  }
</style>
