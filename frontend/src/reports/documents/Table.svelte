<script lang="ts">
  import type { Document } from "../../entries/index.ts";
  import { _ } from "../../i18n.ts";
  import { is_descendant_or_equal } from "../../lib/account.ts";
  import { basename } from "../../lib/paths.ts";
  import { DateColumn, Sorter, StringColumn } from "../../sort/index.ts";
  import SortHeader from "../../sort/SortHeader.svelte";
  import { selectedAccount } from "./stores.ts";
  import {
    getReviewStatus,
    statusLabels,
    statusColors,
    type ReviewStatus,
    detectIssues,
    categoryLabels,
  } from "../../lib/review.ts";
  import { reviewTransactions } from "../../stores/review.ts";
  import { accounts } from "../../stores/index.ts";

  interface Props {
    data: Document[];
    selected?: Document | null;
  }

  let { data, selected = $bindable(null) }: Props = $props();

  /**
   * Extract just the latter part of the filename if it starts with a date.
   */
  function name(doc: Document) {
    const base = basename(doc.filename);
    return base.startsWith(doc.date) ? base.substring(11) : base;
  }

  const columns = [
    new DateColumn<Document>(_("Date")),
    new StringColumn<Document>(_("Name"), (d) => name(d)),
  ] as const;
  let sorter = $state(new Sorter(columns[0], "desc"));

  let is_descendant_of_selected = $derived(
    is_descendant_or_equal($selectedAccount),
  );
  let filtered_documents = $derived(
    data.filter((doc) => is_descendant_of_selected(doc.account)),
  );
  let sorted_documents = $derived(sorter.sort(filtered_documents));

  function getDocIssues(doc: Document) {
    return detectIssues(doc, $reviewTransactions, $accounts);
  }

  function hasIssues(doc: Document): boolean {
    const status = getReviewStatus(doc);
    if (status === "approved" || status === "rejected") {
      return false;
    }
    return getDocIssues(doc).length > 0;
  }
</script>

<table>
  <thead>
    <tr>
      {#each columns as column (column)}
        <SortHeader bind:sorter {column} />
      {/each}
      <th class="status-header">{_("状态")}</th>
      <th class="issues-header">{_("问题")}</th>
    </tr>
  </thead>
  <tbody>
    <!-- eslint-disable-next-line svelte/require-each-key Documents might be duplicate -->
    {#each sorted_documents as doc}
      <tr
        class:selected={selected === doc}
        class:has-issues={hasIssues(doc)}
        draggable={true}
        title={doc.filename}
        ondragstart={(ev) => {
          ev.dataTransfer?.setData("fava/filename", doc.filename);
        }}
        onclick={() => {
          selected = doc;
        }}
      >
        <td>{doc.date}</td>
        <td>{name(doc)}</td>
        <td class="status-cell">
          {#if getReviewStatus(doc)}
            <span
              class="status-badge"
              style="background-color: {statusColors[getReviewStatus(doc) as ReviewStatus]}"
              title={statusLabels[getReviewStatus(doc) as ReviewStatus]}
            >
              {statusLabels[getReviewStatus(doc) as ReviewStatus]}
            </span>
          {:else if hasIssues(doc)}
            <span class="status-badge pending" title={_("待复核")}>
              {_("待复核")}
            </span>
          {/if}
        </td>
        <td class="issues-cell">
          {#if hasIssues(doc)}
            <div class="issues-container">
              {#each getDocIssues(doc).slice(0, 2) as issue}
                <span
                  class="issue-tag"
                  class:issue-account={issue.category === "account_mismatch"}
                  class:issue-amount={issue.category === "amount_discrepancy"}
                  class:issue-missing={issue.category === "missing_fields"}
                  title={issue.details || issue.description}
                >
                  {categoryLabels[issue.category]}
                </span>
              {/each}
              {#if getDocIssues(doc).length > 2}
                <span class="issue-more" title={getDocIssues(doc).slice(2).map(i => i.description).join('\n')}>
                  +{getDocIssues(doc).length - 2}
                </span>
              {/if}
            </div>
          {/if}
        </td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  table {
    width: 100%;
  }

  tr {
    cursor: pointer;
  }

  .selected,
  tr:hover {
    background-color: var(--table-header-background);
  }

  tr.has-issues {
    background-color: rgba(251, 191, 36, 0.1);
  }

  tr.has-issues:hover {
    background-color: rgba(251, 191, 36, 0.2);
  }

  .status-header,
  .issues-header {
    white-space: nowrap;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
    font-size: 12px;
    color: var(--dim-text);
  }

  .status-cell {
    padding: 8px 12px;
    white-space: nowrap;
  }

  .issues-cell {
    padding: 8px 12px;
    min-width: 180px;
  }

  .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    color: white;
    font-weight: 500;
  }

  .status-badge.pending {
    background-color: #fbbf24;
  }

  .issues-container {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }

  .issue-tag {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 500;
  }

  .issue-account {
    background: #fef3c7;
    color: #92400e;
  }

  .issue-amount {
    background: #fee2e2;
    color: #991b1b;
  }

  .issue-missing {
    background: #dbeafe;
    color: #1e40af;
  }

  .issue-more {
    font-size: 10px;
    color: var(--dim-text);
    background: var(--tag-background);
    padding: 2px 6px;
    border-radius: 4px;
  }
</style>
