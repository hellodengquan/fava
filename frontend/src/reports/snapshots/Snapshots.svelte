<script lang="ts">
  import {
    delete_snapshot,
    get_snapshot_compare,
    get_snapshots,
    put_snapshot_clean,
  } from "../../api/index.ts";
  import type { SnapshotMeta } from "../../api/validators.ts";
  import { _ } from "../../i18n.ts";
  import { notify, notify_err } from "../../notifications.ts";
  import { operating_currency } from "../../stores/options.ts";
  import { ctx } from "../../stores/format.ts";
  import { currency_name } from "../../stores/index.ts";
  import SnapshotDiffTree from "./SnapshotDiffTree.svelte";

  type CompareResult = Awaited<ReturnType<typeof get_snapshot_compare>>;

  let snapshots = $state<SnapshotMeta[]>([]);
  let selected_a = $state<string>("");
  let selected_b = $state<string>("");
  let compare_result = $state<CompareResult | null>(null);
  let loading = $state(false);
  let comparing = $state(false);
  let show_clean_dialog = $state(false);
  let clean_keep_last_n = $state<number>(10);
  let clean_keep_days = $state<number>(30);
  let clean_per_report_type = $state<boolean>(true);
  let cleaning = $state(false);

  const report_type_labels: Record<string, string> = {
    balance_sheet: _("Balance Sheet"),
    income_statement: _("Income Statement"),
    trial_balance: _("Trial Balance"),
    account_report: _("Account Report"),
  };

  async function load_snapshots() {
    loading = true;
    try {
      snapshots = await get_snapshots({});
    } catch (error) {
      notify_err(error);
    } finally {
      loading = false;
    }
  }

  async function compare() {
    if (!selected_a || !selected_b) {
      notify(_("Please select two snapshots to compare."), "warning");
      return;
    }
    if (selected_a === selected_b) {
      notify(_("Please select two different snapshots."), "warning");
      return;
    }
    comparing = true;
    try {
      compare_result = await get_snapshot_compare({
        snapshot_a: selected_a,
        snapshot_b: selected_b,
      });
    } catch (error) {
      notify_err(error);
    } finally {
      comparing = false;
    }
  }

  async function remove(id: string) {
    try {
      await delete_snapshot({ snapshot_id: id });
      notify(_("Snapshot deleted."));
      snapshots = snapshots.filter((s) => s.id !== id);
      if (selected_a === id) selected_a = "";
      if (selected_b === id) selected_b = "";
      if (compare_result?.snapshot_a.id === id || compare_result?.snapshot_b.id === id) {
        compare_result = null;
      }
    } catch (error) {
      notify_err(error);
    }
  }

  async function clean_snapshots() {
    if (clean_keep_last_n <= 0 && clean_keep_days <= 0) {
      notify(_("Please set at least one retention policy."), "warning");
      return;
    }
    cleaning = true;
    try {
      const result = await put_snapshot_clean({
        keep_last_n: clean_keep_last_n > 0 ? clean_keep_last_n : undefined,
        keep_days: clean_keep_days > 0 ? clean_keep_days : undefined,
        per_report_type: clean_per_report_type,
      });
      notify(
        _("Cleaned {deleted} snapshots, kept {kept}.").replace(
          "{deleted}",
          String(result.deleted.length),
        ).replace("{kept}", String(result.kept.length)),
      );
      await load_snapshots();
      show_clean_dialog = false;
      compare_result = null;
    } catch (error) {
      notify_err(error);
    } finally {
      cleaning = false;
    }
  }

  function format_filters(filters: SnapshotMeta["filters"]): string {
    const parts: string[] = [];
    if (filters.time) parts.push(`time=${filters.time}`);
    if (filters.account) parts.push(`account=${filters.account}`);
    if (filters.filter) parts.push(`filter=${filters.filter}`);
    if (filters.conversion) parts.push(`conversion=${filters.conversion}`);
    if (filters.interval) parts.push(`interval=${filters.interval}`);
    return parts.length > 0 ? parts.join(", ") : _("(no filters)");
  }

  function format_diff_value(diff: number, currency: string): string {
    const sign = diff > 0 ? "+" : "";
    return `${sign}${$ctx.num(diff, currency)}`;
  }

  load_snapshots();
</script>

<div class="snapshots-page">
  <div class="snapshot-list-section">
    <h3>{_("Saved Snapshots")}</h3>
    {#if loading}
      <p>{_("Loading...")}</p>
    {:else if snapshots.length === 0}
      <p>{_("No snapshots yet. Save a snapshot from a report page.")}</p>
    {:else}
      <table class="snapshot-table">
        <thead>
          <tr>
            <th></th>
            <th></th>
            <th>{_("Name")}</th>
            <th>{_("Report Type")}</th>
            <th>{_("Created At")}</th>
            <th>{_("Filters")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each snapshots as snap (snap.id)}
            <tr>
              <td class="select-cell">
                <label>
                  <input
                    type="radio"
                    name="snapshot_a"
                    value={snap.id}
                    bind:group={selected_a}
                  />
                </label>
              </td>
              <td class="select-cell">
                <label>
                  <input
                    type="radio"
                    name="snapshot_b"
                    value={snap.id}
                    bind:group={selected_b}
                  />
                </label>
              </td>
              <td>{snap.name}</td>
              <td>{report_type_labels[snap.report_type] ?? snap.report_type}</td>
              <td class="mono">{snap.created_at}</td>
              <td class="filters-cell">{format_filters(snap.filters)}</td>
              <td>
                <button type="button" class="delete-btn" onclick={() => remove(snap.id)}>
                  ✕
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <div class="compare-actions">
        <button
          type="button"
          class="compare-btn"
          disabled={!selected_a || !selected_b || selected_a === selected_b || comparing}
          onclick={compare}
        >
          {comparing ? _("Comparing...") : _("Compare Selected Snapshots")}
        </button>
        <button
          type="button"
          class="clean-btn"
          onclick={() => (show_clean_dialog = true)}
        >
          🗑 {_("Clean Up...")}
        </button>
      </div>
    {/if}
  </div>

  {#if show_clean_dialog}
    <div class="modal-overlay" onclick={() => (show_clean_dialog = false)}>
      <div class="modal-dialog" onclick={(e) => e.stopPropagation()}>
        <h3>{_("Clean Up Snapshots")}</h3>
        <p class="modal-desc">
          {_("Delete old snapshots according to the retention policy below.")}
        </p>
        <div class="form-row">
          <label>
            {_("Keep last N snapshots per report type:")}
            <input
              type="number"
              min="0"
              bind:value={clean_keep_last_n}
            />
          </label>
        </div>
        <div class="form-row">
          <label>
            {_("Keep snapshots from last N days:")}
            <input
              type="number"
              min="0"
              bind:value={clean_keep_days}
            />
          </label>
        </div>
        <div class="form-row">
          <label>
            <input
              type="checkbox"
              bind:checked={clean_per_report_type}
            />
            {_("Apply per report type")}
          </label>
        </div>
        <div class="form-actions">
          <button
            type="button"
            class="cancel-btn"
            onclick={() => (show_clean_dialog = false)}
          >
            {_("Cancel")}
          </button>
          <button
            type="button"
            class="confirm-btn"
            disabled={cleaning}
            onclick={clean_snapshots}
          >
            {cleaning ? _("Cleaning...") : _("Clean Up")}
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if compare_result}
    <div class="compare-result-section">
      <h3>{_("Snapshot Comparison")}</h3>
      <div class="compare-meta">
        <div class="compare-meta-item">
          <strong>{_("Snapshot A")}:</strong>
          {compare_result.snapshot_a.name}
          <span class="mono">({compare_result.snapshot_a.created_at})</span>
        </div>
        <div class="compare-meta-item">
          <strong>{_("Snapshot B")}:</strong>
          {compare_result.snapshot_b.name}
          <span class="mono">({compare_result.snapshot_b.created_at})</span>
        </div>
      </div>

      {#if Object.keys(compare_result.balance_diff).length > 0}
        <h4>{_("Balance Changes")}</h4>
        <table class="diff-table">
          <thead>
            <tr>
              <th>{_("Account")}</th>
              {#each $operating_currency as currency (currency)}
                <th class="num">{currency}</th>
              {/each}
              <th class="num other">{_("Other")}</th>
            </tr>
          </thead>
          <tbody>
            {#each Object.entries(compare_result.balance_diff) as [account, diffs] (account)}
              <tr>
                <td>{account}</td>
                {#each $operating_currency as currency (currency)}
                  <td class="num">
                    {#if diffs[currency] != null}
                      <span class:positive={diffs[currency] > 0} class:negative={diffs[currency] < 0}>
                        {format_diff_value(diffs[currency], currency)}
                      </span>
                    {/if}
                  </td>
                {/each}
                <td class="num other">
                  {#each Object.entries(diffs).filter(([c]) => !$operating_currency.includes(c)) as [currency, diff] (currency)}
                    <span class:positive={diff > 0} class:negative={diff < 0}>
                      {format_diff_value(diff, currency)} {$currency_name(currency)}
                    </span><br />
                  {/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="no-diff">{_("No balance differences between the two snapshots.")}</p>
      {/if}

      {#if compare_result.tree_diff.length > 0}
        <h4>{_("Tree Structure Changes")}</h4>
        {#each compare_result.tree_diff as tree, i (i)}
          <div class="tree-diff-section">
            {#if compare_result.tree_diff.length > 1}
              <h5>{_("Tree")} {i + 1}</h5>
            {/if}
            <SnapshotDiffTree {tree} />
          </div>
        {/each}
      {/if}

      {#if compare_result.budget_diff && Object.keys(compare_result.budget_diff).length > 0}
        <h4>{_("Budget Changes")}</h4>
        <table class="diff-table">
          <thead>
            <tr>
              <th>{_("Account")}</th>
              <th>{_("Period")}</th>
              <th>{_("Budget Diff")}</th>
              <th>{_("Budget Children Diff")}</th>
            </tr>
          </thead>
          <tbody>
            {#each Object.entries(compare_result.budget_diff) as [account, periods] (account)}
              {#each periods as period, pi (pi)}
                <tr>
                  <td>{account}</td>
                  <td>{pi + 1}</td>
                  <td>
                    {#each Object.entries(period.budget_diff) as [currency, diff] (currency)}
                      <span class:positive={diff > 0} class:negative={diff < 0}>
                        {format_diff_value(diff, currency)} {currency}
                      </span><br />
                    {/each}
                  </td>
                  <td>
                    {#each Object.entries(period.budget_children_diff) as [currency, diff] (currency)}
                      <span class:positive={diff > 0} class:negative={diff < 0}>
                        {format_diff_value(diff, currency)} {currency}
                      </span><br />
                    {/each}
                  </td>
                </tr>
              {/each}
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  {/if}
</div>

<style>
  .snapshots-page {
    padding: 0 0.5rem;
  }

  .snapshot-list-section {
    margin-bottom: 2rem;
  }

  .snapshot-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9em;
  }

  .snapshot-table th,
  .snapshot-table td {
    padding: 0.4em 0.6em;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }

  .snapshot-table th {
    font-weight: bold;
    background-color: var(--background);
  }

  .select-cell {
    width: 30px;
    text-align: center;
  }

  .filters-cell {
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mono {
    font-family: var(--font-family-monospace);
    font-size: 0.9em;
  }

  .compare-actions {
    margin-top: 1rem;
    display: flex;
    gap: 0.5rem;
  }

  .compare-btn {
    padding: 0.5em 1.5em;
    color: var(--background);
    background-color: var(--link-color);
    border: none;
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.95em;
  }

  .compare-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .compare-btn:not(:disabled):hover {
    opacity: 0.9;
  }

  .clean-btn {
    padding: 0.5em 1.5em;
    color: var(--text);
    background-color: var(--background);
    border: 1px solid var(--border);
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.95em;
  }

  .clean-btn:hover {
    border-color: var(--link-color);
  }

  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal-dialog {
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1.5rem;
    min-width: 360px;
    max-width: 90vw;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }

  .modal-dialog h3 {
    margin-top: 0;
    margin-bottom: 0.5rem;
  }

  .modal-desc {
    color: var(--gray, #666);
    font-size: 0.9em;
    margin-bottom: 1rem;
  }

  .form-row {
    margin-bottom: 0.8rem;
  }

  .form-row label {
    display: block;
    font-size: 0.9em;
    margin-bottom: 0.3rem;
  }

  .form-row input[type="number"] {
    width: 100%;
    padding: 0.4em 0.6em;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--background);
    color: var(--text);
  }

  .form-row input[type="checkbox"] {
    margin-right: 0.5em;
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 1.5rem;
  }

  .cancel-btn {
    padding: 0.5em 1.2em;
    background: var(--background);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 3px;
    cursor: pointer;
  }

  .cancel-btn:hover {
    border-color: var(--gray, #888);
  }

  .confirm-btn {
    padding: 0.5em 1.2em;
    background: var(--error-text, #c00);
    color: white;
    border: none;
    border-radius: 3px;
    cursor: pointer;
  }

  .confirm-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .confirm-btn:not(:disabled):hover {
    opacity: 0.9;
  }

  .delete-btn {
    padding: 2px 6px;
    color: var(--error-text, #c00);
    background: none;
    border: 1px solid transparent;
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.9em;
  }

  .delete-btn:hover {
    border-color: var(--error-text, #c00);
    background-color: var(--error-text, #c00);
    color: white;
  }

  .compare-result-section {
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 2px solid var(--border);
  }

  .compare-meta {
    display: flex;
    gap: 2rem;
    margin-bottom: 1.5rem;
    font-size: 0.9em;
  }

  .compare-meta-item {
    padding: 0.5em 1em;
    background-color: var(--background);
    border: 1px solid var(--border);
    border-radius: 3px;
  }

  .diff-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9em;
    margin-bottom: 1.5rem;
  }

  .diff-table th,
  .diff-table td {
    padding: 0.4em 0.6em;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }

  .diff-table th {
    font-weight: bold;
    background-color: var(--background);
  }

  .diff-table td.num,
  .diff-table th.num {
    text-align: right;
  }

  .diff-table td.other,
  .diff-table th.other {
    text-align: right;
  }

  .positive {
    color: var(--diff-positive, green);
  }

  .negative {
    color: var(--diff-negative, red);
  }

  .no-diff {
    color: var(--gray, #888);
    font-style: italic;
  }

  .tree-diff-section {
    margin-bottom: 1.5rem;
  }

  .tree-diff-section h5 {
    margin-bottom: 0.5rem;
  }
</style>
