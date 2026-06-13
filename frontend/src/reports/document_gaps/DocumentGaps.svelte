<script lang="ts">
  import GapSummary from "./GapSummary.svelte";
  import GapFilterBar from "./GapFilterBar.svelte";
  import GapList from "./GapList.svelte";
  import type {
    DocumentGapsReportProps,
    HandledFilter,
    ViewMode,
  } from "./index.ts";

  let { report }: DocumentGapsReportProps = $props();

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

  function handleAccountFilter(account: string) {
    accountFilter = account;
    viewMode = "transactions";
  }
</script>

<div class="document-gaps-container">
  <GapSummary stats={report.stats} />

  <GapFilterBar
    bind:viewMode
    bind:handledFilter
    bind:accountFilter
    bind:searchQuery
    transactionCount={filteredTransactionGaps.length}
    accountCount={filteredAccountSummaries.length}
  />

  <GapList
    viewMode={viewMode}
    transactionGaps={filteredTransactionGaps}
    accountSummaries={filteredAccountSummaries}
    onAccountFilter={handleAccountFilter}
  />
</div>

<style>
  .document-gaps-container {
    padding: 1rem 1.5rem;
    max-width: 1600px;
    margin: 0 auto;
  }

  @media (max-width: 768px) {
    .document-gaps-container {
      padding: 0.75rem 1rem;
    }
  }
</style>
