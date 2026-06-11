import { writable, derived, get } from "svelte/store";

import type { Document } from "../entries/index.ts";
import type { Transaction } from "../entries/index.ts";
import type { ReviewStatus } from "../lib/review.ts";
import { getReviewStatus, getReviewInfo, getPendingDocuments, groupByCategory } from "../lib/review.ts";
import { accounts } from "./index.ts";
import { put_update_review_status, put_clear_review_status } from "../api/index.ts";
import { router } from "../router.ts";
import { notify, notify_err } from "../notifications.ts";

export const reviewTransactions = writable<Transaction[]>([]);

export const reviewDocuments = writable<Document[]>([]);

interface ReviewState {
  selectedDocument: Document | null;
  isLoading: boolean;
}

const initialState: ReviewState = {
  selectedDocument: null,
  isLoading: false,
};

function createReviewStore() {
  const { subscribe, set, update } = writable<ReviewState>(initialState);

  return {
    subscribe,
    set,
    selectDocument: (doc: Document | null) => {
      update((state) => ({ ...state, selectedDocument: doc }));
    },
    setLoading: (isLoading: boolean) => {
      update((state) => ({ ...state, isLoading }));
    },
    reset: () => set(initialState),
  };
}

export const reviewStore = createReviewStore();

export const pendingDocuments = derived(
  [reviewDocuments, reviewTransactions, accounts],
  ([$docs, $txns, $accounts]) => {
    return getPendingDocuments($docs, $txns, $accounts);
  },
);

export const groupedByCategory = derived(
  [reviewDocuments, reviewTransactions, accounts],
  ([$docs, $txns, $accounts]) => {
    return groupByCategory($docs, $txns, $accounts);
  },
);

export const pendingCount = derived(pendingDocuments, ($docs) => $docs.length);

export const getDocumentReviewInfo = (doc: Document) => {
  const $txns = get(reviewTransactions);
  const $accounts = get(accounts);
  return getReviewInfo(doc, $txns, $accounts);
};

export async function updateDocumentReviewStatus(
  doc: Document,
  status: ReviewStatus,
  notes?: string,
): Promise<boolean> {
  reviewStore.setLoading(true);
  try {
    await put_update_review_status({
      entry_hash: doc.entry_hash,
      status,
      notes: notes || undefined,
    });

    notify(`文档复核状态已更新为: ${status}`);
    router.reload();
    return true;
  } catch (error) {
    notify_err(error, (e) => `更新复核状态失败: ${e.message}`);
    return false;
  } finally {
    reviewStore.setLoading(false);
  }
}

export async function clearDocumentReviewStatus(
  doc: Document,
): Promise<boolean> {
  reviewStore.setLoading(true);
  try {
    await put_clear_review_status({
      entry_hash: doc.entry_hash,
    });

    notify("文档复核状态已清除");
    router.reload();
    return true;
  } catch (error) {
    notify_err(error, (e) => `清除复核状态失败: ${e.message}`);
    return false;
  } finally {
    reviewStore.setLoading(false);
  }
}
