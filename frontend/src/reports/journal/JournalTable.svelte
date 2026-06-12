<script lang="ts">
  import { untrack } from "svelte";

  import { mark_suspicious, unmark_suspicious } from "../../api/index.ts";
  import { _ } from "../../i18n.ts";
  import { get_el } from "../../lib/dom.ts";
  import { shallow_equal } from "../../lib/equals.ts";
  import { log_error } from "../../log.ts";
  import { is_supported_datatransfer } from "../../modals/document-upload.ts";
  import { is_loading, loading_state } from "../../router.ts";
  import {
    journal_show,
    journal_sort,
    type JournalSort,
  } from "../../stores/journal.ts";
  import { get_account_from_url } from "../accounts/index.ts";
  import { handle_journal_click } from "./click_handler.ts";
  import JournalFilters from "./JournalFilters.svelte";
  import JournalHeaders from "./JournalHeaders.svelte";
  import type { JournalSortColumn } from "./sort.ts";
  import { sort_journal } from "./sort.ts";

  interface Props {
    all_pages?: Promise<DocumentFragment | null>[];
    initial_sort: JournalSort;
    journal: DocumentFragment;
    show_change_and_balance: boolean;
  }

  let {
    all_pages = [],
    initial_sort,
    journal,
    show_change_and_balance,
  }: Props = $props();

  let ol: HTMLOListElement | undefined = $state();

  /** Set the data attributes for drag-and-drop on dragenter */
  function ondragenter(event: DragEvent) {
    const closest_element = get_el(event.target);
    const description = closest_element?.closest(".description");
    // Get the closest `<li>` to also find the first posting account in a transaction.
    const li = description?.closest("li");
    if (
      description instanceof Element &&
      li &&
      is_supported_datatransfer(event.dataTransfer)
    ) {
      const account = [...li.querySelectorAll("a")]
        .map((a) => new URL(a.href))
        .map(get_account_from_url)
        .find((res) => res.is_ok)?.value;
      if (account != null) {
        description.setAttribute("data-account-name", account);
        description.classList.add("dragover");
        event.preventDefault();

        const date_link = description
          .closest(".journal > li")
          ?.querySelector(".datecell")
          ?.querySelector("a");
        if (date_link != null) {
          const entry_date = date_link.innerText;
          const hash = new URL(date_link.href).hash;
          if (hash.startsWith("#context-")) {
            const entry_hash = hash.slice(9);
            description.setAttribute("data-entry-date", entry_date);
            description.setAttribute("data-entry-hash", entry_hash);
          }
        }
      }
    }
  }

  async function handle_suspicious_click(event: Event): Promise<void> {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    const indicator = target.closest(".suspicious-toggle");
    if (!indicator) return;

    event.preventDefault();
    event.stopPropagation();

    const entry_hash = indicator.getAttribute("data-entry-hash");
    if (!entry_hash) return;

    const li = indicator.closest("li");
    const is_suspicious = li?.classList.contains("suspicious");

    if (is_suspicious) {
      await unmark_suspicious(entry_hash);
    } else {
      const reason = prompt(_("Reason for marking as suspicious:"), "suspicious");
      if (reason !== null) {
        await mark_suspicious(entry_hash, reason || "suspicious");
      }
    }
  }

  function handle_click(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLElement && target.closest(".suspicious-toggle")) {
      void handle_suspicious_click(event);
      return;
    }
    handle_journal_click(event);
  }
</script>

<JournalFilters />
<JournalHeaders
  disabled={$is_loading}
  {show_change_and_balance}
  set_sort_column={(column: JournalSortColumn) => {
    const sort: JournalSort = [
      column,
      shallow_equal($journal_sort, [column, "asc"]) ? "desc" : "asc",
    ];
    if (ol) {
      sort_journal(ol, sort);
      $journal_sort = sort;
    }
  }}
/>
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<ol
  class={["flex-table", "journal", ...$journal_show.map((s) => `show-${s}`)]}
  bind:this={ol}
  onclick={handle_click}
  {ondragenter}
  {@attach (node: HTMLOListElement) => {
    void journal;
    untrack(() => {
      const sort = $journal_sort;
      node.innerHTML = "";
      node.append(journal);
      // If the data is already sorted by the fetched order, we do not need to sort again
      // For the non-datewise sorts, only sort once for the initial page and once at the end.
      const needs_sorting = !shallow_equal(sort, initial_sort);
      if (needs_sorting) {
        sort_journal(node, sort);
      }
      if (all_pages.length > 0) {
        loading_state
          .run(async () => {
            for (const page of all_pages) {
              const fragment = await page;
              if (fragment) {
                node.append(fragment);
              }
            }
            if (needs_sorting) {
              sort_journal(node, sort);
            }
          })
          .catch(log_error);
      }
    });
  }}
></ol>
