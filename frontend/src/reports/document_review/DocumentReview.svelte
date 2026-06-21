<script lang="ts">
  import { _ } from "../../i18n.ts";
  import { urlForAccount } from "../../helpers.ts";
  import { basename } from "../../lib/paths.ts";
  import DocumentPreview from "../documents/DocumentPreview.svelte";
  import type { DocumentReviewReportProps } from "./index.ts";

  let { review }: DocumentReviewReportProps = $props();

  type ProblemCategory =
    | "missing_narration"
    | "duplicate_names"
    | "size_anomalies"
    | "multiple_references";

  let activeCategory: ProblemCategory = $state("missing_narration");
  let selectedDoc: any = $state(null);

  const categories: { key: ProblemCategory; label: string; icon: string }[] = [
    { key: "missing_narration", label: _("缺少备注"), icon: "📝" },
    { key: "duplicate_names", label: _("命名重复"), icon: "📋" },
    { key: "size_anomalies", label: _("大小异常"), icon: "📏" },
    { key: "multiple_references", label: _("多次引用"), icon: "🔗" },
  ];

  function getProblemList(key: ProblemCategory) {
    switch (key) {
      case "missing_narration":
        return review.missing_narration;
      case "duplicate_names":
        return review.duplicate_names;
      case "size_anomalies":
        return review.size_anomalies;
      case "multiple_references":
        return review.multiple_references;
    }
  }

  function docName(doc: any) {
    const base = basename(doc.filename);
    return base.startsWith(doc.date) ? base.substring(11) : base;
  }

  let currentList = $derived(getProblemList(activeCategory));
</script>

<div class="document-review">
  <div class="summary-cards">
    <div class="summary-card total">
      <div class="card-icon">📄</div>
      <div class="card-content">
        <div class="card-value">{review.total_documents}</div>
        <div class="card-label">{_("总附件数")}</div>
      </div>
    </div>
    <div class="summary-card problems">
      <div class="card-icon">⚠️</div>
      <div class="card-content">
        <div class="card-value">{review.total_problems}</div>
        <div class="card-label">{_("问题总数")}</div>
      </div>
    </div>
  </div>

  <div class="category-tabs">
    {#each categories as cat (cat.key)}
      <button
        class="tab-button"
        class:active={activeCategory === cat.key}
        onclick={() => {
          activeCategory = cat.key;
          selectedDoc = null;
        }}
      >
        <span class="tab-icon">{cat.icon}</span>
        <span class="tab-label">{cat.label}</span>
        <span class="tab-count">{getProblemList(cat.key).length}</span>
      </button>
    {/each}
  </div>

  <div class="content-wrapper">
    <div class="problem-list">
      {#if currentList.length === 0}
        <div class="empty-state">
          <div class="empty-icon">✅</div>
          <p>{_("该类别暂无问题附件")}</p>
        </div>
      {:else}
        <table class="problem-table">
        <thead>
          <tr>
            <th>{_("日期")}</th>
            <th>{_("附件名称")}</th>
            <th>{_("所属账户")}</th>
            <th>{_("问题描述")}</th>
          </tr>
        </thead>
        <tbody>
          {#each currentList as item (item.document.entry_hash)}
            <tr
              class="problem-row"
              class:selected={selectedDoc?.entry_hash === item.document.entry_hash}
              title={item.document.filename}
              onclick={() => {
                selectedDoc = item.document;
              }}
            >
              <td class="doc-date">{item.document.date}</td>
              <td class="doc-name">
                <span class="doc-name-text">{docName(item.document)}</span>
              </td>
              <td class="doc-account">
                <a href={$urlForAccount(item.document.account)} class="account-link"
                  onclick={(e) => e.stopPropagation()}>
                  {item.document.account}
                </a>
              </td>
              <td class="problem-detail">
                <span class="problem-badge">{item.problem_detail}</span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      {/if}
    </div>

    {#if selectedDoc}
      <div class="preview-panel">
        <div class="preview-header">
          <h3 class="preview-title">{docName(selectedDoc)}</h3>
          <button
            class="preview-close"
            onclick={() => {
              selectedDoc = null;
            }}
          >
            ×
          </button>
        </div>
        <div class="preview-content">
          <DocumentPreview filename={selectedDoc.filename} />
        </div>
        <div class="preview-info">
          <div class="info-row">
            <span class="info-label">{_("账户")}:</span>
            <a href={$urlForAccount(selectedDoc.account)} class="info-value">
              {selectedDoc.account}
            </a>
          </div>
          <div class="info-row">
            <span class="info-label">{_("日期")}:</span>
            <span class="info-value">{selectedDoc.date}</span>
          </div>
          <div class="info-row">
            <span class="info-label">{_("文件")}:</span>
            <span class="info-value file-path" title={selectedDoc.filename}>
              {basename(selectedDoc.filename)}
            </span>
          </div>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .document-review {
    padding: 1rem;
    max-width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
  }

  .summary-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .summary-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.25rem;
    background: var(--table-header-background);
    border-radius: 8px;
    border: 1px solid var(--sidebar-border);
  }

  .summary-card.total .card-icon {
    font-size: 2rem;
  }

  .summary-card.problems {
    border-left: 2px solid var(--error-color, #e74c3c);
  }

  .card-value {
    font-size: 1.75rem;
    font-weight: 600;
    line-height: 1;
  }

  .card-label {
    font-size: 0.875rem;
    color: var(--muted-text-color);
    margin-top: 0.25rem;
  }

  .category-tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--sidebar-border);
    overflow-x: auto;
  }

  .tab-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.875rem;
    white-space: nowrap;
    transition: all 0.2s;
  }

  .tab-button:hover {
    background: var(--table-header-background);
  }

  .tab-button.active {
    border-bottom-color: var(--accent-color, #3498db);
    color: var(--accent-color, #3498db);
  }

  .tab-icon {
    font-size: 1rem;
  }

  .tab-count {
    background: var(--sidebar-border);
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .tab-button.active .tab-count {
    background: var(--accent-color, #3498db);
    color: white;
  }

  .content-wrapper {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
    flex: 1;
    min-height: 0;
  }

  .content-wrapper:has(.preview-panel) {
    grid-template-columns: 1fr 1fr;
  }

  .problem-list {
    background: var(--table-header-background);
    border: 1px solid var(--sidebar-border);
    border-radius: 8px;
    overflow: auto;
    min-height: 0;
  }

  .problem-table {
    width: 100%;
    border-collapse: collapse;
  }

  .problem-table th,
  .problem-table td {
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--sidebar-border);
  }

  .problem-table th {
    font-weight: 600;
    font-size: 0.8125rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted-text-color);
    background: var(--background);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .problem-row {
    cursor: pointer;
    transition: background 0.15s;
  }

  .problem-row:hover {
    background: var(--background);
  }

  .problem-row.selected {
    background: var(--background);
    border-left: 3px solid var(--accent-color, #3498db);
  }

  .doc-name {
    font-weight: 500;
  }

  .doc-account {
    color: var(--muted-text-color);
    font-size: 0.875rem;
  }

  .account-link {
    color: inherit;
    text-decoration: none;
  }

  .account-link:hover {
    color: var(--accent-color, #3498db);
    text-decoration: underline;
  }

  .problem-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    background: var(--warning-background, #fef3c7);
    color: var(--warning-color, #92400e);
    border-radius: 9999px;
    font-size: 0.8125rem;
    font-weight: 500;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--muted-text-color);
  }

  .empty-icon {
    font-size: 3rem;
    margin-bottom: 0.5rem;
  }

  .empty-state p {
    margin: 0;
    font-size: 1rem;
  }

  .preview-panel {
    display: flex;
    flex-direction: column;
    background: var(--table-header-background);
    border: 1px solid var(--sidebar-border);
    border-radius: 8px;
    overflow: hidden;
  }

  .preview-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--sidebar-border);
    background: var(--background);
  }

  .preview-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .preview-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--muted-text-color);
    padding: 0 0.5rem;
    line-height: 1;
  }

  .preview-close:hover {
    color: var(--text-color);
  }

  .preview-content {
    flex: 1;
    min-height: 300px;
    overflow: auto;
    background: var(--background);
  }

  .preview-info {
    padding: 1rem;
    border-top: 1px solid var(--sidebar-border);
    font-size: 0.875rem;
  }

  .info-row {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .info-row:last-child {
    margin-bottom: 0;
  }

  .info-label {
    font-weight: 500;
    color: var(--muted-text-color);
    min-width: 60px;
  }

  .info-value {
    flex: 1;
    word-break: break-all;
  }

  a.info-value {
    color: inherit;
    text-decoration: none;
  }

  a.info-value:hover {
    color: var(--accent-color, #3498db);
    text-decoration: underline;
  }

  .file-path {
    font-family: monospace;
    font-size: 0.8125rem;
  }

  @media (max-width: 768px) {
    .content-wrapper:has(.preview-panel) {
      grid-template-columns: 1fr;
    }

    .preview-content {
      min-height: 200px;
    }
  }
</style>
