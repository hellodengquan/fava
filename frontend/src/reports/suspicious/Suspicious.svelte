<script lang="ts">
  import { _ } from "../../i18n.ts";
  import { base_url } from "../../stores/index.ts";
  import { mark_suspicious, unmark_suspicious } from "../../api/index.ts";
  import type {
    SuspiciousByAccount,
    SuspiciousByTime,
    SuspiciousTransaction,
  } from "../../api/validators.ts";

  export let by_account: SuspiciousByAccount[] = $props();
  export let by_time: SuspiciousByTime[] = $props();
  export let view_mode: "account" | "time" = $props("account");
  export let interval: string = $props("month");

  function url_for_entry(entry_hash: string): string {
    return `${$base_url}journal/#context-${entry_hash}`;
  }

  async function handle_toggle_suspicious(
    entry_hash: string,
    currently_suspicious: boolean,
  ) {
    if (currently_suspicious) {
      await unmark_suspicious(entry_hash);
    } else {
      const reason = prompt(_("Reason for marking as suspicious:"), "suspicious");
      if (reason !== null) {
        await mark_suspicious(entry_hash, reason || "suspicious");
      }
    }
  }
</script>

<div class="suspicious-review">
  <div class="view-switcher">
    <button
      class={view_mode === "account" ? "active" : ""}
      onclick={() => (view_mode = "account")}
    >
      {_("By Account")}
    </button>
    <button
      class={view_mode === "time" ? "active" : ""}
      onclick={() => (view_mode = "time")}
    >
      {_("By Time")}
    </button>
    {#if view_mode === "time"}
      <select
        bind:value={interval}
        onchange={() => {
          // This will be handled by the route loader
        }}
      >
        <option value="day">{_("Day")}</option>
        <option value="week">{_("Week")}</option>
        <option value="month">{_("Month")}</option>
        <option value="quarter">{_("Quarter")}</option>
        <option value="year">{_("Year")}</option>
      </select>
    {/if}
  </div>

  {#if view_mode === "account"}
    {#if by_account.length === 0}
      <p class="empty">{_("No suspicious transactions.")}</p>
    {:else}
      <div class="account-groups">
        {#each by_account as group}
          <div class="account-group">
            <h3>
              <a href={`${$base_url}account/${group.account}`}>{group.account}</a>
              <span class="count">{group.count}</span>
            </h3>
            <table>
              <thead>
                <tr>
                  <th>{_("Date")}</th>
                  <th>{_("Payee")}</th>
                  <th>{_("Narration")}</th>
                  <th>{_("Reason")}</th>
                  <th>{_("Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {#each group.transactions as tx}
                  <tr>
                    <td>
                      <a href={url_for_entry(tx.entry_hash)}>{tx.date}</a>
                    </td>
                    <td>{tx.payee}</td>
                    <td>{tx.narration}</td>
                    <td>{tx.suspicious_reason || "-"}</td>
                    <td>
                      <button
                        class="unmark-btn"
                        onclick={() => handle_toggle_suspicious(tx.entry_hash, true)}
                      >
                        {_("Unmark")}
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/each}
      </div>
    {/if}
  {:else}
    {#if by_time.length === 0}
      <p class="empty">{_("No suspicious transactions.")}</p>
    {:else}
      <div class="time-groups">
        {#each by_time as period}
          <div class="time-group">
            <h3>
              {period.period}
              <span class="count">{period.count}</span>
            </h3>
            <div class="period-accounts">
              {#each period.by_account as account_group}
                <details>
                  <summary>
                    <span class="account-name">{account_group.account}</span>
                    <span class="count">{account_group.count}</span>
                  </summary>
                  <table>
                    <thead>
                      <tr>
                        <th>{_("Date")}</th>
                        <th>{_("Payee")}</th>
                        <th>{_("Narration")}</th>
                        <th>{_("Reason")}</th>
                        <th>{_("Actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each account_group.transactions as tx}
                        <tr>
                          <td>
                            <a href={url_for_entry(tx.entry_hash)}>{tx.date}</a>
                          </td>
                          <td>{tx.payee}</td>
                          <td>{tx.narration}</td>
                          <td>{tx.suspicious_reason || "-"}</td>
                          <td>
                            <button
                              class="unmark-btn"
                              onclick={() => handle_toggle_suspicious(tx.entry_hash, true)}
                            >
                              {_("Unmark")}
                            </button>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </details>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .suspicious-review {
    padding: 1rem;
  }

  .view-switcher {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
    align-items: center;

    button {
      padding: 0.5rem 1rem;
      border: 1px solid var(--table-border);
      background: var(--entry-background);
      cursor: pointer;
      border-radius: 4px;

      &.active {
        background: var(--table-header-background);
        color: var(--table-header-text);
      }
    }

    select {
      margin-left: 1rem;
      padding: 0.5rem;
    }
  }

  .account-groups,
  .time-groups {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .account-group,
  .time-group {
    border: 1px solid var(--table-border);
    border-radius: 4px;
    overflow: hidden;
  }

  h3 {
    margin: 0;
    padding: 0.75rem 1rem;
    background: var(--table-header-background);
    color: var(--table-header-text);
    display: flex;
    justify-content: space-between;
    align-items: center;

    .count {
      background: var(--suspicious-border, #ffc107);
      color: #000;
      padding: 0.25rem 0.5rem;
      border-radius: 12px;
      font-size: 0.8em;
    }
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.5rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--table-border);
  }

  th {
    background: var(--entry-background);
    font-weight: 600;
  }

  .unmark-btn {
    padding: 0.25rem 0.75rem;
    font-size: 0.85em;
    cursor: pointer;
    background: var(--entry-background);
    border: 1px solid var(--table-border);
    border-radius: 3px;

    &:hover {
      background: var(--journal-hover-highlight);
    }
  }

  .empty {
    text-align: center;
    padding: 2rem;
    color: var(--text-color-lighter);
  }

  .period-accounts {
    padding: 1rem;

    details {
      margin-bottom: 0.5rem;
      border: 1px solid var(--table-border);
      border-radius: 3px;

      summary {
        padding: 0.5rem 1rem;
        cursor: pointer;
        display: flex;
        justify-content: space-between;
        align-items: center;

        .account-name {
          font-weight: 500;
        }

        .count {
          background: var(--suspicious-border, #ffc107);
          color: #000;
          padding: 0.15rem 0.5rem;
          border-radius: 10px;
          font-size: 0.8em;
        }
      }

      table {
        margin: 0;
        border-top: 1px solid var(--table-border);
      }
    }
  }
</style>
