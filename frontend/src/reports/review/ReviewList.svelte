<script lang="ts">
  import { onMount } from "svelte";

  import { urlForAccount, urlForSource } from "../../helpers.ts";
  import { _, format } from "../../i18n.ts";
  import { router } from "../../router.ts";
  import { accounts, base_url } from "../../stores/index.ts";
  import {
    enriched_errors,
    review_context_stack,
    review_stats,
    review_store,
    urlForReviewDetail,
  } from "../../stores/review.ts";

  type FilterStatus = "all" | "pending" | "skipped" | "explained";

  let filterStatus = $state<FilterStatus>("all");
  let filterType = $state<string>("all");
  let searchText = $state<string>("");

  let selectedIds = $state<Set<string>>(new Set());
  let batchExplanation = $state<string>("");
  let showBatchExplain = $state<boolean>(false);
  let batchNote = $state<string>("");
  let showBatchNote = $state<boolean>(false);

  let highlightId = $state<string | null>(null);
  let tableContainer: HTMLElement | undefined = $state();

  let account_re = $derived(new RegExp(`(${$accounts.join("|")})`));

  function extract_accounts(msg: string): ["text" | "account", string][] {
    return msg
      .split(account_re)
      .map((text, index) =>
        index % 2 === 0 ? ["text", text] : ["account", text],
      );
  }

  const error_types = $derived(
    Array.from(new Set($enriched_errors.map((e) => e.error.type))).sort(),
  );

  const filtered = $derived(
    $enriched_errors.filter((item) => {
      if (filterStatus !== "all" && item.state.status !== filterStatus) {
        return false;
      }
      if (filterType !== "all" && item.error.type !== filterType) {
        return false;
      }
      if (searchText) {
        const hay = (item.error.message + item.error.type + (item.state.note || "") + (item.state.explanation || "")).toLowerCase();
        if (!hay.includes(searchText.toLowerCase())) {
          return false;
        }
      }
      return true;
    }),
  );

  const filteredIds = $derived(new Set(filtered.map((i) => i.id)));

  const allFilteredSelected = $derived(
    filtered.length > 0 && filtered.every((i) => selectedIds.has(i.id)),
  );

  const selectedCount = $derived(
    [...selectedIds].filter((id) => filteredIds.has(id)).length,
  );

  function statusLabel(status: string): string {
    switch (status) {
      case "pending":
        return _("待处理");
      case "skipped":
        return _("已跳过");
      case "explained":
        return _("已解释");
      default:
        return status;
    }
  }

  function statusClass(status: string): string {
    switch (status) {
      case "pending":
        return "status-pending";
      case "skipped":
        return "status-skipped";
      case "explained":
        return "status-explained";
      default:
        return "";
    }
  }

  function goDetail(id: string): void {
    review_context_stack.push({
      highlightId: id,
      scrollTop: tableContainer?.scrollTop ?? 0,
      filterStatus,
      filterType,
      searchText,
    });
    router.navigate($base_url + urlForReviewDetail(id));
  }

  function handleSkip(id: string, ev: Event): void {
    ev.stopPropagation();
    review_store.skip(id);
  }

  function handleReset(id: string, ev: Event): void {
    ev.stopPropagation();
    review_store.reset(id);
  }

  function toggleSelect(id: string, ev: Event): void {
    ev.stopPropagation();
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    selectedIds = next;
  }

  function toggleSelectAll(): void {
    if (allFilteredSelected) {
      const next = new Set(selectedIds);
      for (const item of filtered) {
        next.delete(item.id);
      }
      selectedIds = next;
    } else {
      const next = new Set(selectedIds);
      for (const item of filtered) {
        next.add(item.id);
      }
      selectedIds = next;
    }
  }

  function getSelectedIds(): string[] {
    return [...selectedIds].filter((id) => filteredIds.has(id));
  }

  function handleBatchSkip(): void {
    const ids = getSelectedIds();
    if (ids.length === 0) return;
    review_store.batchSkip(ids);
    selectedIds = new Set();
  }

  function handleBatchExplain(): void {
    const ids = getSelectedIds();
    if (ids.length === 0) return;
    review_store.batchExplain(ids, batchExplanation);
    batchExplanation = "";
    showBatchExplain = false;
    selectedIds = new Set();
  }

  function handleBatchNote(): void {
    const ids = getSelectedIds();
    if (ids.length === 0) return;
    review_store.batchNote(ids, batchNote);
    batchNote = "";
    showBatchNote = false;
    selectedIds = new Set();
  }

  function handleBatchReset(): void {
    const ids = getSelectedIds();
    if (ids.length === 0) return;
    review_store.batchReset(ids);
    selectedIds = new Set();
  }

  onMount(() => {
    review_context_stack.markHistoryList();
    let ctx:
      | {
          highlightId: string | null;
          scrollTop: number;
          filterStatus: string;
          filterType: string;
          searchText: string;
        }
      | undefined = review_context_stack.takePendingRestore();
    if (!ctx) {
      ctx = review_context_stack.pop();
    }
    if (ctx) {
      if (ctx.filterStatus && ctx.filterStatus !== "all") {
        filterStatus = ctx.filterStatus as FilterStatus;
      }
      if (ctx.filterType && ctx.filterType !== "all") {
        filterType = ctx.filterType;
      }
      if (ctx.searchText) {
        searchText = ctx.searchText;
      }
      if (ctx.highlightId) {
        highlightId = ctx.highlightId;
      }
      if (ctx.scrollTop > 0 && tableContainer) {
        requestAnimationFrame(() => {
          if (tableContainer) {
            tableContainer.scrollTop = ctx!.scrollTop;
          }
        });
      }
    }
  });

  $effect(() => {
    if (highlightId && tableContainer) {
      requestAnimationFrame(() => {
        const row = tableContainer?.querySelector(`[data-row-id="${CSS.escape(highlightId!)}"]`);
        if (row) {
          row.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      });
    }
  });

  function saveContext(): void {
    review_context_stack.replaceTop({
      highlightId,
      scrollTop: tableContainer?.scrollTop ?? 0,
      filterStatus,
      filterType,
      searchText,
    });
  }

  $effect(() => {
    if ($review_context_stack.length > 0) {
      saveContext();
    }
  });
</script>

<div class="review-desk">
  <div class="review-header">
    <h2>{_("复核台")}</h2>
    <div class="review-stats">
      <span class="stat stat-total">{format(_("总计 %(n)s 条"), { n: $review_stats.total.toString() })}</span>
      <span class="stat stat-pending">{format(_("待处理 %(n)s 条"), { n: $review_stats.pending.toString() })}</span>
      <span class="stat stat-skipped">{format(_("已跳过 %(n)s 条"), { n: $review_stats.skipped.toString() })}</span>
      <span class="stat stat-explained">{format(_("已解释 %(n)s 条"), { n: $review_stats.explained.toString() })}</span>
    </div>
  </div>

  <div class="review-filters">
    <div class="filter-group">
      <label>{_("状态筛选")}:</label>
      <select bind:value={filterStatus}>
        <option value="all">{_("全部")}</option>
        <option value="pending">{_("待处理")}</option>
        <option value="skipped">{_("已跳过")}</option>
        <option value="explained">{_("已解释")}</option>
      </select>
    </div>
    <div class="filter-group">
      <label>{_("异常类型")}:</label>
      <select bind:value={filterType}>
        <option value="all">{_("全部")}</option>
        {#each error_types as t (t)}
          <option value={t}>{t}</option>
        {/each}
      </select>
    </div>
    <div class="filter-group filter-search">
      <label>{_("搜索")}:</label>
      <input
        type="text"
        bind:value={searchText}
        placeholder={_("搜索消息、备注或解释...")}
      />
    </div>
  </div>

  {#if selectedCount > 0}
    <div class="batch-bar">
      <span class="batch-info">
        {format(_("已选中 %(n)s 条"), { n: selectedCount.toString() })}
      </span>
      <button type="button" class="btn btn-batch-skip" onclick={handleBatchSkip}>
        {_("批量跳过")}
      </button>
      <button
        type="button"
        class="btn btn-batch-explain"
        onclick={() => (showBatchExplain = !showBatchExplain)}
      >
        {_("批量解释")}
      </button>
      <button
        type="button"
        class="btn btn-batch-note"
        onclick={() => (showBatchNote = !showBatchNote)}
      >
        {_("批量备注")}
      </button>
      <button type="button" class="btn btn-batch-reset" onclick={handleBatchReset}>
        {_("批量重置")}
      </button>
      <button
        type="button"
        class="btn btn-batch-clear"
        onclick={() => (selectedIds = new Set())}
      >
        {_("取消选择")}
      </button>
    </div>
    {#if showBatchExplain}
      <div class="batch-row batch-explain-row">
        <textarea
          class="form-textarea"
          bind:value={batchExplanation}
          rows={3}
          placeholder={_("请输入批量解释说明...")}
        ></textarea>
        <button
          type="button"
          class="btn btn-primary"
          onclick={handleBatchExplain}
          disabled={!batchExplanation.trim()}
        >
          {_("确认解释")}
        </button>
      </div>
    {/if}
    {#if showBatchNote}
      <div class="batch-row batch-note-row">
        <textarea
          class="form-textarea"
          bind:value={batchNote}
          rows={3}
          placeholder={_("请输入批量备注内容...（不改变复核状态）")}
        ></textarea>
        <button
          type="button"
          class="btn btn-secondary"
          onclick={handleBatchNote}
          disabled={!batchNote.trim()}
        >
          {_("确认备注")}
        </button>
      </div>
    {/if}
  {/if}

  {#if filtered.length > 0}
    <div class="table-scroll" bind:this={tableContainer}>
      <table class="review-table">
        <thead>
          <tr>
            <th class="th-check">
              <input
                type="checkbox"
                checked={allFilteredSelected}
                onchange={toggleSelectAll}
              />
            </th>
            <th>{_("状态")}</th>
            <th>{_("类型")}</th>
            <th>{_("文件")}</th>
            <th>{_("行号")}</th>
            <th>{_("异常消息")}</th>
            <th>{_("备注")}</th>
            <th>{_("操作")}</th>
          </tr>
        </thead>
        <tbody>
          {#each filtered as item (item.id)}
            <tr
              data-row-id={item.id}
              class="review-row clickable {statusClass(item.state.status)} {highlightId === item.id ? 'highlighted' : ''}"
              onclick={() => goDetail(item.id)}
            >
              <td class="td-check" onclick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={selectedIds.has(item.id)}
                  onchange={(e: Event) => toggleSelect(item.id, e)}
                />
              </td>
              <td>
                <span class="badge {statusClass(item.state.status)}">
                  {statusLabel(item.state.status)}
                </span>
              </td>
              <td class="type-cell">{item.error.type}</td>
              {#if item.error.source}
                {@const url = $urlForSource(
                  item.error.source.filename,
                  item.error.source.lineno.toString(),
                )}
                {@const title = format(_("Show source %(file)s:%(lineno)s"), {
                  file: item.error.source.filename,
                  lineno: item.error.source.lineno.toString(),
                })}
                <td>{item.error.source.filename}</td>
                <td class="num">
                  <a
                    class="source"
                    href={url}
                    {title}
                    onclick={(e) => e.stopPropagation()}
                  >{item.error.source.lineno}</a>
                </td>
              {:else}
                <td></td>
                <td class="num"></td>
              {/if}
              <td class="pre msg-cell">
                {#each extract_accounts(item.error.message) as [type, text]}
                  {#if type === "text"}
                    {text}
                  {:else}
                    <a
                      href={$urlForAccount(text)}
                      onclick={(e) => e.stopPropagation()}
                    >{text}</a>
                  {/if}
                {/each}
              </td>
              <td class="note-cell">
                {#if item.state.note}
                  <span class="note-preview">{item.state.note}</span>
                {:else if item.state.explanation}
                  <span class="explanation-preview">[{_("已解释")}]</span>
                {:else}
                  <span class="empty-note">—</span>
                {/if}
              </td>
              <td class="actions-cell" onclick={(e) => e.stopPropagation()}>
                {#if item.state.status !== "skipped"}
                  <button
                    type="button"
                    class="btn btn-skip"
                    onclick={(e) => handleSkip(item.id, e)}
                    title={_("跳过此异常")}
                  >{_("跳过")}</button>
                {:else}
                  <button
                    type="button"
                    class="btn btn-reset"
                    onclick={(e) => handleReset(item.id, e)}
                    title={_("重置状态")}
                  >{_("重置")}</button>
                {/if}
                <button
                  type="button"
                  class="btn btn-detail"
                  onclick={() => goDetail(item.id)}
                  title={_("查看详情")}
                >{_("详情")}</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <p class="empty-state">
      {_("暂无匹配的异常记录。")}
    </p>
  {/if}
</div>

<style>
  .review-desk {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .review-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .review-header h2 {
    margin: 0;
  }

  .review-stats {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .stat {
    padding: 0.25rem 0.6rem;
    border-radius: 4px;
    font-size: 0.85rem;
    background: #f5f5f5;
  }

  .stat-pending {
    background: #fff3cd;
    color: #856404;
  }

  .stat-skipped {
    background: #e2e3e5;
    color: #383d41;
  }

  .stat-explained {
    background: #d4edda;
    color: #155724;
  }

  .review-filters {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    padding: 0.75rem;
    background: #fafafa;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
  }

  .filter-group {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .filter-group label {
    font-weight: 500;
    font-size: 0.85rem;
    white-space: nowrap;
  }

  .filter-group select,
  .filter-group input {
    padding: 0.3rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 3px;
    font-size: 0.85rem;
  }

  .filter-search input {
    min-width: 220px;
  }

  .batch-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 0.75rem;
    background: #e8f0fe;
    border: 1px solid #c5d9f0;
    border-radius: 4px;
    flex-wrap: wrap;
  }

  .batch-info {
    font-weight: 500;
    font-size: 0.85rem;
    margin-right: 0.5rem;
  }

  .batch-row {
    display: flex;
    gap: 0.75rem;
    align-items: flex-start;
    padding: 0.75rem;
    border: 1px solid;
    border-radius: 4px;
  }

  .batch-row .form-textarea {
    flex: 1;
    min-height: 60px;
  }

  .batch-explain-row {
    background: #f0fff0;
    border-color: #c3e6cb;
  }

  .batch-note-row {
    background: #fffbeb;
    border-color: #ffe0a1;
  }

  .form-textarea {
    box-sizing: border-box;
    padding: 0.5rem 0.7rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.85rem;
    font-family: inherit;
    resize: vertical;
  }

  .form-textarea:focus {
    outline: none;
    border-color: #007bff;
    box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.15);
  }

  .table-scroll {
    max-height: 70vh;
    overflow-y: auto;
  }

  .review-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }

  .review-table th,
  .review-table td {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid #e0e0e0;
    text-align: left;
    vertical-align: top;
  }

  .review-table th {
    background: #f5f5f5;
    font-weight: 600;
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .th-check,
  .td-check {
    width: 36px;
    text-align: center;
  }

  .review-row.clickable {
    cursor: pointer;
    transition: background 0.15s;
  }

  .review-row.clickable:hover {
    background: #f0f7ff;
  }

  .review-row.status-pending {
    border-left: 3px solid #ffc107;
  }

  .review-row.status-skipped {
    border-left: 3px solid #6c757d;
    opacity: 0.75;
  }

  .review-row.status-explained {
    border-left: 3px solid #28a745;
  }

  .review-row.highlighted {
    background: #fffde7 !important;
    box-shadow: inset 3px 0 0 #ff6f00;
  }

  .badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    font-size: 0.75rem;
    font-weight: 500;
    white-space: nowrap;
  }

  .badge.status-pending {
    background: #fff3cd;
    color: #856404;
  }

  .badge.status-skipped {
    background: #e2e3e5;
    color: #383d41;
  }

  .badge.status-explained {
    background: #d4edda;
    color: #155724;
  }

  .type-cell {
    font-family: monospace;
    font-size: 0.8rem;
    white-space: nowrap;
  }

  .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .msg-cell {
    max-width: 400px;
    word-wrap: break-word;
  }

  .note-cell {
    max-width: 180px;
  }

  .note-preview {
    display: inline-block;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-style: italic;
    color: #555;
  }

  .explanation-preview {
    color: #28a745;
    font-style: italic;
  }

  .empty-note {
    color: #aaa;
  }

  .actions-cell {
    white-space: nowrap;
  }

  .btn {
    display: inline-block;
    padding: 0.25rem 0.6rem;
    margin: 0 0.15rem;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #fff;
    cursor: pointer;
    font-size: 0.8rem;
    transition: all 0.15s;
  }

  .btn:hover:not(:disabled) {
    background: #f0f0f0;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-skip {
    border-color: #ffc107;
    color: #856404;
  }

  .btn-skip:hover:not(:disabled) {
    background: #fff3cd;
  }

  .btn-reset {
    border-color: #6c757d;
    color: #383d41;
  }

  .btn-reset:hover:not(:disabled) {
    background: #e2e3e5;
  }

  .btn-detail {
    border-color: #007bff;
    color: #007bff;
  }

  .btn-detail:hover:not(:disabled) {
    background: #cce5ff;
  }

  .btn-batch-skip {
    border-color: #ffc107;
    color: #856404;
  }

  .btn-batch-skip:hover:not(:disabled) {
    background: #fff3cd;
  }

  .btn-batch-explain {
    border-color: #28a745;
    color: #155724;
  }

  .btn-batch-explain:hover:not(:disabled) {
    background: #d4edda;
  }

  .btn-batch-note {
    border-color: #ffa726;
    color: #e65100;
  }

  .btn-batch-note:hover:not(:disabled) {
    background: #ffe0b2;
  }

  .btn-batch-reset {
    border-color: #6c757d;
    color: #383d41;
  }

  .btn-batch-reset:hover:not(:disabled) {
    background: #e2e3e5;
  }

  .btn-batch-clear {
    border-color: #dc3545;
    color: #dc3545;
  }

  .btn-batch-clear:hover:not(:disabled) {
    background: #f8d7da;
  }

  .btn-primary {
    border-color: #28a745;
    background: #28a745;
    color: #fff;
  }

  .btn-primary:hover:not(:disabled) {
    background: #218838;
    border-color: #218838;
  }

  .btn-secondary {
    border-color: #ffa726;
    background: #ffa726;
    color: #fff;
  }

  .btn-secondary:hover:not(:disabled) {
    background: #fb8c00;
    border-color: #fb8c00;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: #888;
    font-style: italic;
  }

  .pre {
    white-space: pre-wrap;
    word-wrap: break-word;
  }
</style>
