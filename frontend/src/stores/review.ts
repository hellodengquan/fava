import { derived, get, writable } from "svelte/store";

import type { BeancountError, ReviewItemState, ReviewStatus } from "../api/validators.ts";
import { errors, ledgerData } from "./index.ts";
import { notify, notify_err } from "../notifications.ts";

const STORAGE_KEY_PREFIX = "fava:review:";
const REVIEW_BROADCAST_CHANNEL = "fava-review-state-sync";
const DEFAULT_BATCH_LIMIT = 500;
const ETAG_RE = /^"review-v(\d+)"$/;

function etagForVersion(version: number): string {
  return `"review-v${version}"`;
}

function parseEtagVersion(etag: string | null): number | null {
  if (!etag) return null;
  const m = etag.match(ETAG_RE);
  return m ? Number(m[1]) : null;
}

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
  limit?: number;
  message: string;
}

class ReviewPutError extends Error {
  readonly status: number;
  readonly body: any;
  constructor(status: number, message: string, body: any) {
    super(message);
    this.status = status;
    this.body = body;
    this.name = "ReviewPutError";
  }
}

class ReviewPreconditionError extends ReviewPutError {
  constructor(message: string, body: any) {
    super(428, message, body);
    this.name = "ReviewPreconditionError";
  }
}

class ReviewBatchTooLargeError extends ReviewPutError {
  readonly size: number;
  readonly limit: number;
  constructor(message: string, body: any) {
    super(413, message, body);
    this.name = "ReviewBatchTooLargeError";
    this.size = Number(body?.size) || 0;
    this.limit = Number(body?.limit) || DEFAULT_BATCH_LIMIT;
  }
}

class ReviewConflictError extends ReviewPutError {
  readonly conflictBody: ConflictBody;
  constructor(message: string, body: ConflictBody) {
    super(409, message, body);
    this.name = "ReviewConflictError";
    this.conflictBody = body;
  }
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

async function fetchReviewState(): Promise<{ snapshot: LocalSnapshot; etag: string | null }> {
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
    const etag = res.headers.get("ETag");
    if (
      data &&
      typeof data === "object" &&
      typeof data.version === "number" &&
      data.data &&
      typeof data.data === "object"
    ) {
      return {
        snapshot: { version: data.version, data: data.data as Record<string, ReviewItemState> },
        etag,
      };
    }
    return { snapshot: { version: 0, data: {} }, etag };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    notify_err(msg);
    return { snapshot: { version: 0, data: {} }, etag: null };
  }
}

async function putReviewState(
  baseUrl: string,
  version: number,
  stateArray: Array<[string, unknown]>,
  etag: string | null,
): Promise<{ result: PutResult; etag: string | null }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  // Always send If-Match: derive from version if ETag missing.
  const effectiveEtag = etag ?? etagForVersion(version);
  headers["If-Match"] = effectiveEtag;
  const res = await fetch(`${baseUrl}review_state/`, {
    method: "PUT",
    headers,
    body: JSON.stringify({ version, state: stateArray }),
  });
  const json = await res.json().catch(() => ({}));
  const errMsg = json?.error || json?.data?.error || res.statusText;

  if (res.status === 409) {
    throw new ReviewConflictError(
      `版本冲突：${errMsg || "concurrent update"}`,
      json as ConflictBody,
    );
  }
  if (res.status === 428) {
    throw new ReviewPreconditionError(
      errMsg || "缺少 If-Match 头，需要先获取最新版本",
      json,
    );
  }
  if (res.status === 413) {
    throw new ReviewBatchTooLargeError(
      errMsg || "批量过大，需要拆分",
      json,
    );
  }

  if (!res.ok) {
    throw new ReviewPutError(
      res.status,
      `PUT review_state failed (${res.status}): ${errMsg}`,
      json,
    );
  }

  const resultData = json.data || json;
  const resultEtag = res.headers.get("ETag");
  return {
    result: resultData as PutResult,
    etag: resultEtag,
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
  let currentServerLimit: number = DEFAULT_BATCH_LIMIT;

  let channel: BroadcastChannel | null = null;
  let syncAttached = false;

  function attachMultiTabSync(): void {
    if (syncAttached || typeof window === "undefined") return;
    syncAttached = true;

    if (typeof BroadcastChannel !== "undefined") {
      try {
        channel = new BroadcastChannel(REVIEW_BROADCAST_CHANNEL);
        channel.addEventListener("message", (ev) => {
          const msg = ev.data as
            | { type: "review_saved"; version: number; from: string }
            | undefined;
          if (msg?.type === "review_saved" && msg.from !== syncSourceId) {
            // Non-authoritative: fetch latest snapshot without clobbering
            // local pending patches (they will be merged on next flush).
            void pullRemoteSnapshot(msg.version);
          }
        });
      } catch {
        channel = null;
      }
    }

    window.addEventListener("storage", (ev) => {
      if (!ev.key || !lastBaseUrl) return;
      const myStorageKeys = [storageKey(lastBaseUrl), contextStorageKey(lastBaseUrl)];
      if (ev.key === storageKey(lastBaseUrl) || myStorageKeys.includes(ev.key)) {
        void pullRemoteSnapshot();
      }
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        void pullRemoteSnapshot();
      }
    });
  }

  const syncSourceId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;

  function broadcastSaved(version: number): void {
    try {
      if (channel && typeof channel.postMessage === "function") {
        channel.postMessage({
          type: "review_saved",
          version,
          from: syncSourceId,
        });
      }
    } catch {
      // ignore broadcast failures
    }
  }

  async function pullRemoteSnapshot(
    expectedMinimumVersion?: number,
  ): Promise<void> {
    if (saveInFlight) return;
    const priorVersion = currentVersion;
    const { snapshot, etag } = await fetchReviewState();
    if (
      typeof expectedMinimumVersion === "number" &&
      snapshot.version < expectedMinimumVersion
    ) {
      return;
    }
    if (snapshot.version <= priorVersion) {
      return;
    }
    const serverVersion = snapshot.version;
    const serverData = snapshot.data;
    // Re-apply any pending local patches on top of the fresh server
    // snapshot, so locally-edited dirty fields are not lost.
    const byId = new Map<string, ReviewItemState | null>();
    for (const p of pendingPatches) {
      byId.set(p.id, p.value);
    }
    const localData = get(store);
    const merged: Record<string, ReviewItemState> = { ...serverData };
    const newPending: PendingPatch[] = [];
    for (const [patchId, patchValue] of byId) {
      if (patchValue === null) {
        delete merged[patchId];
        newPending.push({ id: patchId, value: null });
      } else {
        const prior = localData[patchId] ?? defaultState();
        const server = serverData[patchId];
        const out: ReviewItemState = server ? { ...server } : { ...defaultState() };
        let changed = false;
        for (const key of ["status", "note", "explanation"] as const) {
          const priorVal = prior[key];
          const patchVal = (patchValue as ReviewItemState)[key];
          const serverVal = out[key];
          if (patchVal !== priorVal && patchVal !== serverVal) {
            if ((key === "note" || key === "explanation") && typeof serverVal === "string" && typeof patchVal === "string") {
              out[key] = serverVal ? `${serverVal}\n\n${patchVal}` : patchVal;
            } else {
              out[key] = patchVal;
            }
            changed = true;
          } else if (patchVal !== priorVal && patchVal === serverVal) {
            changed = true;
          }
        }
        if (!changed) continue;
        out.updated_at = new Date().toISOString();
        merged[patchId] = out;
        newPending.push({ id: patchId, value: out });
      }
    }
    currentVersion = serverVersion;
    currentEtag = etag;
    store.set(merged);
    pendingPatches = newPending;
    persistLocal(merged);
    notify(`已从其他标签页同步复核状态（v${serverVersion}）`);
  }

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
      attachMultiTabSync();
      const { snapshot, etag } = await fetchReviewState();
      applySnapshot(snapshot, etag);
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
      attachMultiTabSync();
      fetchReviewState().then(({ snapshot, etag }) => applySnapshot(snapshot, etag));
    }
  });

  const { subscribe, set, update } = store;

  function persistLocal(value: ReviewStoreValue) {
    if (lastBaseUrl) {
      saveToStorage(lastBaseUrl, { version: currentVersion, data: value });
    }
  }

  function mergeConflictOnTop(
    serverBase: Record<string, ReviewItemState>,
    baseVersion: number,
    baseEtag: string | null,
    patchesById: Map<string, ReviewItemState | null>,
    originalPatches: PendingPatch[],
  ): PendingPatch[] {
    const merged: Record<string, ReviewItemState> = { ...serverBase };
    const localState = get(store);
    const mergedPatches: PendingPatch[] = [];
    for (const [patchId, patchValue] of patchesById) {
      if (patchValue === null) {
        delete merged[patchId];
        mergedPatches.push({ id: patchId, value: null });
      } else {
        const prior = localState[patchId] ?? defaultState();
        const server = serverBase[patchId];
        const out: ReviewItemState = server ? { ...server } : { ...defaultState() };
        let changed = false;
        for (const key of ["status", "note", "explanation"] as const) {
          const priorVal = prior[key];
          const patchVal = (patchValue as ReviewItemState)[key];
          const serverVal = out[key];
          if (patchVal !== priorVal && patchVal !== serverVal) {
            if ((key === "note" || key === "explanation") && typeof serverVal === "string" && typeof patchVal === "string") {
              out[key] = serverVal ? `${serverVal}\n\n${patchVal}` : patchVal;
            } else {
              out[key] = patchVal;
            }
            changed = true;
          } else if (patchVal !== priorVal && patchVal === serverVal) {
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
    currentEtag = baseEtag;
    persistLocal(merged);
    void originalPatches;
    return mergedPatches;
  }

  async function sendOneBatch(
    stateArray: Array<[string, unknown]>,
    byId: Map<string, ReviewItemState | null>,
    originalPatches: PendingPatch[],
  ): Promise<"ok" | "conflict" | "precondition" | "split"> {
    const { result, etag } = await putReviewState(
      lastBaseUrl,
      currentVersion,
      stateArray,
      currentEtag,
    );
    currentVersion = result.version;
    currentEtag = etag;
    if (typeof result.limit === "number") {
      currentServerLimit = result.limit;
    }
    persistLocal(get(store));
    broadcastSaved(result.version);
    retryCount = 0;
    void byId;
    void originalPatches;
    return "ok";
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

    try {
      const entries = [...byId.entries()];
      const batches: Array<[string, unknown][]> = [];
      const effectiveLimit = Math.max(1, currentServerLimit);
      for (let i = 0; i < entries.length; i += effectiveLimit) {
        batches.push(entries.slice(i, i + effectiveLimit).map(([k, v]) => [k, v]));
      }

      for (let bi = 0; bi < batches.length; bi++) {
        const stateArray = batches[bi];
        try {
          await sendOneBatch(stateArray, byId, patches);
        } catch (e: unknown) {
          if (e instanceof ReviewBatchTooLargeError) {
            // Server has a smaller limit than we thought; re-split this
            // batch and retry exactly this shard (earlier shards already ok).
            currentServerLimit = Math.max(1, Math.min(e.limit, currentServerLimit));
            const subBatches: Array<[string, unknown][]> = [];
            for (let i = 0; i < stateArray.length; i += currentServerLimit) {
              subBatches.push(stateArray.slice(i, i + currentServerLimit));
            }
            batches.splice(bi, 1, ...subBatches);
            bi -= 1;
            notify_err(
              `复核批次过大，已按 ${currentServerLimit} 条/批拆分后重试`,
            );
            continue;
          }
          if (e instanceof ReviewPreconditionError) {
            // If-Match mismatch due to stale local ETag/version;
            // pull a fresh snapshot, merge patches back in, then
            // retry the whole remaining queue once.
            retryCount += 1;
            if (retryCount >= 3) {
              throw new Error("Precondition 重试次数过多，请刷新页面重试");
            }
            const { snapshot, etag } = await fetchReviewState();
            const rePending = mergeConflictOnTop(
              snapshot.data,
              snapshot.version,
              etag,
              byId,
              patches,
            );
            pendingPatches = [...rePending, ...pendingPatches, ...batches.slice(bi + 1).flatMap((b) => b.map(([k, v]) => ({ id: k, value: v as ReviewItemState | null })))];
            notify(`重新获取最新复核版本（v${snapshot.version}）后重试保存`);
            saveInFlight = false;
            saveTimer = setTimeout(() => {
              void flushPatches();
            }, 800);
            return;
          }
          if (e instanceof ReviewConflictError) {
            retryCount += 1;
            const limit = 3;
            if (retryCount >= limit) {
              throw new Error(`冲突重试次数达到 ${limit}，请刷新页面重试`);
            }
            const conflict = e.conflictBody;
            const latest = conflict.latest_data;
            const baseData: Record<string, ReviewItemState> =
              latest && latest.data && typeof latest.data === "object"
                ? (latest.data as Record<string, ReviewItemState>)
                : get(store);
            const baseVersion: number =
              latest && typeof latest.version === "number" ? latest.version : currentVersion;
            // Re-compose: re-push the current failing batch + any later
            // batches in this flush + anything queued while we were running
            // into the front of pendingPatches after they are merged on top.
            const remaining = new Map<string, ReviewItemState | null>(byId);
            for (const later of batches.slice(bi + 1)) {
              for (const [k, v] of later) {
                remaining.set(k, v as ReviewItemState | null);
              }
            }
            const rePending = mergeConflictOnTop(
              baseData,
              baseVersion,
              null,
              remaining,
              patches,
            );
            pendingPatches = [...rePending, ...pendingPatches];
            notify(`复核数据出现并发冲突，已自动合并（第 ${retryCount} 次重试）`);
            saveInFlight = false;
            saveTimer = setTimeout(() => {
              void flushPatches();
            }, 800);
            return;
          }
          throw e;
        }
      }

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
