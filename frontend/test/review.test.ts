import { deepEqual, equal, notEqual, ok } from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

import {
  Document,
  entryValidator,
  Transaction,
} from "../src/entries/index.ts";
import {
  categoryLabels,
  detectIssues,
  getPendingDocuments,
  getReviewNotes,
  getReviewedAt,
  getReviewInfo,
  getReviewStatus,
  groupByCategory,
  statusColors,
  statusLabels,
  updateJournalReviewBadge,
} from "../src/lib/review.ts";
import { reviewStore, reviewDocuments, reviewTransactions } from "../src/stores/review.ts";

function createTestDocument(overrides: Partial<{
  account: string;
  date: string;
  entry_hash: string;
  filename: string;
  meta: Record<string, string>;
  links: string[];
}> = {}): Document {
  const json = {
    t: "Document" as const,
    meta: {
      filename: "/test/test.beancount",
      lineno: "1",
      ...overrides.meta,
    },
    date: overrides.date || "2024-01-15",
    entry_hash: overrides.entry_hash || "test-hash-1",
    account: overrides.account || "Expenses:Food:Restaurant",
    filename: overrides.filename || "/test/receipt-2024-01-15.pdf",
    tags: [],
    links: overrides.links || [],
  };
  const result = entryValidator(json);
  ok(result.is_ok(), `Validation error: ${result.is_err() ? result.error : ""}`);
  return result.value as Document;
}

function createTestTransaction(overrides: Partial<{
  entry_hash: string;
  date: string;
  links: string[];
  payee: string;
  narration: string;
  postings: Array<{ account: string; amount: string }>;
}> = {}): Transaction {
  const json = {
    t: "Transaction" as const,
    meta: { filename: "/test/test.beancount", lineno: "1" },
    date: overrides.date || "2024-01-15",
    entry_hash: overrides.entry_hash || "txn-hash-1",
    flag: "*",
    payee: overrides.payee || "Test Store",
    narration: overrides.narration || "Test transaction",
    tags: [],
    links: overrides.links || [],
    postings: overrides.postings || [
      { account: "Expenses:Food:Restaurant", amount: "25.00 USD", meta: {} },
      { account: "Assets:Cash", amount: "-25.00 USD", meta: {} },
    ],
  };
  const result = entryValidator(json);
  ok(result.is_ok(), `Validation error: ${result.is_err() ? result.error : ""}`);
  return result.value as Transaction;
}

test("getReviewStatus: returns null when no review_status in meta", () => {
  const doc = createTestDocument();
  equal(getReviewStatus(doc), null);
});

test("getReviewStatus: returns status when present in meta", () => {
  const doc = createTestDocument({ meta: { review_status: "approved" } });
  equal(getReviewStatus(doc), "approved");
});

test("getReviewStatus: handles different status values", () => {
  const pendingDoc = createTestDocument({ meta: { review_status: "pending" } });
  const rejectedDoc = createTestDocument({ meta: { review_status: "rejected" } });

  equal(getReviewStatus(pendingDoc), "pending");
  equal(getReviewStatus(rejectedDoc), "rejected");
});

test("getReviewStatus: returns null for invalid status values", () => {
  const invalidDoc = createTestDocument({ meta: { review_status: "invalid" } });
  equal(getReviewStatus(invalidDoc), null);
});

test("getReviewStatus: returns null for non-string values", () => {
  const doc = createTestDocument({ meta: { review_status: "TRUE" } });
  equal(getReviewStatus(doc), null);
});

test("getReviewNotes: returns notes when present", () => {
  const doc = createTestDocument({ meta: { review_notes: "Check amount" } });
  equal(getReviewNotes(doc), "Check amount");
});

test("getReviewNotes: returns undefined when not present", () => {
  const doc = createTestDocument();
  equal(getReviewNotes(doc), undefined);
});

test("getReviewedAt: returns date when present", () => {
  const doc = createTestDocument({ meta: { reviewed_at: "2024-01-15T10:30:00" } });
  equal(getReviewedAt(doc), "2024-01-15T10:30:00");
});

test("detectIssues: no issues for valid document", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({
    filename: "/test/receipt-2024-01-15_25.00.pdf",
  });
  const txn = createTestTransaction({
    links: ["link1"],
    postings: [
      { account: "Expenses:Food:Restaurant", amount: "25.00 USD", meta: {} },
      { account: "Assets:Cash", amount: "-25.00 USD", meta: {} },
    ],
  });
  const docWithLink = createTestDocument({
    filename: "/test/receipt-2024-01-15_25.00.pdf",
    links: ["link1"],
  });

  const issues = detectIssues(docWithLink, [txn], accounts);
  equal(issues.length, 0);
});

test("detectIssues: account_mismatch when account not in accounts list", () => {
  const accounts = ["Expenses:Food", "Assets:Cash"];
  const doc = createTestDocument({ account: "Expenses:Food:Restaurant" });

  const issues = detectIssues(doc, [], accounts);
  equal(issues.length, 2);
  equal(issues[0].category, "account_mismatch");
  equal(issues[0].description, "账户不存在或无效");
});

test("detectIssues: missing_fields when no linked transactions", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument();

  const issues = detectIssues(doc, [], accounts);
  ok(issues.some((i) => i.category === "missing_fields"));
  ok(issues.some((i) => i.description === "未关联交易记录"));
});

test("detectIssues: amount_discrepancy when amounts don't match", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({
    filename: "/test/receipt-2024-01-15_30.00.pdf",
    links: ["link1"],
  });
  const txn = createTestTransaction({
    links: ["link1"],
    postings: [
      { account: "Expenses:Food:Restaurant", amount: "25.00 USD", meta: {} },
      { account: "Assets:Cash", amount: "-25.00 USD", meta: {} },
    ],
  });

  const issues = detectIssues(doc, [txn], accounts);
  ok(issues.some((i) => i.category === "amount_discrepancy"));
});

test("detectIssues: missing_fields when date is empty", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({ date: "", links: ["link1"] });
  const txn = createTestTransaction({ links: ["link1"] });

  const issues = detectIssues(doc, [txn], accounts);
  ok(issues.some((i) => i.description === "缺少日期"));
});

test("detectIssues: matches via document link in posting meta", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({
    filename: "/test/receipt.pdf",
  });
  const txn = createTestTransaction({
    postings: [
      {
        account: "Expenses:Food:Restaurant",
        amount: "25.00 USD",
        meta: { document: "/test/receipt.pdf" },
      },
      { account: "Assets:Cash", amount: "-25.00 USD", meta: {} },
    ],
  });

  const issues = detectIssues(doc, [txn], accounts);
  ok(!issues.some((i) => i.description === "未关联交易记录"));
});

test("groupByCategory: groups documents by issue category", () => {
  const accounts = ["Expenses:Food", "Assets:Cash"];

  const doc1 = createTestDocument({
    entry_hash: "h1",
    account: "Expenses:Food:Restaurant",
    links: ["link1"],
    filename: "/test/receipt_25.00.pdf",
  });
  const doc2 = createTestDocument({
    entry_hash: "h2",
    account: "Expenses:Food",
    links: ["link2"],
    filename: "/test/receipt_30.00.pdf",
  });
  const doc3 = createTestDocument({
    entry_hash: "h3",
    account: "Expenses:Food",
  });

  const txn = createTestTransaction({
    links: ["link1", "link2"],
    postings: [
      { account: "Expenses:Food", amount: "25.00 USD", meta: {} },
      { account: "Assets:Cash", amount: "-25.00 USD", meta: {} },
    ],
  });

  const grouped = groupByCategory([doc1, doc2, doc3], [txn], accounts);

  ok(grouped.account_mismatch.length === 1);
  equal(grouped.account_mismatch[0].entry_hash, "h1");

  ok(grouped.amount_discrepancy.length >= 1);

  ok(grouped.missing_fields.length >= 1);
  ok(grouped.missing_fields.some((d) => d.entry_hash === "h3"));
});

test("getPendingDocuments: filters out approved and rejected documents", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];

  const pendingDoc = createTestDocument({
    entry_hash: "pending",
    meta: { review_status: "pending" },
  });
  const approvedDoc = createTestDocument({
    entry_hash: "approved",
    meta: { review_status: "approved" },
  });
  const rejectedDoc = createTestDocument({
    entry_hash: "rejected",
    meta: { review_status: "rejected" },
  });
  const noStatusDoc = createTestDocument({
    entry_hash: "no-status",
    links: ["link1"],
  });
  const noStatusWithIssues = createTestDocument({
    entry_hash: "no-status-issues",
  });

  const txn = createTestTransaction({ links: ["link1"] });

  const docs = [pendingDoc, approvedDoc, rejectedDoc, noStatusDoc, noStatusWithIssues];
  const pending = getPendingDocuments(docs, [txn], accounts);

  equal(pending.length, 2);
  ok(pending.some((d) => d.entry_hash === "pending"));
  ok(pending.some((d) => d.entry_hash === "no-status-issues"));
  ok(!pending.some((d) => d.entry_hash === "approved"));
  ok(!pending.some((d) => d.entry_hash === "rejected"));
  ok(!pending.some((d) => d.entry_hash === "no-status"));
});

test("getReviewInfo: combines status and issues", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({
    meta: {
      review_status: "pending",
      review_notes: "Check this",
      reviewed_at: "2024-01-15T10:30:00",
    },
    links: ["link1"],
  });
  const txn = createTestTransaction({ links: ["link1"] });

  const info = getReviewInfo(doc, [txn], accounts);

  equal(info.status, "pending");
  equal(info.notes, "Check this");
  equal(info.reviewed_at, "2024-01-15T10:30:00");
  equal(info.issues.length, 0);
});

test("statusLabels: has correct labels", () => {
  equal(statusLabels.pending, "待复核");
  equal(statusLabels.approved, "已通过");
  equal(statusLabels.rejected, "已拒绝");
});

test("statusColors: has correct colors", () => {
  equal(statusColors.pending, "#fbbf24");
  equal(statusColors.approved, "#10b981");
  equal(statusColors.rejected, "#ef4444");
});

test("categoryLabels: has correct labels", () => {
  equal(categoryLabels.account_mismatch, "账户问题");
  equal(categoryLabels.amount_discrepancy, "金额差异");
  equal(categoryLabels.missing_fields, "缺失字段");
});

test("updateJournalReviewBadge: returns false when row not found", () => {
  const dom = new JSDOM("<ol><li data-entry-hash='other-hash'></li></ol>");
  const container = dom.window.document.querySelector("ol")!;

  const result = updateJournalReviewBadge(container, "test-hash", "approved");
  equal(result, false);
});

test("updateJournalReviewBadge: creates new badge when status set", () => {
  const dom = new JSDOM(`
    <ol>
      <li data-entry-hash='test-hash'>
        <p>
          <span class='description'>Test Document</span>
        </p>
      </li>
    </ol>
  `);
  const container = dom.window.document.querySelector("ol")!;

  const result = updateJournalReviewBadge(container, "test-hash", "approved");
  equal(result, true);

  const badge = container.querySelector(".review-status-badge")!;
  ok(badge);
  equal(badge.textContent, "已通过");
  equal(badge.getAttribute("title"), "已通过");
  equal((badge as HTMLElement).style.backgroundColor, "rgb(16, 185, 129)");
});

test("updateJournalReviewBadge: updates existing badge when status changes", () => {
  const dom = new JSDOM(`
    <ol>
      <li data-entry-hash='test-hash'>
        <p>
          <span class='description'>
            Test Document
            <span class='review-status-badge' style='background-color: #fbbf24' title='待复核'>待复核</span>
          </span>
        </p>
      </li>
    </ol>
  `);
  const container = dom.window.document.querySelector("ol")!;

  const result = updateJournalReviewBadge(container, "test-hash", "rejected");
  equal(result, true);

  const badges = container.querySelectorAll(".review-status-badge");
  equal(badges.length, 1);

  const badge = badges[0]!;
  equal(badge.textContent, "已拒绝");
  equal(badge.getAttribute("title"), "已拒绝");
  equal((badge as HTMLElement).style.backgroundColor, "rgb(239, 68, 68)");
});

test("updateJournalReviewBadge: removes badge when status is null", () => {
  const dom = new JSDOM(`
    <ol>
      <li data-entry-hash='test-hash'>
        <p>
          <span class='description'>
            Test Document
            <span class='review-status-badge' style='background-color: #10b981' title='已通过'>已通过</span>
          </span>
        </p>
      </li>
    </ol>
  `);
  const container = dom.window.document.querySelector("ol")!;

  const result = updateJournalReviewBadge(container, "test-hash", null);
  equal(result, true);

  const badge = container.querySelector(".review-status-badge");
  equal(badge, null);
});

test("updateJournalReviewBadge: handles pending status", () => {
  const dom = new JSDOM(`
    <ol>
      <li data-entry-hash='test-hash'>
        <p><span class='description'>Test Document</span></p>
      </li>
    </ol>
  `);
  const container = dom.window.document.querySelector("ol")!;

  updateJournalReviewBadge(container, "test-hash", "pending");

  const badge = container.querySelector(".review-status-badge")!;
  equal(badge.textContent, "待复核");
  equal((badge as HTMLElement).style.backgroundColor, "rgb(251, 191, 36)");
});

test("reviewStore: initial state is correct", () => {
  const state = reviewStore.reset();
  reviewStore.subscribe((s) => {
    equal(s.selectedDocument, null);
    equal(s.isLoading, false);
    equal(s.lastUpdatedHash, null);
    equal(s.lastUpdatedStatus, null);
  });
});

test("reviewStore: markUpdated sets lastUpdated fields", () => {
  reviewStore.markUpdated("test-hash-123", "approved");

  reviewStore.subscribe((s) => {
    equal(s.lastUpdatedHash, "test-hash-123");
    equal(s.lastUpdatedStatus, "approved");
  });
});

test("reviewStore: markUpdated with null status", () => {
  reviewStore.markUpdated("test-hash-456", null);

  reviewStore.subscribe((s) => {
    equal(s.lastUpdatedHash, "test-hash-456");
    equal(s.lastUpdatedStatus, null);
  });
});

test("reviewStore: setLoading updates isLoading", () => {
  reviewStore.setLoading(true);

  reviewStore.subscribe((s) => {
    equal(s.isLoading, true);
  });

  reviewStore.setLoading(false);

  reviewStore.subscribe((s) => {
    equal(s.isLoading, false);
  });
});

test("reviewStore: selectDocument sets selectedDocument", () => {
  const doc = createTestDocument({ entry_hash: "selected-doc" });

  reviewStore.selectDocument(doc);

  reviewStore.subscribe((s) => {
    equal(s.selectedDocument?.entry_hash, "selected-doc");
  });

  reviewStore.selectDocument(null);

  reviewStore.subscribe((s) => {
    equal(s.selectedDocument, null);
  });
});

test("reviewStore: reset clears all state", () => {
  reviewStore.markUpdated("some-hash", "approved");
  reviewStore.setLoading(true);
  reviewStore.selectDocument(createTestDocument());

  reviewStore.reset();

  reviewStore.subscribe((s) => {
    equal(s.selectedDocument, null);
    equal(s.isLoading, false);
    equal(s.lastUpdatedHash, null);
    equal(s.lastUpdatedStatus, null);
  });
});

test("reviewDocuments store: initial state is empty", () => {
  reviewDocuments.subscribe((docs) => {
    deepEqual(docs, []);
  });
});

test("reviewTransactions store: initial state is empty", () => {
  reviewTransactions.subscribe((txns) => {
    deepEqual(txns, []);
  });
});

test("reviewDocuments store: can be updated", () => {
  const doc1 = createTestDocument({ entry_hash: "doc1" });
  const doc2 = createTestDocument({ entry_hash: "doc2" });

  reviewDocuments.set([doc1, doc2]);

  reviewDocuments.subscribe((docs) => {
    equal(docs.length, 2);
    equal(docs[0].entry_hash, "doc1");
    equal(docs[1].entry_hash, "doc2");
  });

  reviewDocuments.set([]);
});

test("detectIssues: document with amount matching no issues", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({
    filename: "/test/receipt-2024-01-15_25.00.pdf",
    links: ["link1"],
  });
  const txn = createTestTransaction({
    links: ["link1"],
    postings: [
      { account: "Expenses:Food:Restaurant", amount: "25.00 USD", meta: {} },
      { account: "Assets:Cash", amount: "-25.00 USD", meta: {} },
    ],
  });

  const issues = detectIssues(doc, [txn], accounts);
  equal(issues.length, 0);
});

test("detectIssues: document with decimal amount matches", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({
    filename: "/test/receipt_123.45.pdf",
    links: ["link1"],
  });
  const txn = createTestTransaction({
    links: ["link1"],
    postings: [
      { account: "Expenses:Food:Restaurant", amount: "123.45 USD", meta: {} },
      { account: "Assets:Cash", amount: "-123.45 USD", meta: {} },
    ],
  });

  const issues = detectIssues(doc, [txn], accounts);
  equal(issues.length, 0);
});

test("detectIssues: small amount difference is flagged", () => {
  const accounts = ["Expenses:Food:Restaurant", "Assets:Cash"];
  const doc = createTestDocument({
    filename: "/test/receipt_25.05.pdf",
    links: ["link1"],
  });
  const txn = createTestTransaction({
    links: ["link1"],
    postings: [
      { account: "Expenses:Food:Restaurant", amount: "25.00 USD", meta: {} },
      { account: "Assets:Cash", amount: "-25.00 USD", meta: {} },
    ],
  });

  const issues = detectIssues(doc, [txn], accounts);
  ok(issues.some((i) => i.category === "amount_discrepancy"));
});

test("getReviewStatus: type check ensures string values", () => {
  const doc = createTestDocument({
    meta: {
      review_status: "approved",
      some_bool: "TRUE",
    },
  });

  equal(getReviewStatus(doc), "approved");
  const meta = doc.meta as unknown as { get: (k: string) => boolean };
  notEqual(meta.get("some_bool"), "TRUE");
});
