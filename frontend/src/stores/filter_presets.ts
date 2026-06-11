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

class FilterPresetsStore {
  #presets = writable<FilterPreset[]>([]);
  #loading = writable(false);
  #current_page_type = writable<FilterPresetPageType>("all");

  /** Subscribe to the list of presets. */
  subscribe = this.#presets.subscribe;

  /** Subscribe to the loading state. */
  loading = { subscribe: this.#loading.subscribe };

  /** Subscribe to the current page type filter. */
  current_page_type = { subscribe: this.#current_page_type.subscribe };

  /** Set the current page type for filtering presets. */
  set_page_type(page: FilterPresetPageType): void {
    this.#current_page_type.set(page);
  }

  /** Load presets from the backend. */
  async load(page?: FilterPresetPageType): Promise<void> {
    this.#loading.set(true);
    try {
      const presets = await get_filter_presets(page);
      this.#presets.set(presets);
    } catch (error) {
      notify_err(error, (e) => `Failed to load filter presets: ${e.message}`);
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
      notify_err(new Error("Preset name cannot be empty."));
      return null;
    }

    // Check for name conflict locally first
    if (this.name_exists(trimmed_name)) {
      notify_err(
        new Error(`A filter preset named "${trimmed_name}" already exists.`),
      );
      return null;
    }

    try {
      const preset = await create_filter_preset({
        name: trimmed_name,
        page,
        filters,
      });
      this.#presets.update((presets) => [...presets, preset]);
      notify(`Created filter preset "${trimmed_name}".`);
      return preset;
    } catch (error) {
      notify_err(error, (e) => `Failed to create preset: ${e.message}`);
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
      notify_err(new Error("Preset name cannot be empty."));
      return null;
    }

    // Check for name conflict locally first
    if (this.name_exists(trimmed_name, id)) {
      notify_err(
        new Error(`A filter preset named "${trimmed_name}" already exists.`),
      );
      return null;
    }

    // Confirm if name already exists
    const existing = this.find_by_id(id);
    if (existing && existing.name !== trimmed_name) {
      const confirmed = window.confirm(
        `Rename filter preset "${existing.name}" to "${trimmed_name}"?`,
      );
      if (!confirmed) return null;
    }

    try {
      const preset = await update_filter_preset({ id, name: trimmed_name });
      this.#presets.update((presets) =>
        presets.map((p) => (p.id === id ? preset : p)),
      );
      notify(`Renamed filter preset to "${trimmed_name}".`);
      return preset;
    } catch (error) {
      notify_err(error, (e) => `Failed to rename preset: ${e.message}`);
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
    if (!existing) return null;

    try {
      const preset = await update_filter_preset({ id, filters });
      this.#presets.update((presets) =>
        presets.map((p) => (p.id === id ? preset : p)),
      );
      notify(`Updated filter preset "${preset.name}".`);
      return preset;
    } catch (error) {
      notify_err(error, (e) => `Failed to update preset: ${e.message}`);
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
    if (!existing) return false;

    const confirmed = window.confirm(
      `Delete filter preset "${existing.name}"? This action cannot be undone.`,
    );
    if (!confirmed) return false;

    try {
      await delete_filter_preset(id);
      this.#presets.update((presets) => presets.filter((p) => p.id !== id));
      notify(`Deleted filter preset "${existing.name}".`);
      return true;
    } catch (error) {
      notify_err(error, (e) => `Failed to delete preset: ${e.message}`);
      return false;
    }
  }

  /**
   * Apply a preset's filters to the current URL.
   * @param id The preset ID.
   */
  apply(id: string): void {
    const preset = this.find_by_id(id);
    if (!preset) {
      notify_err(new Error(`Filter preset "${id}" not found.`));
      return;
    }
    apply_filters_to_url(preset.filters);
  }
}

/** The singleton filter presets store instance. */
export const filter_presets = new FilterPresetsStore();
