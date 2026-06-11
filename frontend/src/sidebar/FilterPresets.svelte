<!--
  @component
  Filter presets management component.

  Provides UI for:
  - Saving current filters as a named preset
  - Quick switching between saved presets via dropdown
  - Renaming and deleting presets (with conflict prompts)
  - Automatic sync with the backend
-->
<script lang="ts">
  import { _ } from "../i18n.ts";
  import {
    filter_presets,
    filters_from_url,
  } from "../stores/filter_presets.ts";
  import type {
    FilterPreset,
    FilterPresetPageType,
  } from "../api/index.ts";
  import { onMount, tick } from "svelte";

  interface Props {
    /** The page type this component is used on. */
    page: FilterPresetPageType;
  }

  let { page }: Props = $props();

  /** The currently selected preset ID in the dropdown (empty = no selection). */
  let selected_preset_id = $state("");
  /** Whether the save dialog is open. */
  let show_save_dialog = $state(false);
  /** Whether the manage menu is open. */
  let show_manage_menu = $state(false);
  /** The name for a new preset. */
  let new_preset_name = $state("");
  /** The preset being renamed (id). */
  let renaming_id = $state<string | null>(null);
  /** The rename input value. */
  let rename_value = $state("");
  /** Reference to the manage menu button for click-outside detection. */
  let menu_button: HTMLButtonElement | undefined = $state();
  /** Reference to the save dialog input. */
  let save_input: HTMLInputElement | undefined = $state();

  let presets_list = $state<FilterPreset[]>([]);
  let loading = $state(false);

  function unsubscribe_presets() {
    return filter_presets.subscribe((v) => {
      presets_list = v;
    });
  }
  function unsubscribe_loading() {
    return filter_presets.loading.subscribe((v) => {
      loading = v;
    });
  }

  let unsub_presets: ReturnType<typeof unsubscribe_presets>;
  let unsub_loading: ReturnType<typeof unsubscribe_loading>;

  onMount(() => {
    unsub_presets = unsubscribe_presets();
    unsub_loading = unsubscribe_loading();
    refresh_presets();

    return () => {
      unsub_presets();
      unsub_loading();
    };
  });

  /**
   * Refresh the presets list for the current page type.
   */
  async function refresh_presets(): Promise<void> {
    await filter_presets.load(page);
  }

  $effect(() => {
    if (show_save_dialog) {
      tick().then(() => {
        save_input?.focus();
      });
    }
  });

  /**
   * Handle selecting a preset from the dropdown.
   */
  function on_select_change(event: Event): void {
    const target = event.target as HTMLSelectElement;
    const id = target.value;
    if (id) {
      filter_presets.apply(id);
      selected_preset_id = id;
    }
  }

  /**
   * Open the save preset dialog.
   */
  function open_save_dialog(): void {
    new_preset_name = "";
    show_save_dialog = true;
  }

  /**
   * Close the save preset dialog.
   */
  function close_save_dialog(): void {
    show_save_dialog = false;
    new_preset_name = "";
  }

  /**
   * Save the current filters as a new preset.
   */
  async function save_current_as_preset(): Promise<void> {
    const name = new_preset_name.trim();
    if (!name) return;

    const filters = filters_from_url();
    const created = await filter_presets.create(name, page, filters);
    if (created) {
      selected_preset_id = created.id;
      close_save_dialog();
    }
  }

  /**
   * Update an existing preset with current filters.
   */
  async function overwrite_preset(id: string): Promise<void> {
    const preset = filter_presets.find_by_id(id);
    if (!preset) return;

    const confirmed = window.confirm(
      _(`Overwrite the filters in preset "{name}"?`).replace(
        "{name}",
        preset.name,
      ),
    );
    if (!confirmed) return;

    const filters = filters_from_url();
    await filter_presets.update_filters(id, filters);
    show_manage_menu = false;
  }

  /**
   * Start renaming a preset.
   */
  function start_rename(preset: FilterPreset): void {
    renaming_id = preset.id;
    rename_value = preset.name;
  }

  /**
   * Cancel renaming.
   */
  function cancel_rename(): void {
    renaming_id = null;
    rename_value = "";
  }

  /**
   * Confirm renaming a preset.
   */
  async function confirm_rename(id: string): Promise<void> {
    const name = rename_value.trim();
    if (!name) return;

    const updated = await filter_presets.rename(id, name);
    if (updated) {
      cancel_rename();
    }
  }

  /**
   * Delete a preset.
   */
  async function delete_preset(id: string): Promise<void> {
    const success = await filter_presets.delete(id);
    if (success) {
      if (selected_preset_id === id) {
        selected_preset_id = "";
      }
      show_manage_menu = false;
    }
  }

  /**
   * Close manage menu when clicking outside.
   */
  function handle_click_outside(event: MouseEvent): void {
    if (
      show_manage_menu &&
      menu_button &&
      !menu_button.contains(event.target as Node) &&
      !(event.target as HTMLElement).closest(".preset-manage-menu")
    ) {
      show_manage_menu = false;
    }
  }

  /** Format a timestamp to a readable date string. */
  function format_date(timestamp: number): string {
    return new Date(timestamp * 1000).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
</script>

<svelte:body onclick={handle_click_outside} />

<div class="filter-presets">
  <!-- Preset selector dropdown -->
  <div class="preset-selector">
    <select
      bind:value={selected_preset_id}
      onchange={on_select_change}
      disabled={loading || presets_list.length === 0}
      title={_("Select a saved filter preset")}
    >
      <option value="">
        {loading ? _("Loading…") : _("— Select Preset —")}
      </option>
      {#each presets_list as preset (preset.id)}
        <option value={preset.id}>{preset.name}</option>
      {/each}
    </select>
  </div>

  <!-- Save button -->
  <button
    type="button"
    class="preset-save-btn"
    onclick={open_save_dialog}
    title={_("Save current filters as a preset")}
  >
    💾
  </button>

  <!-- Manage menu button -->
  <button
    type="button"
    class="preset-manage-btn"
    bind:this={menu_button}
    onclick={() => (show_manage_menu = !show_manage_menu)}
    title={_("Manage filter presets")}
    disabled={presets_list.length === 0}
  >
    ⚙️
  </button>
</div>

<!-- Save Preset Dialog -->
{#if show_save_dialog}
  <div class="preset-dialog-overlay" onclick={close_save_dialog}>
    <div
      class="preset-dialog"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label={_("Save filter preset")}
    >
      <h3>{_("Save as Preset")}</h3>
      <div class="preset-dialog-body">
        <label>
          <span>{_("Preset name")}:</span>
          <input
            type="text"
            bind:value={new_preset_name}
            bind:this={save_input}
            placeholder={_("Enter a name for this filter preset")}
            onkeydown={(e) => {
              if (e.key === "Enter") save_current_as_preset();
              if (e.key === "Escape") close_save_dialog();
            }}
          />
        </label>
        <div class="preset-hint">
          {_("Current filters will be saved with this name.")}
        </div>
      </div>
      <div class="preset-dialog-actions">
        <button type="button" class="btn-cancel" onclick={close_save_dialog}>
          {_("Cancel")}
        </button>
        <button
          type="button"
          class="btn-primary"
          onclick={save_current_as_preset}
          disabled={!new_preset_name.trim()}
        >
          {_("Save")}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Manage Presets Menu -->
{#if show_manage_menu && presets_list.length > 0}
  <div class="preset-manage-menu" role="menu">
    <div class="manage-menu-header">
      <strong>{_("Manage Presets")}</strong>
    </div>
    <ul>
      {#each presets_list as preset (preset.id)}
        <li class="manage-menu-item" role="none">
          {#if renaming_id === preset.id}
            <div class="rename-form">
              <input
                type="text"
                bind:value={rename_value}
                onkeydown={(e) => {
                  if (e.key === "Enter") confirm_rename(preset.id);
                  if (e.key === "Escape") cancel_rename();
                }}
                onblur={() => {
                  if (rename_value.trim() && rename_value !== preset.name) {
                    confirm_rename(preset.id);
                  } else {
                    cancel_rename();
                  }
                }}
                autofocus
              />
            </div>
          {:else}
            <div class="preset-info">
              <span class="preset-name">{preset.name}</span>
              <span class="preset-meta">
                {preset.page !== "all"
                  ? `${preset.page} · `
                  : ""}{format_date(preset.updated_at)}
              </span>
            </div>
          {/if}
          <div class="preset-actions">
            {#if renaming_id !== preset.id}
              <button
                type="button"
                class="action-btn apply"
                title={_("Apply this preset")}
                onclick={() => {
                  filter_presets.apply(preset.id);
                  selected_preset_id = preset.id;
                  show_manage_menu = false;
                }}
              >
                →
              </button>
              <button
                type="button"
                class="action-btn overwrite"
                title={_("Overwrite with current filters")}
                onclick={() => overwrite_preset(preset.id)}
              >
                ↺
              </button>
              <button
                type="button"
                class="action-btn rename"
                title={_("Rename preset")}
                onclick={() => start_rename(preset)}
              >
                ✏️
              </button>
              <button
                type="button"
                class="action-btn delete"
                title={_("Delete preset")}
                onclick={() => delete_preset(preset.id)}
              >
                🗑️
              </button>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
    <div class="manage-menu-footer">
      <button type="button" class="btn-refresh" onclick={refresh_presets}>
        🔄 {_("Refresh")}
      </button>
    </div>
  </div>
{/if}

<style>
  .filter-presets {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-left: 8px;
    position: relative;
  }

  .preset-selector select {
    padding: 6px 24px 6px 8px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--background);
    color: var(--text-color);
    font-size: 13px;
    cursor: pointer;
    max-width: 200px;
    text-overflow: ellipsis;
  }

  .preset-selector select:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .preset-save-btn,
  .preset-manage-btn {
    padding: 6px 8px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--background);
    color: var(--text-color);
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
  }

  .preset-save-btn:hover,
  .preset-manage-btn:hover {
    background-color: var(--hover-background);
  }

  .preset-manage-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Dialog overlay */
  .preset-dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .preset-dialog {
    background-color: var(--background);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 20px;
    min-width: 360px;
    max-width: 90vw;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  }

  .preset-dialog h3 {
    margin: 0 0 16px 0;
    font-size: 16px;
    color: var(--text-color);
  }

  .preset-dialog-body label {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .preset-dialog-body label span {
    font-size: 13px;
    color: var(--text-color);
  }

  .preset-dialog-body input[type="text"] {
    padding: 8px 10px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--input-background, var(--background));
    color: var(--text-color);
    font-size: 14px;
  }

  .preset-dialog-body input[type="text"]:focus {
    outline: none;
    border-color: var(--accent-color, #2563eb);
  }

  .preset-hint {
    margin-top: 8px;
    font-size: 12px;
    color: var(--muted-text-color, #6b7280);
  }

  .preset-dialog-actions {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .btn-cancel,
  .btn-primary {
    padding: 8px 16px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
  }

  .btn-cancel {
    background-color: var(--background);
    color: var(--text-color);
  }

  .btn-cancel:hover {
    background-color: var(--hover-background);
  }

  .btn-primary {
    background-color: var(--accent-color, #2563eb);
    color: white;
    border-color: var(--accent-color, #2563eb);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary:hover:not(:disabled) {
    background-color: var(--accent-color-hover, #1d4ed8);
  }

  /* Manage menu */
  .preset-manage-menu {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 4px;
    background-color: var(--background);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    z-index: 999;
    min-width: 380px;
    max-width: 480px;
    max-height: 60vh;
    overflow-y: auto;
  }

  .manage-menu-header {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-color);
    font-size: 13px;
  }

  .preset-manage-menu ul {
    list-style: none;
    margin: 0;
    padding: 4px 0;
  }

  .manage-menu-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    gap: 8px;
    border-bottom: 1px solid var(--border-color-light, rgba(0, 0, 0, 0.06));
  }

  .manage-menu-item:last-child {
    border-bottom: none;
  }

  .preset-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
    flex: 1;
  }

  .preset-name {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .preset-meta {
    font-size: 11px;
    color: var(--muted-text-color, #6b7280);
    margin-top: 2px;
  }

  .rename-form {
    flex: 1;
  }

  .rename-form input {
    width: 100%;
    padding: 4px 6px;
    border: 1px solid var(--accent-color, #2563eb);
    border-radius: 3px;
    background-color: var(--input-background, var(--background));
    color: var(--text-color);
    font-size: 13px;
  }

  .preset-actions {
    display: flex;
    gap: 2px;
    flex-shrink: 0;
  }

  .action-btn {
    width: 28px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: 4px;
    background: transparent;
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .action-btn:hover {
    background-color: var(--hover-background);
  }

  .action-btn.apply:hover {
    background-color: rgba(34, 197, 94, 0.15);
  }

  .action-btn.overwrite:hover {
    background-color: rgba(59, 130, 246, 0.15);
  }

  .action-btn.rename:hover {
    background-color: rgba(234, 179, 8, 0.15);
  }

  .action-btn.delete:hover {
    background-color: rgba(239, 68, 68, 0.15);
  }

  .manage-menu-footer {
    padding: 8px 14px;
    border-top: 1px solid var(--border-color);
    display: flex;
    justify-content: flex-end;
  }

  .btn-refresh {
    padding: 6px 10px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--background);
    color: var(--text-color);
    font-size: 12px;
    cursor: pointer;
  }

  .btn-refresh:hover {
    background-color: var(--hover-background);
  }

  @media (max-width: 768px) {
    .filter-presets {
      margin-left: 4px;
    }

    .preset-selector select {
      max-width: 140px;
      font-size: 12px;
    }

    .preset-dialog {
      min-width: 280px;
    }

    .preset-manage-menu {
      min-width: 280px;
    }
  }
</style>
