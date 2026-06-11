<script lang="ts">
  import { _ } from "../../i18n.ts";
  import type { Document } from "../../entries/index.ts";
  import {
    categoryLabels,
    statusLabels,
    statusColors,
    type ReviewCategory,
    type ReviewStatus,
  } from "../../lib/review.ts";
  import {
    groupedByCategory,
    getDocumentReviewInfo,
    updateDocumentReviewStatus,
    clearDocumentReviewStatus,
    reviewStore,
  } from "../../stores/review.ts";
  import { basename } from "../../lib/paths.ts";
  import { selectedAccount } from "./stores.ts";
  import { is_descendant_or_equal } from "../../lib/account.ts";

  let selectedCategory: ReviewCategory | "all" = $state("all");
  let selectedDoc: Document | null = $state(null);
  let reviewNotes = $state("");
  let showReviewPanel = $state(false);

  let is_descendant_of_selected = $derived(
    is_descendant_or_equal($selectedAccount),
  );

  const categories: (ReviewCategory | "all")[] = [
    "all",
    "account_mismatch",
    "amount_discrepancy",
    "missing_fields",
  ];

  $effect(() => {
    void $groupedByCategory;
  });

  function filteredDocsByCategory(category: ReviewCategory | "all"): Document[] {
    const grouped = $groupedByCategory;
    if (category === "all") {
      const allDocs = new Set<Document>();
      for (const docs of Object.values(grouped)) {
        for (const doc of docs) {
          allDocs.add(doc);
        }
      }
      return Array.from(allDocs).filter(is_descendant_of_selected);
    }
    return grouped[category].filter(is_descendant_of_selected);
  }

  function name(doc: Document): string {
    const base = basename(doc.filename);
    return base.startsWith(doc.date) ? base.substring(11) : base;
  }

  function selectDocument(doc: Document) {
    selectedDoc = doc;
    showReviewPanel = true;
    reviewNotes = "";
  }

  function closeReviewPanel() {
    showReviewPanel = false;
    selectedDoc = null;
    reviewNotes = "";
  }

  async function approve() {
    if (selectedDoc) {
      const success = await updateDocumentReviewStatus(
        selectedDoc,
        "approved",
        reviewNotes || undefined,
      );
      if (success) {
        closeReviewPanel();
      }
    }
  }

  async function reject() {
    if (selectedDoc) {
      const success = await updateDocumentReviewStatus(
        selectedDoc,
        "rejected",
        reviewNotes || undefined,
      );
      if (success) {
        closeReviewPanel();
      }
    }
  }

  async function clearStatus() {
    if (selectedDoc) {
      const success = await clearDocumentReviewStatus(selectedDoc);
      if (success) {
        closeReviewPanel();
      }
    }
  }

  function getCategoryCount(category: ReviewCategory | "all"): number {
    return filteredDocsByCategory(category).length;
  }
</script>

<div class="review-queue">
  <div class="header">
    <h3>{_("待复核队列")}</h3>
    <span class="pending-count">
      {$groupedByCategory &&
        Object.values($groupedByCategory).flat().length > 0 &&
        `${Object.values($groupedByCategory).flat().filter(is_descendant_of_selected).length} 项待处理`}
    </span>
  </div>

  <div class="category-tabs">
    {#each categories as cat}
      <button
        class={["tab", { active: selectedCategory === cat }]}
        onclick={() => (selectedCategory = cat)}
      >
        {cat === "all" ? _("全部") : categoryLabels[cat]}
        <span class="count">{getCategoryCount(cat)}</span>
      </button>
    {/each}
  </div>

  <div class="document-list">
    {#if filteredDocsByCategory(selectedCategory).length === 0}
      <div class="empty-state">{_("暂无待复核文档")}</div>
    {:else}
      {#each filteredDocsByCategory(selectedCategory) as doc (doc.entry_hash)}
        <div
          class={["document-item", { selected: selectedDoc === doc }]}
          onclick={() => selectDocument(doc)}
        >
          <div class="doc-info">
            <div class="doc-date">{doc.date}</div>
            <div class="doc-name" title={doc.filename}>{name(doc)}</div>
            <div class="doc-account">{doc.account}</div>
          </div>
          {#each getDocumentReviewInfo(doc).issues as issue}
            <span class="issue-badge" class:issue-account={issue.category === "account_mismatch"} class:issue-amount={issue.category === "amount_discrepancy"} class:issue-missing={issue.category === "missing_fields"}>
              {categoryLabels[issue.category]}
            </span>
          {/each}
          {#if getDocumentReviewInfo(doc).status !== "pending"}
            <span
              class="status-badge"
              style="background-color: {statusColors[getDocumentReviewInfo(doc).status as ReviewStatus]}"
            >
              {statusLabels[getDocumentReviewInfo(doc).status as ReviewStatus]}
            </span>
          {/if}
        </div>
      {/each}
    {/if}
  </div>

  {#if showReviewPanel && selectedDoc}
    <div class="review-panel-overlay" onclick={closeReviewPanel}></div>
    <div class="review-panel">
      <div class="panel-header">
        <h4>{_("复核文档")}</h4>
        <button class="close-btn" onclick={closeReviewPanel}>×</button>
      </div>

      <div class="panel-content">
        <div class="doc-details">
          <p><strong>{_("日期")}:</strong> {selectedDoc.date}</p>
          <p><strong>{_("文件名")}:</strong> {name(selectedDoc)}</p>
          <p><strong>{_("账户")}:</strong> {selectedDoc.account}</p>
          <p><strong>{_("完整路径")}:</strong> {selectedDoc.filename}</p>
        </div>

        <div class="issues-section">
          <h5>{_("检测到的问题")}:</h5>
          <ul class="issues-list">
            {#each getDocumentReviewInfo(selectedDoc).issues as issue}
              <li class="issue-item">
                <span class="issue-icon">⚠️</span>
                <div>
                  <strong>{categoryLabels[issue.category]}</strong>
                  <p>{issue.description}</p>
                  {#if issue.details}
                    <p class="issue-details">{issue.details}</p>
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        </div>

        {#if getDocumentReviewInfo(selectedDoc).status !== "pending"}
          <div class="current-status">
            <strong>{_("当前状态")}:</strong>
            <span
              class="status-badge"
              style="background-color: {statusColors[getDocumentReviewInfo(selectedDoc).status as ReviewStatus]}"
            >
              {statusLabels[getDocumentReviewInfo(selectedDoc).status as ReviewStatus]}
            </span>
            {#if getDocumentReviewInfo(selectedDoc).reviewed_at}
              <p class="review-time">
                {_("复核时间")}: {new Date(getDocumentReviewInfo(selectedDoc).reviewed_at!).toLocaleString()}
              </p>
            {/if}
            {#if getDocumentReviewInfo(selectedDoc).notes}
              <p class="review-notes">
                {_("备注")}: {getDocumentReviewInfo(selectedDoc).notes}
              </p>
            {/if}
          </div>
        {/if}

        <div class="review-form">
          <label for="review-notes">{_("复核备注")}:</label>
          <textarea
            id="review-notes"
            bind:value={reviewNotes}
            placeholder={_("请输入复核备注（可选）...")}
            rows={3}
          />
        </div>

        <div class="review-actions">
          <button class="btn-approve" onclick={approve} disabled={$reviewStore.isLoading}>
            ✓ {_("通过")}
          </button>
          <button class="btn-reject" onclick={reject} disabled={$reviewStore.isLoading}>
            ✗ {_("拒绝")}
          </button>
          {#if getDocumentReviewInfo(selectedDoc).status !== "pending"}
            <button class="btn-clear" onclick={clearStatus} disabled={$reviewStore.isLoading}>
              ↺ {_("清除状态")}
            </button>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .review-queue {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    padding: 16px;
    border-bottom: 1px solid var(--sidebar-border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .header h3 {
    margin: 0;
    font-size: 16px;
  }

  .pending-count {
    font-size: 12px;
    color: var(--dim-text);
  }

  .category-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--sidebar-border);
  }

  .tab {
    padding: 4px 8px;
    border: 1px solid var(--sidebar-border);
    background: var(--input-background);
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .tab:hover {
    background: var(--table-header-background);
  }

  .tab.active {
    background: var(--selected-background);
    border-color: var(--selected-border);
  }

  .count {
    background: var(--tag-background);
    padding: 1px 6px;
    border-radius: 10px;
    font-size: 11px;
  }

  .document-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .empty-state {
    text-align: center;
    padding: 32px 16px;
    color: var(--dim-text);
  }

  .document-item {
    padding: 12px;
    border: 1px solid transparent;
    border-radius: 6px;
    cursor: pointer;
    margin-bottom: 8px;
    background: var(--entry-background);
  }

  .document-item:hover {
    background: var(--table-header-background);
  }

  .document-item.selected {
    border-color: var(--selected-border);
    background: var(--selected-background);
  }

  .doc-info {
    margin-bottom: 8px;
  }

  .doc-date {
    font-size: 12px;
    color: var(--dim-text);
  }

  .doc-name {
    font-weight: 500;
    font-size: 14px;
    margin: 2px 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .doc-account {
    font-size: 12px;
    color: var(--dim-text);
  }

  .issue-badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    margin-right: 4px;
    margin-bottom: 4px;
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

  .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    color: white;
    margin-right: 4px;
  }

  .review-panel-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 100;
  }

  .review-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: var(--entry-background);
    border-radius: 8px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    z-index: 101;
    width: 500px;
    max-width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
  }

  .panel-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--sidebar-border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .panel-header h4 {
    margin: 0;
  }

  .close-btn {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    padding: 0;
    line-height: 1;
  }

  .panel-content {
    padding: 20px;
  }

  .doc-details {
    margin-bottom: 20px;
  }

  .doc-details p {
    margin: 4px 0;
    font-size: 14px;
  }

  .issues-section {
    margin-bottom: 20px;
  }

  .issues-section h5 {
    margin: 0 0 12px 0;
  }

  .issues-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .issue-item {
    display: flex;
    gap: 12px;
    padding: 12px;
    background: var(--table-header-background);
    border-radius: 6px;
    margin-bottom: 8px;
  }

  .issue-icon {
    font-size: 18px;
  }

  .issue-item p {
    margin: 2px 0;
    font-size: 13px;
  }

  .issue-details {
    color: var(--dim-text);
    font-size: 12px;
  }

  .current-status {
    margin-bottom: 20px;
    padding: 12px;
    background: var(--table-header-background);
    border-radius: 6px;
  }

  .review-time,
  .review-notes {
    margin: 8px 0 0 0;
    font-size: 12px;
    color: var(--dim-text);
  }

  .review-form {
    margin-bottom: 20px;
  }

  .review-form label {
    display: block;
    margin-bottom: 6px;
    font-weight: 500;
  }

  .review-form textarea {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--sidebar-border);
    border-radius: 4px;
    background: var(--input-background);
    font-family: inherit;
    resize: vertical;
  }

  .review-actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
  }

  .review-actions button {
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    border: none;
    font-weight: 500;
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
