<script lang="ts">
  import { _ } from "../../i18n.ts";
  import { urlForAccount, urlForRaw } from "../../helpers.ts";
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
  let selectedItem: any = $state(null);
  let expandedReferences: Set<string> = $state(new Set());
  let showStatsDetail: boolean = $state(false);

  const DEFAULT_VISIBLE_REFS = 5;

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

  let groups = $derived.by(() => {
    if (activeCategory === "size_anomalies") {
      const criterionGroups = new Map<string, { label: string; items: any[] }>();
      for (const item of currentList) {
        const c = item.size_context?.criterion ?? "unknown";
        if (!criterionGroups.has(c)) {
          const labels: Record<string, string> = {
            absolute_zero: _("空文件"),
            absolute_min: _("绝对值过小"),
            absolute_max: _("绝对值过大"),
            relative_median_low: _("相对中位数偏小"),
            relative_median_high: _("相对中位数偏大"),
            unknown: _("其他"),
          };
          criterionGroups.set(c, { label: labels[c] ?? c, items: [] });
        }
        criterionGroups.get(c)!.items.push(item);
      }
      return [...criterionGroups.entries()].map(([key, val]) => ({
        key,
        label: val.label,
        items: val.items,
      }));
    }
    if (activeCategory === "missing_narration") {
      return [{ key: "all", label: _("所有缺少备注的附件"), items: currentList }];
    }
    if (activeCategory === "duplicate_names") {
      const nameGroups = new Map<string, any[]>();
      for (const item of currentList) {
        const name = basename(item.document.filename);
        if (!nameGroups.has(name)) {
          nameGroups.set(name, []);
        }
        nameGroups.get(name)!.push(item);
      }
      return [...nameGroups.entries()].map(([name, items]) => ({
        key: name,
        label: name,
        items,
      }));
    }
    if (activeCategory === "multiple_references") {
      return [{ key: "all", label: _("引用次数超过一次的附件"), items: currentList }];
    }
    return [{ key: "all", label: "", items: currentList }];
  });

  function criterionBadgeClass(criterion: string) {
    if (criterion.startsWith("absolute")) return "badge-absolute";
    if (criterion.startsWith("relative")) return "badge-relative";
    return "badge-unknown";
  }

  function formatSize(sizeKb: number) {
    if (sizeKb >= 1024) return `${(sizeKb / 1024).toFixed(1)} MB`;
    if (sizeKb >= 1) return `${sizeKb.toFixed(1)} KB`;
    return `${Math.round(sizeKb * 1024)} B`;
  }

  function selectItem(item: any) {
    selectedItem = item;
    selectedDoc = item.document;
  }

  function toggleReferences(docHash: string) {
    if (expandedReferences.has(docHash)) {
      expandedReferences.delete(docHash);
    } else {
      expandedReferences.add(docHash);
    }
    expandedReferences = new Set(expandedReferences);
  }

  function isExpanded(docHash: string) {
    return expandedReferences.has(docHash);
  }

  function getVisibleReferences(refs: any[], docHash: string) {
    if (isExpanded(docHash) || refs.length <= DEFAULT_VISIBLE_REFS) {
      return refs;
    }
    return refs.slice(0, DEFAULT_VISIBLE_REFS);
  }

  function hasMoreReferences(refs: any[], docHash: string) {
    return refs.length > DEFAULT_VISIBLE_REFS && !isExpanded(docHash);
  }
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
    <button
      type="button"
      class="summary-card references"
      onclick={() => { showStatsDetail = !showStatsDetail; }}
    >
      <div class="card-icon">🔗</div>
      <div class="card-content">
        <div class="card-value">{review.reference_stats.total_references}</div>
        <div class="card-label">{_("引用总数")} ({review.reference_stats.total_documents_referenced} 个附件)</div>
      </div>
    </button>
  </div>

  {#if showStatsDetail}
    <div class="stats-panel">
      <div class="stats-section">
        <div class="stats-title">{_("引用统计")}</div>
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">{_("metadata 键")}:</span>
            <span class="stat-value">{review.reference_stats.metadata_keys_found.join(", ") || "-"}</span>
          </div>
          {#if review.reference_stats.top_referenced.length > 0}
            <div class="stat-item full-width">
              <span class="stat-label">{_("Top 5 被引用附件")}:</span>
              <ul class="top-refs-list">
                {#each review.reference_stats.top_referenced as item (item[0])}
                  <li>
                    <span class="truncate" title={String(item[0])}>{basename(String(item[0]))}</span>
                    <span class="ref-count">{item[1]} 次</span>
                  </li>
                {/each}
              </ul>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <div class="category-tabs">
    {#each categories as cat (cat.key)}
      <button
        class="tab-button"
        class:active={activeCategory === cat.key}
        onclick={() => {
          activeCategory = cat.key;
          selectedDoc = null;
          selectedItem = null;
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
        {#each groups as group (group.key)}
          <div class="group-section">
            <div class="group-header">
              <span class="group-label">{group.label}</span>
              <span class="group-count">{group.items.length}</span>
            </div>
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
                {#each group.items as item (item.document.entry_hash)}
                  <tr
                    class="problem-row"
                    class:selected={selectedDoc?.entry_hash === item.document.entry_hash}
                    title={item.document.filename}
                    onclick={() => selectItem(item)}
                  >
                    <td class="doc-date">{item.document.date}</td>
                    <td class="doc-name">{docName(item.document)}</td>
                    <td class="doc-account">
                      <a href={$urlForAccount(item.document.account)} class="account-link"
                        onclick={(e) => e.stopPropagation()}>
                        {item.document.account}
                      </a>
                    </td>
                    <td class="problem-detail">
                      <span class="problem-badge {criterionBadgeClass(item.size_context?.criterion ?? '')}">
                        {item.problem_detail}
                      </span>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/each}
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
              selectedItem = null;
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

          {#if selectedItem?.size_context}
            <div class="info-divider"></div>
            <div class="info-row">
              <span class="info-label">{_("文件大小")}:</span>
              <span class="info-value">{formatSize(selectedItem.size_context.size_kb)}</span>
            </div>
            {#if selectedItem.size_context.median_size_kb != null}
              <div class="info-row">
                <span class="info-label">{_("群体中位数")}:</span>
                <span class="info-value">{formatSize(selectedItem.size_context.median_size_kb)}</span>
              </div>
            {/if}
            <div class="info-row">
              <span class="info-label">{_("判定标准")}:</span>
              <span class="info-value criterion-tag {criterionBadgeClass(selectedItem.size_context.criterion)}">
                {#if selectedItem.size_context.criterion === "absolute_zero"}
                  {_("绝对阈值: 0 字节")}
                {:else if selectedItem.size_context.criterion === "absolute_min"}
                  {"绝对阈值: < "}{selectedItem.size_context.min_threshold_kb}{" KB"}
                {:else if selectedItem.size_context.criterion === "absolute_max"}
                  {"绝对阈值: > "}{Math.round(selectedItem.size_context.max_threshold_kb / 1024)}{" MB"}
                {:else if selectedItem.size_context.criterion === "relative_median_low"}
                  {"相对中位数: < "}{selectedItem.size_context.median_ratio_low_pct}{"%"}
                {:else if selectedItem.size_context.criterion === "relative_median_high"}
                  {"相对中位数: > "}{(selectedItem.size_context.median_ratio_high_pct / 100).toFixed(0)}{"x"}
                {:else}
                  {selectedItem.size_context.criterion}
                {/if}
              </span>
            </div>
          {/if}

          {#if selectedItem?.reference_sources?.length > 0}
            <div class="info-divider"></div>
            <div class="references-header">
              <span class="info-label">{_("引用来源")} ({selectedItem.reference_sources.length})</span>
              {#if hasMoreReferences(selectedItem.reference_sources, selectedDoc.entry_hash)}
                <button
                  class="expand-btn"
                  onclick={() => toggleReferences(selectedDoc.entry_hash)}
                >
                  {_("展开全部")}
                </button>
              {:else if selectedItem.reference_sources.length > DEFAULT_VISIBLE_REFS && isExpanded(selectedDoc.entry_hash)}
                <button
                  class="expand-btn"
                  onclick={() => toggleReferences(selectedDoc.entry_hash)}
                >
                  {_("收起")}
                </button>
              {/if}
            </div>
            <div class="reference-list">
              {#each getVisibleReferences(selectedItem.reference_sources, selectedDoc.entry_hash) as ref (ref.entry_hash)}
                <div class="reference-item">
                  <span class="ref-type">{ref.entry_type}</span>
                  <span class="ref-date">{ref.date}</span>
                  <a href={$urlForRaw(`/${ref.entry_hash}`)} class="ref-link" title={ref.query_path}>🔗</a>
                  {#if ref.account}
                    <a href={$urlForAccount(ref.account)} class="ref-account">{ref.account}</a>
                  {/if}
                  {#if ref.payee}
                    <span class="ref-payee">{ref.payee}</span>
                  {/if}
                  {#if ref.narration}
                    <span class="ref-narration">{ref.narration}</span>
                  {/if}
                </div>
              {/each}
              {#if hasMoreReferences(selectedItem.reference_sources, selectedDoc.entry_hash)}
                <div class="reference-more">
                  <button
                    class="more-btn"
                    onclick={() => toggleReferences(selectedDoc.entry_hash)}
                  >
                    {"还有 "}{selectedItem.reference_sources.length - DEFAULT_VISIBLE_REFS}{" 条引用，点击展开"}
                  </button>
                </div>
              {/if}
            </div>
          {/if}
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
    margin-bottom: 1rem;
  }

  .summary-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.25rem;
    background: var(--table-header-background);
    border-radius: 8px;
    border: 1px solid var(--sidebar-border);
    cursor: default;
  }

  .summary-card.references {
    cursor: pointer;
    transition: all 0.2s;
  }

  .summary-card.references:hover {
    border-color: var(--accent-color, #3498db);
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

  .stats-panel {
    background: var(--table-header-background);
    border: 1px solid var(--sidebar-border);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .stats-title {
    font-weight: 600;
    margin-bottom: 0.75rem;
    font-size: 0.9375rem;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }

  .stat-item {
    display: flex;
    gap: 0.5rem;
    font-size: 0.875rem;
  }

  .stat-item.full-width {
    grid-column: 1 / -1;
    flex-direction: column;
    gap: 0.25rem;
  }

  .stat-label {
    font-weight: 500;
    color: var(--muted-text-color);
    min-width: 80px;
  }

  .stat-value {
    flex: 1;
    word-break: break-all;
  }

  .top-refs-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .top-refs-list li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.25rem 0.5rem;
    background: var(--background);
    border-radius: 4px;
    font-size: 0.8125rem;
  }

  .ref-count {
    font-weight: 600;
    color: var(--accent-color, #3498db);
  }

  .truncate {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 300px;
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

  .group-section {
    border-bottom: 1px solid var(--sidebar-border);
  }

  .group-section:last-child {
    border-bottom: none;
  }

  .group-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: var(--background);
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--muted-text-color);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .group-count {
    background: var(--sidebar-border);
    padding: 0.0625rem 0.375rem;
    border-radius: 9999px;
    font-size: 0.6875rem;
    font-weight: 600;
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
    border-radius: 9999px;
    font-size: 0.8125rem;
    font-weight: 500;
    background: var(--warning-background, #fef3c7);
    color: var(--warning-color, #92400e);
  }

  .badge-absolute {
    background: #fee2e2;
    color: #991b1b;
  }

  .badge-relative {
    background: #fef3c7;
    color: #92400e;
  }

  .badge-unknown {
    background: var(--sidebar-border);
    color: var(--muted-text-color);
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
    min-height: 250px;
    overflow: auto;
    background: var(--background);
  }

  .preview-info {
    padding: 1rem;
    border-top: 1px solid var(--sidebar-border);
    font-size: 0.875rem;
    overflow-y: auto;
    max-height: 45%;
  }

  .info-divider {
    border-top: 1px dashed var(--sidebar-border);
    margin: 0.75rem 0;
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
    min-width: 80px;
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

  .criterion-tag {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .criterion-tag.badge-absolute {
    background: #fee2e2;
    color: #991b1b;
  }

  .criterion-tag.badge-relative {
    background: #fef3c7;
    color: #92400e;
  }

  .references-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .expand-btn {
    background: none;
    border: 1px solid var(--sidebar-border);
    border-radius: 4px;
    padding: 0.125rem 0.5rem;
    font-size: 0.75rem;
    cursor: pointer;
    color: var(--muted-text-color);
    transition: all 0.2s;
  }

  .expand-btn:hover {
    border-color: var(--accent-color, #3498db);
    color: var(--accent-color, #3498db);
  }

  .reference-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .reference-item {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    align-items: baseline;
    padding: 0.375rem 0.5rem;
    background: var(--background);
    border-radius: 4px;
    font-size: 0.8125rem;
  }

  .ref-type {
    background: var(--sidebar-border);
    padding: 0.0625rem 0.375rem;
    border-radius: 3px;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
  }

  .ref-date {
    color: var(--muted-text-color);
    font-size: 0.75rem;
  }

  .ref-link {
    color: var(--accent-color, #3498db);
    text-decoration: none;
    font-size: 0.8125rem;
  }

  .ref-link:hover {
    text-decoration: underline;
  }

  .ref-account {
    color: inherit;
    text-decoration: none;
    font-size: 0.8125rem;
  }

  .ref-account:hover {
    color: var(--accent-color, #3498db);
    text-decoration: underline;
  }

  .ref-payee {
    font-weight: 500;
  }

  .ref-narration {
    color: var(--muted-text-color);
    font-style: italic;
  }

  .reference-more {
    margin-top: 0.5rem;
  }

  .more-btn {
    width: 100%;
    padding: 0.5rem;
    background: var(--background);
    border: 1px dashed var(--sidebar-border);
    border-radius: 4px;
    color: var(--muted-text-color);
    font-size: 0.8125rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .more-btn:hover {
    border-color: var(--accent-color, #3498db);
    color: var(--accent-color, #3498db);
  }

  @media (max-width: 768px) {
    .content-wrapper:has(.preview-panel) {
      grid-template-columns: 1fr;
    }

    .preview-content {
      min-height: 200px;
    }

    .stats-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
