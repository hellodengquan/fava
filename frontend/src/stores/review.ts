import { derived, get, writable } from "svelte/store";

import type { BeancountError, ReviewItemState, ReviewStatus } from "../api/validators.ts";
import { errors, ledgerData } from "./index.ts";
import { notify, notify_err } from "../notifications.ts";

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

interface ConflictBody {
  error?: string;
  expected_version?: number;
  got_version?: number;
  latest_data?: { version: number; data: Record<string, ReviewItemState> };
}

interface PutResult {
  version: number;
  count: number;
  applied?: number;
  message: string;
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

async function fetchReviewState(): Promise<LocalSnapshot> {
  try {
    const base = (get(ledgerData)?.base_url ?? "") || "";
    const res = await fetch(`${base}review_state/`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      throw new Error(`GET review_state failed (${res.status})`);
    }
    const payload = await res.json();
    const { data, mtime: _mtime } = payload;
    if (
      data &&
      typeof data === "object" &&
      typeof data.version === "number" &&
      data.data &&
      typeof data.data === "object"
    ) {
      return { version: data.version, data: data.data as Record<string, ReviewItemState> };
    }
    return { version: 0, data: {} };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    notify_err(msg);
    return { version: 0, data: {} };
  }
}

async function putReviewState(
  baseUrl: string,
  version: number,
  stateArray: Array<[string, unknown]>,
  etag: string | null,
): Promise<{ result: PutResult; etag: string | null; conflict: ConflictBody | null }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (etag) {
    headers["If-Match"] = etag;
  }
  const res = await fetch(`${baseUrl}review_state/`, {
    method: "PUT",
    headers,
    body: JSON.stringify({ version, state: stateArray }),
  });
  const json = await res.json().catch(() => ({}));

  if (res.status === 409) {
    return {
      result: undefined as never,
      etag: null,
      conflict: json as ConflictBody,
    };
  }

  if (!res.ok) {
    const err = json?.error || json?.data?.error || res.statusText;
    throw new Error(`PUT review_state failed (${res.status}): ${err}`);
  }

  const resultData = json.data || json;
  const resultEtag = res.headers.get("ETag");
  return {
    result: resultData as PutResult,
    etag: resultEtag,
    conflict: null,
  };
}

function createReviewStore() {
  const initial: ReviewStoreValue = {};
  const store = writable<ReviewStoreValue>(initial);
  let initialized = false;
  let lastBaseUrl = "";
  let currentVersion = 0;
  let currentEtag: string | null = null;
  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let saveInFlight = false;
  let pendingPatches: PendingPatch[] = [];
  let retryCount = 0;

  function applySnapshot(snap: LocalSnapshot, etag: string | null = null): void {
    currentVersion = snap.version;
    currentEtag = etag;
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
      const backendSnap = await fetchReviewState();
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
      fetchReviewState().then((backendSnap) => applySnapshot(backendSnap));
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
      return;
    }
    if (pendingPatches.length === 0) {
      return;
    }

    saveInFlight = true;
    const patches = pendingPatches;
    pendingPatches = [];

    const byId = new Map<string, ReviewItemState | null>();
    for (const p of patches) {
      byId.set(p.id, p.value);
    }
    const stateArray: Array<[string, unknown]> = [...byId.entries()].map(
      ([k, v]) => [k, v],
    );

    try {
      const { result, etag, conflict } = await putReviewState(
        lastBaseUrl,
        currentVersion,
        stateArray,
        currentEtag,
      );
      if (conflict) {
        saveInFlight = false;
        retryCount += 1;
        const limit = 3;
        if (retryCount >= limit) {
          pendingPatches = [...patches, ...pendingPatches];
          notify_err(`复核数据保存冲突，已达到最大重试次数 (${limit})，请刷新页面重试`);
          retryCount = 0;
          return;
        }
        // Merge: apply server latest_data as base, then re-apply client-side patches
        const latest = conflict.latest_data;
        const baseData: Record<string, ReviewItemState> =
          latest && latest.data && typeof latest.data === "object"
            ? (latest.data as Record<string, ReviewItemState>)
            : get(store);
        const baseVersion: number =
          latest && typeof latest.version === "number" ? latest.version : currentVersion;
        const merged: Record<string, ReviewItemState> = { ...baseData };
        const localState = get(store);
        const mergedPatches: PendingPatch[] = [];
        for (const [patchId, patchValue] of byId) {
          if (patchValue === null) {
            delete merged[patchId];
            mergedPatches.push({ id: patchId, value: null });
          } else {
            const prior = localState[patchId] ?? defaultState();
            const server = baseData[patchId];
            // Three-way merge (partial): take server as base, but prefer
            // client fields that are "different from what the client saw".
            // Simple heuristic: write the whole patchValue, but for any
            // field where server is already different from local prior,
            // keep the server's version of that specific field.
            const out: ReviewItemState = server ? { ...server } : { ...defaultState() };
            let changed = false;
            for (const key of ["status", "note", "explanation"] as const) {
              const priorVal = prior[key];
              const patchVal = (patchValue as ReviewItemState)[key];
              const serverVal = out[key];
              if (patchVal !== priorVal && patchVal !== serverVal) {
                // Client made a real change vs the version it had:
                // apply client change (unless server has a diverging note
                // or explanation, in which case we concatenate).
                if ((key === "note" || key === "explanation") && typeof serverVal === "string" && typeof patchVal === "string") {
                  out[key] = serverVal ? `${serverVal}\n\n${patchVal}` : patchVal;
                } else {
                  out[key] = patchVal;
                }
                changed = true;
              } else if (patchVal !== priorVal && patchVal === serverVal) {
                // No actual divergence
                changed = true;
              }
            }
            if (!changed) {
              const defaultVal = defaultState();
              const isDefault =
                out.status === defaultVal.status &&
                out.note === defaultVal.note &&
                out.explanation === defaultVal.explanation;
              if (isDefault) {
                continue;
              }
            }
            out.updated_at = new Date().toISOString();
            merged[patchId] = out;
            mergedPatches.push({ id: patchId, value: out });
          }
        }
        store.set(merged);
        currentVersion = baseVersion;
        currentEtag = etag;
        persistLocal(merged);
        pendingPatches = [...mergedPatches, ...pendingPatches];
        notify(`复核数据出现并发冲突，已自动合并 (第 ${retryCount} 次重试)`);
        saveTimer = setTimeout(() => {
          void flushPatches();
        }, 800);
        return;
      }
      currentVersion = result.version;
      currentEtag = etag;
      persistLocal(get(store));
      retryCount = 0;
      saveInFlight = false;
      if (pendingPatches.length > 0) {
        void flushPatches();
      }
    } catch (e: unknown) {
      saveInFlight = false;
      const msg = e instanceof Error ? e.message : String(e);
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
    const snap = await fetchReviewState();
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
const HISTORY_PAGE_TYPE_KEY = "fava:review-page-type";

function contextStorageKey(baseUrl: string): string {
  return `${CONTEXT_KEY_PREFIX}${baseUrl.replace(/[^a-zA-Z0-9]/g, "_")}`;
}

interface HistoryStackBridge {
  push(snap: ReviewContextSnapshot): void;
  pop(): ReviewContextSnapshot | undefined;
  peek(): ReviewContextSnapshot | undefined;
  top(): ReviewContextSnapshot;
  replaceTop(snap: ReviewContextSnapshot): void;
  clear(): void;
  takePendingRestore(): ReviewContextSnapshot | undefined;
  markHistoryList(): void;
  markHistoryDetail(): void;
  navigateToList(url: string, listCtx: ReviewContextSnapshot): void;
  navigateToDetail(url: string, detailId: string, listCtx: ReviewContextSnapshot): void;
  updateDetailHighlight(id: string, replaceUrl: string): void;
  onPopStateBackToList(handler: (snap: ReviewContextSnapshot) => void): () => void;
  backOrNavigateToList(goListDirect: () => void): void;
  get subscribe(): (
    run: (value: ReviewContextSnapshot[]) => void,
    invalidate?: (value?: ReviewContextSnapshot[]) => void,
  ) => () => void;
  update(updater: (stack: ReviewContextSnapshot[]) => ReviewContextSnapshot[]): void;
}

function createReviewContext(): HistoryStackBridge {
  type Stack = ReviewContextSnapshot[];
  const initial: Stack = [];
  const store = writable<Stack>(initial);

  let lastBaseUrl = "";
  let pendingRestore: ReviewContextSnapshot | undefined = undefined;
  const backToListHandlers: Array<(snap: ReviewContextSnapshot) => void> = [];

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

  function currentPageType(): "list" | "detail" | undefined {
    try {
      const raw = history.state?.[HISTORY_PAGE_TYPE_KEY];
      if (raw === "review-list") return "list";
      if (raw === "review-detail") return "detail";
    } catch {
      // ignore
    }
    return undefined;
  }

  function writePageType(
    type: "review-list" | "review-detail",
    replace: boolean,
    url?: string,
  ) {
    try {
      const existing = (history.state as Record<string, unknown> | null) ?? {};
      const next = { ...existing, [HISTORY_PAGE_TYPE_KEY]: type };
      if (replace) {
        history.replaceState(next, "", url);
      } else {
        history.pushState(next, "", url);
      }
    } catch {
      // ignore
    }
  }

  ledgerData.subscribe(($ledgerData) => {
    const baseUrl = $ledgerData?.base_url ?? "";
    if (baseUrl && baseUrl !== lastBaseUrl) {
      lastBaseUrl = baseUrl;
      const loaded = loadLocal(baseUrl);
      store.set(loaded);
    }
  });

  const { subscribe, set, update } = store;

  function push(snap: ReviewContextSnapshot): void {
    update((stack) => {
      const next = [...stack, snap];
      if (next.length > 200) {
        next.splice(0, next.length - 200);
      }
      persistLocal(next);
      return next;
    });
  }

  function pop(): ReviewContextSnapshot | undefined {
    let result: ReviewContextSnapshot | undefined;
    update((stack) => {
      if (stack.length === 0) {
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
    pendingRestore = undefined;
  }

  function takePendingRestore(): ReviewContextSnapshot | undefined {
    const value = pendingRestore;
    pendingRestore = undefined;
    return value;
  }

  function markHistoryList(): void {
    writePageType("review-list", true);
  }

  function markHistoryDetail(): void {
    writePageType("review-detail", true);
  }

  function navigateToList(
    url: string,
    _listCtx: ReviewContextSnapshot,
  ): void {
    location.assign(url);
  }

  function navigateToDetail(
    url: string,
    _detailId: string,
    listCtx: ReviewContextSnapshot,
  ): void {
    writePageType("review-detail", false, url);
    push(listCtx);
  }

  function updateDetailHighlight(
    _id: string,
    replaceUrl: string,
  ): void {
    writePageType("review-detail", true, replaceUrl);
  }

  function onPopStateBackToList(
    handler: (snap: ReviewContextSnapshot) => void,
  ): () => void {
    backToListHandlers.push(handler);
    return () => {
      const idx = backToListHandlers.indexOf(handler);
      if (idx >= 0) backToListHandlers.splice(idx, 1);
    };
  }

  function handleBrowserPop(_evt: PopStateEvent) {
    const nowType = currentPageType();
    const stack = get(store);

    if (nowType === "list") {
      // Pop one frame (this is the frame we saved when going into the
      // detail page we just came back from) and make it available for
      // the list component to consume on mount.
      const popped = stack.length > 0 ? [...stack].pop() : undefined;
      if (popped) {
        pendingRestore = popped;
        const trimmed = stack.slice(0, -1);
        persistLocal(trimmed);
        set(trimmed);
        for (const h of backToListHandlers) {
          try {
            h(popped);
          } catch {
            // ignore
          }
        }
      }
    }
  }

  if (typeof window !== "undefined") {
    window.addEventListener("popstate", handleBrowserPop);
  }

  function backOrNavigateToList(goListDirect: () => void): void {
    const stack = get(store);
    if (stack.length > 0 && typeof window !== "undefined") {
      history.back();
      return;
    }
    goListDirect();
  }

  return {
    subscribe,
    push,
    pop,
    peek,
    top,
    replaceTop,
    clear,
    takePendingRestore,
    markHistoryList,
    markHistoryDetail,
    navigateToList,
    navigateToDetail,
    updateDetailHighlight,
    onPopStateBackToList,
    backOrNavigateToList,
    update,
  };
}

export const review_context_stack = createReviewContext();

export const review_context = {
  subscribe: review_context_stack.subscribe,
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
