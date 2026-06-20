import { derived, get, writable } from "svelte/store";

import type { BeancountError, ReviewItemState, ReviewStatus } from "../api/validators.ts";
import { get_review_state, put_review_state } from "../api/index.ts";
import { notify, notify_err } from "../notifications.ts";
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

interface LocalSnapshot {
  version: number;
  data: Record<string, ReviewItemState>;
}

function loadFromStorage(baseUrl: string): LocalSnapshot {
  try {
    const key = storageKey(baseUrl);
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && "data" in parsed) {
        return {
          version: Number(parsed.version) || 0,
          data: parsed.data ?? {},
        };
      }
    }
  } catch {
    // ignore
  }
  return { version: 0, data: {} };
}

function saveToStorage(baseUrl: string, snap: LocalSnapshot): void {
  try {
    const key = storageKey(baseUrl);
    localStorage.setItem(key, JSON.stringify(snap));
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

interface PendingPatch {
  id: string;
  value: ReviewItemState | null;
}

function createReviewStore() {
  const initial: ReviewStoreValue = {};
  const store = writable<ReviewStoreValue>(initial);
  let initialized = false;
  let lastBaseUrl = "";
  let currentVersion = 0;
  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let saveInFlight = false;
  let pendingPatches: PendingPatch[] = [];
  let retryCount = 0;

  async function loadFromBackend(): Promise<LocalSnapshot> {
    try {
      const envelope = await get_review_state();
      return { version: envelope.version ?? 0, data: envelope.data ?? {} };
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      notify_err(msg);
      return { version: 0, data: {} };
    }
  }

  function applySnapshot(snap: LocalSnapshot): void {
    currentVersion = snap.version;
    store.set(snap.data);
    if (lastBaseUrl) {
      saveToStorage(lastBaseUrl, snap);
    }
  }

  async function ensureInit() {
    if (initialized) return;
    const $ledgerData = get(ledgerData);
    const baseUrl = $ledgerData?.base_url ?? "";
    if (baseUrl) {
      lastBaseUrl = baseUrl;
      const localSnap = loadFromStorage(baseUrl);
      currentVersion = localSnap.version;
      store.set(localSnap.data);
      initialized = true;
      const backendSnap = await loadFromBackend();
      applySnapshot(backendSnap);
    }
  }

  ledgerData.subscribe(($ledgerData) => {
    const baseUrl = $ledgerData?.base_url ?? "";
    if (baseUrl && baseUrl !== lastBaseUrl) {
      lastBaseUrl = baseUrl;
      initialized = true;
      const localSnap = loadFromStorage(baseUrl);
      currentVersion = localSnap.version;
      store.set(localSnap.data);
      loadFromBackend().then((backendSnap) => applySnapshot(backendSnap));
    }
  });

  const { subscribe, set, update } = store;

  function persistLocal(value: ReviewStoreValue) {
    if (lastBaseUrl) {
      saveToStorage(lastBaseUrl, { version: currentVersion, data: value });
    }
  }

  async function flushPatches(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    if (saveInFlight) {
      // will be picked up by the in-flight flush's retry chain
      return;
    }
    if (pendingPatches.length === 0) {
      return;
    }

    saveInFlight = true;
    const patches = pendingPatches;
    pendingPatches = [];

    // Apply server-side merge semantics: dedupe by id, keep last patch for each id.
    const byId = new Map<string, ReviewItemState | null>();
    for (const p of patches) {
      byId.set(p.id, p.value);
    }
    const stateArray: Array<[string, unknown]> = [...byId.entries()].map(
      ([k, v]) => [k, v],
    );

    try {
      const resp = await put_review_state({
        version: currentVersion,
        state: stateArray,
      });
      currentVersion = resp.version;
      persistLocal(get(store));
      retryCount = 0;
      saveInFlight = false;
      // If more patches accumulated during the request, flush them now.
      if (pendingPatches.length > 0) {
        void flushPatches();
      }
    } catch (e: unknown) {
      saveInFlight = false;
      const msg = e instanceof Error ? e.message : String(e);

      // Detect version mismatch: re-read server state, merge client patches,
      // then retry once automatically.
      const isVersionMismatch =
        msg.includes("version mismatch") ||
        msg.includes("Version mismatch") ||
        msg.includes("409");

      if (isVersionMismatch && retryCount < 2) {
        retryCount++;
        notify(
          `版本冲突，正在自动合并并重试 (${retryCount}/2)...`,
          "info",
        );
        // Re-add these patches to the front of pending queue so they are retried.
        pendingPatches = [...patches, ...pendingPatches];
        const fresh = await loadFromBackend();
        // Merge in-memory state against fresh server state using updated_at precedence.
        const serverData = fresh.data;
        const clientData = get(store);
        const merged: Record<string, ReviewItemState> = { ...serverData };
        for (const p of patches) {
          const serverValue = serverData[p.id];
          const clientValue = clientData[p.id] ?? defaultState();
          if (p.value === null) {
            // Client requested deletion; keep deletion unless server has newer data
            if (
              !serverValue ||
              new Date(clientValue.updated_at) >= new Date(serverValue.updated_at)
            ) {
              delete merged[p.id];
            } else {
              merged[p.id] = serverValue;
            }
          } else {
            if (
              !serverValue ||
              new Date(clientValue.updated_at) >= new Date(serverValue.updated_at)
            ) {
              merged[p.id] = clientValue;
            } else {
              merged[p.id] = serverValue;
            }
          }
        }
        // Also include any server-only entries that were not touched in patches
        for (const [k, v] of Object.entries(serverData)) {
          if (!(k in merged) && !byId.has(k)) {
            merged[k] = v;
          }
        }
        applySnapshot({ version: fresh.version, data: merged });
        void flushPatches();
        return;
      }

      // Hard failure: restore patches to the front of the queue and
      // schedule a retry after a few seconds.
      pendingPatches = [...patches, ...pendingPatches];
      notify_err(`复核数据保存失败：${msg}`);
      retryCount = 0;
      saveTimer = setTimeout(() => {
        void flushPatches();
      }, 3000);
    }
  }

  function persistBackend(patches: PendingPatch[]) {
    pendingPatches = [...pendingPatches, ...patches];
    if (saveTimer) {
      clearTimeout(saveTimer);
    }
    saveTimer = setTimeout(() => {
      void flushPatches();
    }, 500);
  }

  function persist(value: ReviewStoreValue, patches: PendingPatch[]) {
    persistLocal(value);
    persistBackend(patches);
  }

  function getState(id: string): ReviewItemState {
    const all = get(store);
    return all[id] ?? defaultState();
  }

  function setState(
    id: string,
    changes: Partial<ReviewItemState>,
  ): void {
    update((all) => {
      const current = all[id] ?? defaultState();
      const next: ReviewItemState = {
        ...current,
        ...changes,
        updated_at: nowIso(),
      };
      const result = { ...all, [id]: next };
      persist(result, [{ id, value: next }]);
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
      persist(rest, [{ id, value: null }]);
      return rest;
    });
  }

  function batchSkip(ids: string[]): void {
    if (ids.length === 0) return;
    update((all) => {
      const result = { ...all };
      const ts = nowIso();
      const patches: PendingPatch[] = [];
      for (const id of ids) {
        const current = result[id] ?? defaultState();
        const next = { ...current, status: "skipped", updated_at: ts };
        result[id] = next;
        patches.push({ id, value: next });
      }
      persist(result, patches);
      return result;
    });
  }

  function batchExplain(ids: string[], explanation: string): void {
    if (ids.length === 0) return;
    update((all) => {
      const result = { ...all };
      const ts = nowIso();
      const patches: PendingPatch[] = [];
      for (const id of ids) {
        const current = result[id] ?? defaultState();
        const next = {
          ...current,
          status: "explained",
          explanation,
          updated_at: ts,
        };
        result[id] = next;
        patches.push({ id, value: next });
      }
      persist(result, patches);
      return result;
    });
  }

  function batchNote(ids: string[], note: string): void {
    if (ids.length === 0) return;
    update((all) => {
      const result = { ...all };
      const ts = nowIso();
      const patches: PendingPatch[] = [];
      for (const id of ids) {
        const current = result[id] ?? defaultState();
        const next = { ...current, note, updated_at: ts };
        result[id] = next;
        patches.push({ id, value: next });
      }
      persist(result, patches);
      return result;
    });
  }

  function batchReset(ids: string[]): void {
    if (ids.length === 0) return;
    update((all) => {
      const result = { ...all };
      const patches: PendingPatch[] = [];
      for (const id of ids) {
        delete result[id];
        patches.push({ id, value: null });
      }
      persist(result, patches);
      return result;
    });
  }

  async function forceReload(): Promise<void> {
    if (!initialized) {
      await ensureInit();
      return;
    }
    const snap = await loadFromBackend();
    applySnapshot(snap);
  }

  function getCurrentVersion(): number {
    return currentVersion;
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
    batchSkip,
    batchExplain,
    batchNote,
    batchReset,
    forceReload,
    getCurrentVersion,
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
    void _review;
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

export interface ReviewContextSnapshot {
  readonly highlightId: string | null;
  readonly scrollTop: number;
  readonly filterStatus: string;
  readonly filterType: string;
  readonly searchText: string;
}

function defaultContext(): ReviewContextSnapshot {
  return {
    highlightId: null,
    scrollTop: 0,
    filterStatus: "all",
    filterType: "all",
    searchText: "",
  };
}

const CONTEXT_KEY_PREFIX = "fava:review-ctx:";

function contextStorageKey(baseUrl: string): string {
  return `${CONTEXT_KEY_PREFIX}${baseUrl.replace(/[^a-zA-Z0-9]/g, "_")}`;
}

function createReviewContext() {
  type Stack = ReviewContextSnapshot[];
  const initial: Stack = [];
  const store = writable<Stack>(initial);

  let lastBaseUrl = "";

  function persistLocal(stack: Stack) {
    if (lastBaseUrl) {
      try {
        localStorage.setItem(
          contextStorageKey(lastBaseUrl),
          JSON.stringify(stack),
        );
      } catch {
        // ignore
      }
    }
  }

  function loadLocal(baseUrl: string): Stack {
    try {
      const raw = localStorage.getItem(contextStorageKey(baseUrl));
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed.filter(
            (s) => s && typeof s === "object",
          ) as Stack;
        }
      }
    } catch {
      // ignore
    }
    return [];
  }

  ledgerData.subscribe(($ledgerData) => {
    const baseUrl = $ledgerData?.base_url ?? "";
    if (baseUrl && baseUrl !== lastBaseUrl) {
      lastBaseUrl = baseUrl;
      store.set(loadLocal(baseUrl));
    }
  });

  const { subscribe, set, update } = store;

  function push(snap: ReviewContextSnapshot): void {
    update((stack) => {
      const next = [...stack, snap];
      // Cap stack depth to prevent unbounded growth
      if (next.length > 50) {
        next.splice(0, next.length - 50);
      }
      persistLocal(next);
      return next;
    });
  }

  function pop(): ReviewContextSnapshot | undefined {
    let result: ReviewContextSnapshot | undefined;
    update((stack) => {
      if (stack.length === 0) {
        result = undefined;
        return stack;
      }
      const next = [...stack];
      result = next.pop();
      persistLocal(next);
      return next;
    });
    return result;
  }

  function peek(): ReviewContextSnapshot | undefined {
    const stack = get(store);
    return stack[stack.length - 1];
  }

  function top(): ReviewContextSnapshot {
    return peek() ?? defaultContext();
  }

  function replaceTop(snap: ReviewContextSnapshot): void {
    update((stack) => {
      if (stack.length === 0) {
        const next = [snap];
        persistLocal(next);
        return next;
      }
      const next = [...stack];
      next[next.length - 1] = snap;
      persistLocal(next);
      return next;
    });
  }

  function clear(): void {
    const next: Stack = [];
    persistLocal(next);
    set(next);
  }

  return {
    subscribe,
    push,
    pop,
    peek,
    top,
    replaceTop,
    clear,
  };
}

export const review_context_stack = createReviewContext();

/**
 * @deprecated Use `review_context_stack` instead (push/pop/top pattern).
 * This is kept for backward compatibility with existing consumers.
 */
export const review_context = {
  subscribe: review_context_stack.subscribe as unknown as typeof review_context_stack.subscribe,
  set(value: ReviewContextSnapshot) {
    review_context_stack.replaceTop(value);
  },
  update(fn: (ctx: ReviewContextSnapshot) => ReviewContextSnapshot) {
    review_context_stack.update((stack) => {
      const current = stack[stack.length - 1] ?? defaultContext();
      const next = fn(current);
      if (stack.length === 0) {
        return [next];
      }
      const copy = [...stack];
      copy[copy.length - 1] = next;
      return copy;
    });
  },
} as const;
