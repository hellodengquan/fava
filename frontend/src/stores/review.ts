import { derived, get, writable } from "svelte/store";

import type { BeancountError, ReviewItemState, ReviewStatus } from "../api/validators.ts";
import { errors, ledgerData } from "./index.ts";

const STORAGE_KEY_PREFIX = "fava:review:";

function storageKey(baseUrl: string): string {
  return `${STORAGE_KEY_PREFIX}${baseUrl.replace(/[^a-zA-Z0-9]/g, "_")}`;
}

function getErrorId(error: BeancountError): string {
  const src = error.source
    ? `${error.source.filename}:${error.source.lineno}`
    : "no-source";
  return `${error.type}:${src}:${error.message}`;
}

function loadFromStorage(baseUrl: string): Record<string, ReviewItemState> {
  try {
    const key = storageKey(baseUrl);
    const raw = localStorage.getItem(key);
    if (raw) {
      return JSON.parse(raw);
    }
  } catch {
    // ignore
  }
  return {};
}

function saveToStorage(baseUrl: string, data: Record<string, ReviewItemState>): void {
  try {
    const key = storageKey(baseUrl);
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // ignore
  }
}

function nowIso(): string {
  return new Date().toISOString();
}

function defaultState(): ReviewItemState {
  return {
    status: "pending",
    note: "",
    explanation: "",
    updated_at: nowIso(),
  };
}

type ReviewStoreValue = Record<string, ReviewItemState>;

function createReviewStore() {
  const initial: ReviewStoreValue = {};
  const store = writable<ReviewStoreValue>(initial);
  let initialized = false;
  let lastBaseUrl = "";

  function ensureInit() {
    if (initialized) return;
    const $ledgerData = get(ledgerData);
    const baseUrl = $ledgerData?.base_url ?? "";
    if (baseUrl) {
      lastBaseUrl = baseUrl;
      store.set(loadFromStorage(baseUrl));
      initialized = true;
    }
  }

  ledgerData.subscribe(($ledgerData) => {
    const baseUrl = $ledgerData?.base_url ?? "";
    if (baseUrl && baseUrl !== lastBaseUrl) {
      lastBaseUrl = baseUrl;
      store.set(loadFromStorage(baseUrl));
      initialized = true;
    }
  });

  const { subscribe, set, update } = store;

  function persist(value: ReviewStoreValue) {
    if (lastBaseUrl) {
      saveToStorage(lastBaseUrl, value);
    }
  }

  function getState(id: string): ReviewItemState {
    ensureInit();
    const all = get(store);
    return all[id] ?? defaultState();
  }

  function setState(
    id: string,
    changes: Partial<ReviewItemState>,
  ): void {
    ensureInit();
    update((all) => {
      const current = all[id] ?? defaultState();
      const next: ReviewItemState = {
        ...current,
        ...changes,
        updated_at: nowIso(),
      };
      const result = { ...all, [id]: next };
      persist(result);
      return result;
    });
  }

  function setStatus(id: string, status: ReviewStatus): void {
    setState(id, { status });
  }

  function setNote(id: string, note: string): void {
    setState(id, { note });
  }

  function setExplanation(id: string, explanation: string): void {
    setState(id, { explanation });
  }

  function skip(id: string): void {
    setStatus(id, "skipped");
  }

  function explain(id: string, explanation: string): void {
    setState(id, { status: "explained", explanation });
  }

  function reset(id: string): void {
    update((all) => {
      const { [id]: _removed, ...rest } = all;
      persist(rest);
      return rest;
    });
  }

  return {
    subscribe,
    ensureInit,
    getState,
    setState,
    setStatus,
    setNote,
    setExplanation,
    skip,
    explain,
    reset,
  };
}

export const review_store = createReviewStore();

export interface EnrichedError {
  readonly error: BeancountError;
  readonly id: string;
  readonly state: ReviewItemState;
}

export const enriched_errors = derived(
  [errors, review_store, ledgerData],
  ([$errors, _review, $ledgerData]) => {
    void $ledgerData;
    review_store.ensureInit();
    return $errors.map<EnrichedError>((error) => {
      const id = getErrorId(error);
      const state = review_store.getState(id);
      return { error, id, state };
    });
  },
);

export const review_stats = derived(enriched_errors, ($list) => {
  const total = $list.length;
  let pending = 0;
  let skipped = 0;
  let explained = 0;
  for (const item of $list) {
    if (item.state.status === "pending") pending++;
    else if (item.state.status === "skipped") skipped++;
    else if (item.state.status === "explained") explained++;
  }
  return { total, pending, skipped, explained };
});

export function urlForReviewList(): string {
  return "review/";
}

export function urlForReviewDetail(id: string): string {
  return `review/${encodeURIComponent(id)}/`;
}

export function getErrorIdExported(error: BeancountError): string {
  return getErrorId(error);
}
