<script lang="ts">
  import { urlForAccount, urlForSource } from "../../helpers.ts";
  import { _, format } from "../../i18n.ts";
  import { router } from "../../router.ts";
  import {
    enriched_errors,
    review_context_stack,
    review_store,
    urlForReviewDetail,
    urlForReviewList,
  } from "../../stores/review.ts";
  import { accounts, base_url } from "../../stores/index.ts";

  export let id: string;

  let accounts_re = $derived(new RegExp(`(${$accounts.join("|")})`));

  function extract_accounts(msg: string): ["text" | "account", string][] {
    return msg
      .split(accounts_re)
      .map((text, index) =>
        index % 2 === 0 ? ["text", text] : ["account", text],
      );
  }

  const currentIndex = $derived(
    $enriched_errors.findIndex((e) => e.id === id),
  );

  const currentItem = $derived(
    currentIndex >= 0 ? $enriched_errors[currentIndex] : undefined,
  );

  const prevItem = $derived(
    currentIndex > 0 ? $enriched_errors[currentIndex - 1] : undefined,
  );

  const nextItem = $derived(
    currentIndex >= 0 && currentIndex < $enriched_errors.length - 1
      ? $enriched_errors[currentIndex + 1]
      : undefined,
  );

  let noteDraft = $derived.by(() => {
    const state = currentItem?.state;
    return state ? state.note : "";
  });

  let explanationDraft = $derived.by(() => {
    const state = currentItem?.state;
    return state ? state.explanation : "";
  });

  $effect(() => {
    if (currentItem) {
      noteDraft = currentItem.state.note;
      explanationDraft = currentItem.state.explanation;
    }
  });

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

  function goList(): void {
    // 更新栈顶 highlightId 为当前 ID，列表页面 pop 时会看到
    review_context_stack.update((stack) => {
      if (stack.length === 0) {
        return [
          {
            highlightId: id,
            scrollTop: 0,
            filterStatus: "all",
            filterType: "all",
            searchText: "",
          },
        ];
      }
      const next = [...stack];
      const top = { ...next[next.length - 1] };
      top.highlightId = id;
      next[next.length - 1] = top;
      return next;
    });
    router.navigate($base_url + urlForReviewList());
  }

  function goPrev(): void {
    if (prevItem) {
      // 切换详情：更新栈顶 highlightId，保持筛选/滚动位置不变
      review_context_stack.update((stack) => {
        if (stack.length === 0) return stack;
        const next = [...stack];
        const top = { ...next[next.length - 1] };
        top.highlightId = prevItem.id;
        next[next.length - 1] = top;
        return next;
      });
      router.navigate($base_url + urlForReviewDetail(prevItem.id));
    }
  }

  function goNext(): void {
    if (nextItem) {
      review_context_stack.update((stack) => {
        if (stack.length === 0) return stack;
        const next = [...stack];
        const top = { ...next[next.length - 1] };
        top.highlightId = nextItem.id;
        next[next.length - 1] = top;
        return next;
      });
      router.navigate($base_url + urlForReviewDetail(nextItem.id));
    }
  }

  function handleSkip(): void {
    if (currentItem) {
      review_store.skip(currentItem.id);
    }
  }

  function handleReset(): void {
    if (currentItem) {
      review_store.reset(currentItem.id);
    }
  }

  function handleSaveNote(): void {
    if (currentItem) {
      review_store.setNote(currentItem.id, noteDraft);
    }
  }

  function handleSaveExplanation(): void {
    if (currentItem) {
      review_store.explain(currentItem.id, explanationDraft);
    }
  }

  function formatDate(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  }
</script>

<div class="review-detail">
  <div class="detail-nav">
    <button type="button" class="btn btn-back" onclick={goList}>
      ← {_("返回列表")}
    </button>
    <div class="nav-arrows">
      <button
        type="button"
        class="btn btn-nav"
        onclick={goPrev}
        disabled={!prevItem}
        title={prevItem ? _("上一条") : _("没有上一条")}
      >
        ◀ {_("上一条")}
      </button>
      <span class="nav-counter">
        {currentIndex >= 0
          ? format(_("第 %(curr)s / %(total)s 条"), {
              curr: (currentIndex + 1).toString(),
              total: $enriched_errors.length.toString(),
            })
          : "- / -"}
      </span>
      <button
        type="button"
        class="btn btn-nav"
        onclick={goNext}
        disabled={!nextItem}
        title={nextItem ? _("下一条") : _("没有下一条")}
      >
        {_("下一条")} ▶
      </button>
    </div>
  </div>

  {#if currentItem}
    <div class="detail-body">
      <div class="detail-section detail-status">
        <h3>{_("复核状态")}</h3>
        <div class="status-row">
          <span class="badge large {statusClass(currentItem.state.status)}">
            {statusLabel(currentItem.state.status)}
          </span>
          <span class="updated-time">
            {format(_("最后更新: %(time)s"), {
              time: formatDate(currentItem.state.updated_at),
            })}
          </span>
        </div>
        <div class="status-actions">
          {#if currentItem.state.status !== "skipped"}
            <button
              type="button"
              class="btn btn-skip"
              onclick={handleSkip}
              title={_("标记此异常为已跳过")}
            >
              {_("跳过此异常")}
            </button>
          {/if}
          <button
            type="button"
            class="btn btn-reset"
            onclick={handleReset}
            title={_("重置复核状态")}
          >
            {_("重置状态")}
          </button>
        </div>
      </div>

      <div class="detail-section detail-info">
        <h3>{_("异常信息")}</h3>
        <dl class="info-dl">
          <dt>{_("异常类型")}:</dt>
          <dd class="type-value">{currentItem.error.type}</dd>

          <dt>{_("来源文件")}:</dt>
          <dd>
            {#if currentItem.error.source}
              <a
                href={$urlForSource(
                  currentItem.error.source.filename,
                  currentItem.error.source.lineno.toString(),
                )}
              >
                {currentItem.error.source.filename}:{currentItem.error.source.lineno}
              </a>
            {:else}
              <span class="na">—</span>
            {/if}
          </dd>

          {#if currentItem.error.entry_hash}
            <dt>{_("关联交易")}:</dt>
            <dd>
              <code>{currentItem.error.entry_hash}</code>
            </dd>
          {/if}

          <dt>{_("异常详情")}:</dt>
          <dd class="message-detail pre">
            {#each extract_accounts(currentItem.error.message) as [type, text]}
              {#if type === "text"}
                {text}
              {:else}
                <a href={$urlForAccount(text)}>{text}</a>
              {/if}
            {/each}
          </dd>
        </dl>
      </div>

      <div class="detail-section detail-explanation">
        <h3>{_("解释说明")}</h3>
        <p class="section-hint">
          {_("如果这条异常是合理的，请在此处记录解释原因。保存后状态将变为「已解释」。")}
        </p>
        <textarea
          class="form-textarea"
          bind:value={explanationDraft}
          rows={5}
          placeholder={_("请输入对此异常的解释说明...")}
        ></textarea>
        <div class="form-actions">
          <button
            type="button"
            class="btn btn-primary"
            onclick={handleSaveExplanation}
            disabled={!explanationDraft.trim()}
          >
            {_("保存解释")}
          </button>
          {#if currentItem.state.explanation}
            <span class="save-hint">{_("已保存过解释，再次提交将覆盖。")}</span>
          {/if}
        </div>
      </div>

      <div class="detail-section detail-note">
        <h3>{_("备注")}</h3>
        <p class="section-hint">
          {_("添加内部备注信息，不会改变复核状态。")}
        </p>
        <textarea
          class="form-textarea"
          bind:value={noteDraft}
          rows={4}
          placeholder={_("请输入备注信息...")}
          onblur={handleSaveNote}
        ></textarea>
        <div class="form-actions">
          <button
            type="button"
            class="btn btn-secondary"
            onclick={handleSaveNote}
          >
            {_("保存备注")}
          </button>
          <span class="save-hint">{_("失焦时自动保存。")}</span>
        </div>
      </div>

      <div class="detail-section detail-nav-bottom">
        <div class="nav-arrows bottom-nav">
          <button
            type="button"
            class="btn btn-nav"
            onclick={goPrev}
            disabled={!prevItem}
          >
            ◀ {_("上一条")}
          </button>
          <button
            type="button"
            class="btn btn-back"
            onclick={goList}
          >
            {_("返回列表")}
          </button>
          <button
            type="button"
            class="btn btn-nav"
            onclick={goNext}
            disabled={!nextItem}
          >
            {_("下一条")} ▶
          </button>
        </div>
      </div>
    </div>
  {:else}
    <div class="not-found">
      <p>{_("未找到对应的异常记录。")}</p>
      <button type="button" class="btn btn-back" onclick={goList}>
        {_("返回复核台列表")}
      </button>
    </div>
  {/if}
</div>

<style>
  .review-detail {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .detail-nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .nav-arrows {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .nav-counter {
    font-size: 0.85rem;
    color: #666;
    padding: 0 0.5rem;
  }

  .detail-body {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .detail-section {
    padding: 1rem 1.25rem;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    background: #fff;
  }

  .detail-section h3 {
    margin: 0 0 0.75rem 0;
    font-size: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #eee;
  }

  .section-hint {
    margin: 0 0 0.5rem 0;
    font-size: 0.8rem;
    color: #888;
    font-style: italic;
  }

  .status-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
  }

  .badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 10px;
    font-size: 0.8rem;
    font-weight: 500;
  }

  .badge.large {
    padding: 0.35rem 0.85rem;
    font-size: 0.9rem;
    border-radius: 12px;
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

  .updated-time {
    font-size: 0.8rem;
    color: #888;
  }

  .status-actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .info-dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.5rem 1rem;
    margin: 0;
  }

  .info-dl dt {
    font-weight: 600;
    color: #555;
    padding: 0.25rem 0;
    white-space: nowrap;
  }

  .info-dl dd {
    margin: 0;
    padding: 0.25rem 0;
    word-wrap: break-word;
  }

  .type-value {
    font-family: monospace;
    font-size: 0.85rem;
    color: #0056b3;
  }

  .na {
    color: #aaa;
  }

  .message-detail {
    background: #fafafa;
    padding: 0.75rem;
    border-radius: 4px;
    border: 1px solid #eee;
    max-height: 300px;
    overflow-y: auto;
  }

  .form-textarea {
    width: 100%;
    box-sizing: border-box;
    padding: 0.6rem 0.8rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.85rem;
    font-family: inherit;
    resize: vertical;
    min-height: 80px;
    transition: border-color 0.15s;
  }

  .form-textarea:focus {
    outline: none;
    border-color: #007bff;
    box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.15);
  }

  .form-actions {
    margin-top: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .save-hint {
    font-size: 0.75rem;
    color: #888;
    font-style: italic;
  }

  .btn {
    display: inline-block;
    padding: 0.4rem 0.85rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.15s;
    font-family: inherit;
  }

  .btn:hover:not(:disabled) {
    background: #f0f0f0;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-back {
    border-color: #6c757d;
    color: #383d41;
  }

  .btn-back:hover:not(:disabled) {
    background: #e2e3e5;
  }

  .btn-nav {
    border-color: #007bff;
    color: #007bff;
  }

  .btn-nav:hover:not(:disabled) {
    background: #cce5ff;
  }

  .btn-skip {
    border-color: #ffc107;
    background: #fff3cd;
    color: #856404;
  }

  .btn-skip:hover:not(:disabled) {
    background: #ffe69c;
  }

  .btn-reset {
    border-color: #6c757d;
    color: #383d41;
  }

  .btn-reset:hover:not(:disabled) {
    background: #e2e3e5;
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
    border-color: #007bff;
    color: #007bff;
  }

  .btn-secondary:hover:not(:disabled) {
    background: #cce5ff;
  }

  .detail-nav-bottom {
    background: transparent;
    border: none;
    padding: 0;
  }

  .bottom-nav {
    justify-content: center;
    gap: 0.75rem;
  }

  .not-found {
    text-align: center;
    padding: 3rem 1rem;
    color: #888;
  }

  .not-found p {
    margin: 0 0 1rem 0;
    font-style: italic;
  }

  .pre {
    white-space: pre-wrap;
    word-wrap: break-word;
  }
</style>
