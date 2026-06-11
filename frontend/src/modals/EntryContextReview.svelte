<script lang="ts">
  import { onMount } from "svelte";

  import { get_journal } from "../api/index.ts";
  import type { Document, Entry, Transaction } from "../entries/index.ts";
  import { _ } from "../i18n.ts";
  import {
    getReviewStatus,
    statusLabels,
    statusColors,
    categoryLabels,
    detectIssues,
    type ReviewStatus,
    type ReviewInfo,
  } from "../lib/review.ts";
  import { notify } from "../notifications.ts";
  import {
    reviewStore,
    updateDocumentReviewStatus,
    clearDocumentReviewStatus,
    fetchEntryReviewInfo,
  } from "../stores/review.ts";
  import { accounts } from "../stores/index.ts";

  interface Props {
    entry: Document;
  }

  let { entry }: Props = $props();

  let reviewInfo = $state<ReviewInfo | null>(null);
  let reviewNotes = $state("");
  let isLoading = $state(false);
  let transactions: Transaction[] = [];

  onMount(async () => {
    if (entry.t === "Document") {
      await loadReviewData();
    }
  });

  async function loadReviewData() {
    isLoading = true;
    try {
      const serverInfo = await fetchEntryReviewInfo(entry.entry_hash);
      if (serverInfo) {
        reviewInfo = serverInfo;
        reviewNotes = serverInfo.notes ?? "";
      }

      const entries: Entry[] = await get_journal({});
      transactions = entries.filter(
        (e): e is Transaction => e.t === "Transaction",
      );

      if (!serverInfo) {
        const issues = detectIssues(entry, transactions, $accounts);
        const status = getReviewStatus(entry) ?? "pending";
        const notes = entry.meta.get("review_notes")?.toString();
        const reviewed_at = entry.meta.get("reviewed_at")?.toString();
        const reviewed_by = entry.meta.get("reviewed_by")?.toString();

        reviewInfo = {
          status,
          issues,
          notes,
          reviewed_at,
          reviewed_by,
        };
        reviewNotes = notes ?? "";
      } else {
        const issues = detectIssues(entry, transactions, $accounts);
        reviewInfo = { ...serverInfo, issues };
      }
    } catch (error) {
      console.error("Failed to load review data:", error);
    } finally {
      isLoading = false;
    }
  }

  async function approve() {
    if (!reviewInfo) return;
    const success = await updateDocumentReviewStatus(
      entry,
      "approved",
      reviewNotes || undefined,
    );
    if (success) {
      await loadReviewData();
      notify("文档已通过复核");
    }
  }

  async function reject() {
    if (!reviewInfo) return;
    const success = await updateDocumentReviewStatus(
      entry,
      "rejected",
      reviewNotes || undefined,
    );
    if (success) {
      await loadReviewData();
      notify("文档已拒绝复核");
    }
  }

  async function clearStatus() {
    if (!reviewInfo) return;
    const success = await clearDocumentReviewStatus(entry);
    if (success) {
      await loadReviewData();
      notify("复核状态已清除");
    }
  }

  $effect(() => {
    const updatedHash = $reviewStore.lastUpdatedHash;
    const updatedStatus = $reviewStore.lastUpdatedStatus;
    if (updatedHash === entry.entry_hash && reviewInfo) {
      const newStatus = updatedStatus ?? "pending";
      if (updatedStatus === null) {
        reviewInfo = { ...reviewInfo, status: "pending", reviewed_at: undefined, notes: undefined };
      } else {
        reviewInfo = { ...reviewInfo, status: newStatus };
      }
    }
  });
</script>

{#if entry.t === "Document"}
  <div class="review-section">
    <h4>{_("复核状态")}</h4>

    {#if isLoading}
      <p class="loading">{_("加载中...")}</p>
    {:else if reviewInfo}
      <div class="status-display">
        <span
          class="status-badge"
          style="background-color: {statusColors[reviewInfo.status as ReviewStatus]}"
        >
          {statusLabels[reviewInfo.status as ReviewStatus]}
        </span>
        {#if reviewInfo.reviewed_at}
          <span class="review-time">
            {_("复核时间")}: {new Date(reviewInfo.reviewed_at).toLocaleString()}
          </span>
        {/if}
      </div>

      {#if reviewInfo.issues.length > 0}
        <div class="issues-section">
          <h5>{_("检测到的问题")}:</h5>
          <ul class="issues-list">
            {#each reviewInfo.issues as issue}
              <li class="issue-item">
                <span
                  class="issue-tag"
                  class:issue-account={issue.category === "account_mismatch"}
                  class:issue-amount={issue.category === "amount_discrepancy"}
                  class:issue-missing={issue.category === "missing_fields"}
                >
                  {categoryLabels[issue.category]}
                </span>
                <div class="issue-content">
                  <strong>{issue.description}</strong>
                  {#if issue.details}
                    <p class="issue-details">{issue.details}</p>
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if reviewInfo.notes}
        <div class="notes-section">
          <h5>{_("复核备注")}:</h5>
          <p class="notes-text">{reviewInfo.notes}</p>
        </div>
      {/if}

      <div class="review-form">
        <label for="review-notes-editor">{_("添加复核备注")}:</label>
        <textarea
          id="review-notes-editor"
          bind:value={reviewNotes}
          placeholder={_("请输入复核备注（可选）...")}
          rows={2}
        />
      </div>

      <div class="review-actions">
        <button
          class="btn-approve"
          onclick={approve}
          disabled={$reviewStore.isLoading}
        >
          ✓ {_("通过")}
        </button>
        <button
          class="btn-reject"
          onclick={reject}
          disabled={$reviewStore.isLoading}
        >
          ✗ {_("拒绝")}
        </button>
        {#if reviewInfo.status !== "pending"}
          <button
            class="btn-clear"
            onclick={clearStatus}
            disabled={$reviewStore.isLoading}
          >
            ↺ {_("清除状态")}
          </button>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .review-section {
    margin-top: 16px;
    padding: 16px;
    background: var(--table-header-background);
    border-radius: 6px;
    border: 1px solid var(--sidebar-border);
  }

  .review-section h4 {
    margin: 0 0 12px 0;
    font-size: 14px;
  }

  .loading {
    color: var(--dim-text);
    font-size: 13px;
  }

  .status-display {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }

  .status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 12px;
    color: white;
    font-weight: 500;
  }

  .review-time {
    font-size: 12px;
    color: var(--dim-text);
  }

  .issues-section {
    margin-bottom: 16px;
  }

  .issues-section h5 {
    margin: 0 0 8px 0;
    font-size: 13px;
  }

  .issues-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .issue-item {
    display: flex;
    gap: 10px;
    padding: 10px;
    background: var(--entry-background);
    border-radius: 4px;
    margin-bottom: 6px;
  }

  .issue-tag {
    flex-shrink: 0;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    height: fit-content;
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

  .issue-content {
    flex: 1;
  }

  .issue-content strong {
    font-size: 13px;
  }

  .issue-details {
    margin: 4px 0 0 0;
    font-size: 12px;
    color: var(--dim-text);
  }

  .notes-section {
    margin-bottom: 16px;
  }

  .notes-section h5 {
    margin: 0 0 4px 0;
    font-size: 13px;
  }

  .notes-text {
    margin: 0;
    padding: 8px 12px;
    background: var(--entry-background);
    border-radius: 4px;
    font-size: 13px;
    border-left: 3px solid var(--selected-border);
  }

  .review-form {
    margin-bottom: 12px;
  }

  .review-form label {
    display: block;
    margin-bottom: 4px;
    font-size: 12px;
    font-weight: 500;
  }

  .review-form textarea {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--sidebar-border);
    border-radius: 4px;
    background: var(--input-background);
    font-family: inherit;
    font-size: 13px;
    resize: vertical;
  }

  .review-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .review-actions button {
    padding: 6px 14px;
    border-radius: 4px;
    cursor: pointer;
    border: none;
    font-weight: 500;
    font-size: 13px;
  }

  .btn-approve {
    background: #10b981;
    color: white;
  }

  .btn-approve:hover:not(:disabled) {
    background: #059669;
  }

  .btn-reject {
    background: #ef4444;
    color: white;
  }

  .btn-reject:hover:not(:disabled) {
    background: #dc2626;
  }

  .btn-clear {
    background: #6b7280;
    color: white;
  }

  .btn-clear:hover:not(:disabled) {
    background: #4b5563;
  }

  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
