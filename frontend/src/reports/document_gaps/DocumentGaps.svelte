<script lang="ts">
  import { mark_document_gap } from "../../api/index.ts";
  import { _ } from "../../i18n.ts";
  import { router } from "../../router.ts";
  import type {
    AccountGapSummary,
    DocumentGapsReportProps,
    TransactionGap,
  } from "./index.ts";

  let { report }: DocumentGapsReportProps = $props();

  type ViewMode = "transactions" | "accounts";
  type HandledFilter = "all" | "unhandled" | "handled";

  let viewMode: ViewMode = $state("transactions");
  let handledFilter: HandledFilter = $state("unhandled");
  let accountFilter: string = $state("");
  let searchQuery: string = $state("");

  const filteredTransactionGaps = $derived(
    report.transaction_gaps.filter((g) => {
      if (handledFilter === "handled" && !g.handled) return false;
      if (handledFilter === "unhandled" && g.handled) return false;
      if (accountFilter) {
        if (!g.accounts.some((a) => a.startsWith(accountFilter))) return false;
      }
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const haystack =
          `${g.payee} ${g.narration} ${g.accounts.join(" ")} ${g.total_amount}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    }),
  );

  const filteredAccountSummaries = $derived(
    report.account_summaries.filter((a) => {
      if (a.transactions_without_docs === 0) return false;
      if (accountFilter && !a.account.startsWith(accountFilter)) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        if (!a.account.toLowerCase().includes(q)) return false;
      }
      return true;
    }),
  );

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

  function pct(value: number, total: number): string {
    if (total === 0) return "0%";
    return `${((value / total) * 100).toFixed(1)}%`;
  }

  const docCoveragePct = $derived(
    pct(
      report.stats.transactions_with_docs,
      report.stats.total_transactions,
    ),
  );
</script>

<div class="document-gaps-container">
  <section class="stats-section">
    <h2>{_("Statistics Summary")}</h2>
    <div class="stats-grid">
      <div class="stat-card total">
        <div class="stat-value">{report.stats.total_transactions}</div>
        <div class="stat-label">{_("Total Transactions")}</div>
      </div>
      <div class="stat-card with-docs">
        <div class="stat-value">
          {report.stats.transactions_with_docs}
          <span class="stat-sub">({docCoveragePct})</span>
        </div>
        <div class="stat-label">{_("With Documents")}</div>
      </div>
      <div class="stat-card missing">
        <div class="stat-value">{report.stats.transactions_without_docs}</div>
        <div class="stat-label">{_("Missing Documents")}</div>
      </div>
      <div class="stat-card handled">
        <div class="stat-value">{report.stats.handled_count}</div>
        <div class="stat-label">{_("Marked Handled")}</div>
      </div>
      <div class="stat-card unhandled warn">
        <div class="stat-value">{report.stats.unhandled_count}</div>
        <div class="stat-label">{_("Unhandled Gaps")}</div>
      </div>
      <div class="stat-card accounts">
        <div class="stat-value">
          {report.stats.accounts_with_gaps}/{report.stats.total_accounts}
        </div>
        <div class="stat-label">{_("Accounts with Gaps")}</div>
      </div>
    </div>
    {#if report.stats.missing_amount || report.stats.total_amount}
      <div class="amount-row">
        <span class="amount-label">{_("Missing Amount")}:</span>
        <span class="amount-value missing-amount">
          {report.stats.missing_amount || "-"}
        </span>
        <span class="amount-sep">/</span>
        <span class="amount-label">{_("Total Amount")}:</span>
        <span class="amount-value">{report.stats.total_amount || "-"}</span>
      </div>
    {/if}
  </section>

  <section class="controls-section">
    <div class="controls-row">
      <div class="view-switcher">
        <button
          class={viewMode === "transactions" ? "active" : ""}
          onclick={() => (viewMode = "transactions")}
        >
          {_("By Transaction")}
          <span class="badge">{filteredTransactionGaps.length}</span>
        </button>
        <button
          class={viewMode === "accounts" ? "active" : ""}
          onclick={() => (viewMode = "accounts")}
        >
          {_("By Account")}
          <span class="badge">{filteredAccountSummaries.length}</span>
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

  {#if viewMode === "transactions"}
    <section class="transactions-section">
      {#if filteredTransactionGaps.length === 0}
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
              {#each filteredTransactionGaps as gap (gap.entry_hash)}
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
                            onclick|preventDefault={() =>
                              jumpToAccount(acc)}
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
      {#if filteredAccountSummaries.length === 0}
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
              {#each filteredAccountSummaries as acc (acc.account)}
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
                      onclick={() => {
                        accountFilter = acc.account;
                        viewMode = "transactions";
                      }}
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
</div>

<style>
  .document-gaps-container {
    padding: 1rem 1.5rem;
    max-width: 1600px;
    margin: 0 auto;
  }

  h2 {
    margin: 0 0 1rem 0;
    font-size: 1.25rem;
  }

  .stats-section {
    background: var(--sidebar-background);
    border: 1px solid var(--sidebar-border);
    border-radius: 8px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
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

  @media (max-width: 768px) {
    .stats-grid {
      grid-template-columns: repeat(2, 1fr);
    }
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
