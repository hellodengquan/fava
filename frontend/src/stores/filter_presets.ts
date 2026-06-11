import { get, writable } from "svelte/store";

import {
  create_filter_preset,
  delete_filter_preset,
  get_filter_presets,
  type FilterPreset,
  type FilterPresetFilters,
  type FilterPresetPageType,
  update_filter_preset,
} from "../api/index.ts";
import type { FetchHTTPError } from "../lib/fetch.ts";
import { notify, notify_err } from "../notifications.ts";
import { router, set_query_param } from "../router.ts";
import { getURLFilters } from "./filters.ts";

/**
 * Create a FilterPresetFilters object from the current URL.
 */
export function filters_from_url(): FilterPresetFilters {
  const url = router.current;
  const filters = getURLFilters(url);
  return {
    account: filters.account,
    filter: filters.filter,
    time: filters.time,
    conversion: filters.conversion,
    interval: filters.interval,
  };
}

/**
 * Apply a FilterPresetFilters object to the current URL and navigate.
 */
export function apply_filters_to_url(filters: FilterPresetFilters): void {
  const url = new URL(router.current);
  set_query_param(url, "account", filters.account);
  set_query_param(url, "filter", filters.filter);
  set_query_param(url, "time", filters.time);
  if (filters.conversion !== "at_cost" && filters.conversion) {
    set_query_param(url, "conversion", filters.conversion);
  }
  if (filters.interval && filters.interval !== "monthly") {
    set_query_param(url, "interval", filters.interval);
  }
  if (url.href !== router.current.href) {
    router.navigate(url);
  }
}

/** Known filter-preset error codes returned from the backend. */
type FilterPresetErrorCode =
  | "name_conflict"
  | "not_found"
  | "concurrent_modification"
  | "empty_name"
  | "name_too_long"
  | "invalid_page_type"
  | "filter_preset_error";

/**
 * Extract a structured filter-preset error from a thrown value if possible.
 */
function parse_preset_error(error: unknown): {
  code: FilterPresetErrorCode;
  message: string;
  details: Record<string, unknown>;
} | null {
  if (error instanceof Error && (error as FetchHTTPError).code) {
    const http_err = error as FetchHTTPError;
    const code = (http_err.code as FilterPresetErrorCode) ?? "filter_preset_error";
    return {
      code,
      message: http_err.message,
      details: (http_err.details as Record<string, unknown>) ?? {},
    };
  }
  return null;
}

/**
 * Format a user-facing error message, enriching it with the conflicting
 * preset name or other helpful context when available.
 */
function format_preset_error_message(error: unknown, fallback: string): string {
  const parsed = parse_preset_error(error);
  if (!parsed) return fallback;

  switch (parsed.code) {
    case "name_conflict": {
      const conflicting_name = parsed.details.conflicting_name;
      const existing_id = parsed.details.existing_preset_id;
      if (typeof conflicting_name === "string") {
        return existing_id
          ? `A filter preset named "${conflicting_name}" already exists (id: ${String(existing_id)}).`
          : `A filter preset named "${conflicting_name}" already exists.`;
      }
      return "A filter preset with this name already exists.";
    }
    case "concurrent_modification":
      return (
        "The filter presets were modified in another browser tab or session. " +
        "Please reload the preset list and try again."
      );
    case "not_found":
      return "The filter preset no longer exists. It may have been deleted elsewhere.";
    case "empty_name":
      return "Preset name cannot be empty.";
    case "name_too_long":
      return "Preset name is too long (max 100 characters).";
    default:
      return fallback;
  }
}

class FilterPresetsStore {
  #presets = writable<FilterPreset[]>([]);
  #loading = writable(false);
  #current_page_type = writable<FilterPresetPageType>("all");
  /** The currently selected preset ID in the UI dropdown. */
  #selected_id = writable<string>("");

  /** Subscribe to the list of presets. */
  subscribe = this.#presets.subscribe;

  /** Subscribe to the loading state. */
  loading = { subscribe: this.#loading.subscribe };

  /** Subscribe to the currently selected preset ID. */
  selected_id = { subscribe: this.#selected_id.subscribe };

  /** Subscribe to the current page type filter. */
  current_page_type = { subscribe: this.#current_page_type.subscribe };

  /** Set the current page type for filtering presets. */
  set_page_type(page: FilterPresetPageType): void {
    this.#current_page_type.set(page);
  }

  /** Set the currently selected preset ID (called from the UI). */
  set_selected_id(id: string): void {
    this.#selected_id.set(id);
  }

  /**
   * If the selected preset has been removed or is no longer visible for the
   * current page, reset the selection to the empty default.
   */
  #maybe_clear_selection(): void {
    const current = get(this.#selected_id);
    if (!current) return;
    const visible = get(this.#presets);
    if (!visible.some((p) => p.id === current)) {
      this.#selected_id.set("");
    }
  }

  /** Load presets from the backend. */
  async load(page?: FilterPresetPageType): Promise<void> {
    this.#loading.set(true);
    try {
      const presets = await get_filter_presets(page);
      this.#presets.set(presets);
      this.#maybe_clear_selection();
    } catch (error) {
      notify_err(error, (e) =>
        format_preset_error_message(
          e,
          `Failed to load filter presets: ${e.message}`,
        ),
      );
    } finally {
      this.#loading.set(false);
    }
  }

  /** Get all presets (synchronously, from the store). */
  get_all(): FilterPreset[] {
    return get(this.#presets);
  }

  /** Find a preset by ID (synchronously). */
  find_by_id(id: string): FilterPreset | undefined {
    return get(this.#presets).find((p) => p.id === id);
  }

  /** Find a preset by name (synchronously). */
  find_by_name(name: string): FilterPreset | undefined {
    return get(this.#presets).find((p) => p.name === name);
  }

  /** Check if a name already exists among presets. */
  name_exists(name: string, exclude_id?: string): boolean {
    return get(this.#presets).some(
      (p) => p.name === name && p.id !== exclude_id,
    );
  }

  /**
   * Create a new preset.
   * @param name The preset name.
   * @param page The page type.
   * @param filters The filter parameters.
   * @returns The created preset, or null if failed.
   */
  async create(
    name: string,
    page: FilterPresetPageType,
    filters: FilterPresetFilters,
  ): Promise<FilterPreset | null> {
    const trimmed_name = name.trim();
    if (!trimmed_name) {
      notify("Preset name cannot be empty.", "error");
      return null;
    }

    // Fast local check; the authoritative check is still on the backend.
    const local_conflict = this.find_by_name(trimmed_name);
    if (local_conflict) {
      notify(
        `A filter preset named "${trimmed_name}" already exists.`,
        "error",
      );
      return null;
    }

    try {
      const preset = await create_filter_preset({
        name: trimmed_name,
        page,
        filters,
      });
      this.#presets.update((presets) => {
        const updated = [...presets, preset];
        return updated;
      });
      this.#selected_id.set(preset.id);
      notify(`Created filter preset "${trimmed_name}".`);
      return preset;
    } catch (error) {
      const message = format_preset_error_message(
        error,
        `Failed to create preset: ${(error as Error).message}`,
      );
      notify(message, "error");
      // If a conflict was detected server-side, refresh the list.
      const parsed = parse_preset_error(error);
      if (parsed?.code === "name_conflict" || parsed?.code === "concurrent_modification") {
        await this.load(page);
      }
      return null;
    }
  }

  /**
   * Rename an existing preset.
   * @param id The preset ID.
   * @param new_name The new name.
   * @returns The updated preset, or null if failed.
   */
  async rename(id: string, new_name: string): Promise<FilterPreset | null> {
    const trimmed_name = new_name.trim();
    if (!trimmed_name) {
      notify("Preset name cannot be empty.", "error");
      return null;
    }

    const existing = this.find_by_id(id);
    if (!existing) {
      notify("That filter preset no longer exists.", "error");
      return null;
    }

    if (existing.name === trimmed_name) return existing;

    // Fast local name-conflict check.
    const name_conflict = this.find_by_name(trimmed_name);
    if (name_conflict) {
      notify(
        `Cannot rename: a filter preset named "${trimmed_name}" already exists.`,
        "error",
      );
      return null;
    }

    // User confirmation.
    const confirmed = window.confirm(
      `Rename filter preset "${existing.name}" to "${trimmed_name}"?`,
    );
    if (!confirmed) return null;

    try {
      const preset = await update_filter_preset({ id, name: trimmed_name });
      this.#presets.update((presets) =>
        presets.map((p) => (p.id === id ? preset : p)),
      );
      notify(`Renamed filter preset to "${trimmed_name}".`);
      return preset;
    } catch (error) {
      const message = format_preset_error_message(
        error,
        `Failed to rename preset: ${(error as Error).message}`,
      );
      notify(message, "error");
      const parsed = parse_preset_error(error);
      if (
        parsed?.code === "name_conflict" ||
        parsed?.code === "concurrent_modification" ||
        parsed?.code === "not_found"
      ) {
        await this.load();
      }
      return null;
    }
  }

  /**
   * Update the filters of an existing preset.
   * @param id The preset ID.
   * @param filters The new filter parameters.
   * @returns The updated preset, or null if failed.
   */
  async update_filters(
    id: string,
    filters: FilterPresetFilters,
  ): Promise<FilterPreset | null> {
    const existing = this.find_by_id(id);
    if (!existing) {
      notify("That filter preset no longer exists.", "error");
      return null;
    }

    try {
      const preset = await update_filter_preset({ id, filters });
      this.#presets.update((presets) =>
        presets.map((p) => (p.id === id ? preset : p)),
      );
      notify(`Updated filter preset "${preset.name}".`);
      return preset;
    } catch (error) {
      const message = format_preset_error_message(
        error,
        `Failed to update preset: ${(error as Error).message}`,
      );
      notify(message, "error");
      const parsed = parse_preset_error(error);
      if (parsed?.code === "concurrent_modification" || parsed?.code === "not_found") {
        await this.load();
      }
      return null;
    }
  }

  /**
   * Delete a preset.
   * @param id The preset ID.
   * @returns true if deleted successfully.
   */
  async delete(id: string): Promise<boolean> {
    const existing = this.find_by_id(id);
    if (!existing) {
      notify("That filter preset no longer exists.", "error");
      return false;
    }

    const confirmed = window.confirm(
      `Delete filter preset "${existing.name}"? This action cannot be undone.`,
    );
    if (!confirmed) return false;

    try {
      await delete_filter_preset(id);
      this.#presets.update((presets) => presets.filter((p) => p.id !== id));
      // Clear selection if we just deleted the selected preset.
      if (get(this.#selected_id) === id) {
        this.#selected_id.set("");
      }
      this.#maybe_clear_selection();
      notify(`Deleted filter preset "${existing.name}".`);
      return true;
    } catch (error) {
      const message = format_preset_error_message(
        error,
        `Failed to delete preset: ${(error as Error).message}`,
      );
      notify(message, "error");
      const parsed = parse_preset_error(error);
      if (parsed?.code === "concurrent_modification" || parsed?.code === "not_found") {
        await this.load();
      }
      return false;
    }
  }

  /**
   * Apply a preset's filters to the current URL.
   *
   * If the preset was saved for a different page (or for "all" pages and
   * the caller is currently on a specific page) the user is warned that
   * the current filter state on other pages would be overwritten by
   * navigating and has to confirm before the URL is mutated.
   *
   * @param id The preset ID.
   */
  apply(id: string): void {
    const preset = this.find_by_id(id);
    if (!preset) {
      notify("That filter preset no longer exists.", "error");
      this.#maybe_clear_selection();
      return;
    }

    const current_page = get(this.#current_page_type);
    const is_cross_page =
      preset.page !== "all" &&
      current_page !== "all" &&
      preset.page !== current_page;
    const is_all_pages_preset = preset.page === "all";

    if (is_cross_page || is_all_pages_preset) {
      const target =
        preset.page === "all"
          ? "all pages that share the universal filters"
          : `the ${preset.page} page`;
      const confirmed = window.confirm(
        `Applying the filter preset "${preset.name}" will overwrite the ` +
          `current filter state for ${target}. Continue?`,
      );
      if (!confirmed) {
        // Roll back the dropdown selection – the user bailed out.
        this.#maybe_clear_selection();
        return;
      }
    }

    this.#selected_id.set(id);
    apply_filters_to_url(preset.filters);
  }
}

/** The singleton filter presets store instance. */
export const filter_presets = new FilterPresetsStore();
