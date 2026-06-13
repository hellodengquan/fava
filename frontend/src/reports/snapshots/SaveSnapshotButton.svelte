<script lang="ts">
  import { put_snapshot } from "../../api/index.ts";
  import { _ } from "../../i18n.ts";
  import { notify, notify_err } from "../../notifications.ts";
  import { searchParams } from "../../stores/url.ts";

  interface Props {
    report_type: string;
  }

  let { report_type }: Props = $props();

  let show_dialog = $state(false);
  let snapshot_name = $state("");
  let saving = $state(false);

  function open_dialog() {
    const now = new Date();
    snapshot_name = `${report_type} ${now.toLocaleDateString()}`;
    show_dialog = true;
  }

  function close_dialog() {
    show_dialog = false;
    snapshot_name = "";
  }

  async function save() {
    if (!snapshot_name.trim()) {
      notify(_("Please enter a name for the snapshot."), "warning");
      return;
    }
    saving = true;
    try {
      const params: Record<string, string> = {
        name: snapshot_name.trim(),
        report_type,
      };
      const $params = $searchParams;
      for (const key of ["account", "conversion", "filter", "interval", "time"]) {
        const val = $params.get(key);
        if (val) params[key] = val;
      }
      if ($params.get("a")) params.a = $params.get("a")!;
      if ($params.get("r")) params.r = $params.get("r")!;
      await put_snapshot(params);
      notify(_("Snapshot saved successfully."));
      close_dialog();
    } catch (error) {
      notify_err(error);
    } finally {
      saving = false;
    }
  }
</script>

<button type="button" class="snapshot-btn" title={_("Save Snapshot")} onclick={open_dialog}>
  📷
</button>

{#if show_dialog}
  <div class="snapshot-overlay" onclick={close_dialog} role="presentation">
    <div class="snapshot-dialog" onclick={(e) => e.stopPropagation()}>
      <h3>{_("Save Snapshot")}</h3>
      <p class="dialog-hint">{_("Save the current report view as a snapshot for later comparison.")}</p>
      <label>
        {_("Name")}
        <input type="text" bind:value={snapshot_name} placeholder={_("Snapshot name")} />
      </label>
      <div class="dialog-actions">
        <button type="button" class="cancel-btn" onclick={close_dialog}>
          {_("Cancel")}
        </button>
        <button type="button" class="save-btn" disabled={saving || !snapshot_name.trim()} onclick={save}>
          {saving ? _("Saving...") : _("Save")}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .snapshot-btn {
    padding: 2px 6px;
    background: none;
    border: 1px solid var(--border, #ccc);
    border-radius: 3px;
    cursor: pointer;
    font-size: 1em;
    line-height: 1;
  }

  .snapshot-btn:hover {
    background-color: var(--sidebar-border, #eee);
  }

  .snapshot-overlay {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: rgb(0 0 0 / 50%);
  }

  .snapshot-dialog {
    width: 400px;
    max-width: 90vw;
    padding: 1.5rem;
    background-color: var(--background, #fff);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgb(0 0 0 / 20%);
  }

  .snapshot-dialog h3 {
    margin: 0 0 0.5rem;
  }

  .dialog-hint {
    margin: 0 0 1rem;
    font-size: 0.9em;
    color: var(--gray, #888);
  }

  .snapshot-dialog label {
    display: block;
    margin-bottom: 1rem;
    font-size: 0.9em;
  }

  .snapshot-dialog input {
    display: block;
    width: 100%;
    padding: 0.4em;
    margin-top: 0.3em;
    border: 1px solid var(--border, #ccc);
    border-radius: 3px;
    font-size: 1em;
  }

  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  .cancel-btn {
    padding: 0.4em 1em;
    background: none;
    border: 1px solid var(--border, #ccc);
    border-radius: 3px;
    cursor: pointer;
  }

  .save-btn {
    padding: 0.4em 1em;
    color: var(--background, #fff);
    background-color: var(--link-color, #0066cc);
    border: none;
    border-radius: 3px;
    cursor: pointer;
  }

  .save-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .save-btn:not(:disabled):hover {
    opacity: 0.9;
  }
</style>
