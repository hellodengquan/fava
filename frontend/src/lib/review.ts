import type { Document } from "../entries/index.ts";
import type { Transaction } from "../entries/index.ts";

export type ReviewStatus = "pending" | "approved" | "rejected";

export type ReviewCategory =
  | "account_mismatch"
  | "amount_discrepancy"
  | "missing_fields";

export interface ReviewIssue {
  category: ReviewCategory;
  description: string;
  details?: string;
}

export interface ReviewInfo {
  status: ReviewStatus;
  issues: ReviewIssue[];
  reviewed_at?: string;
  reviewed_by?: string;
  notes?: string;
}

const REVIEW_STATUS_KEY = "review_status";
const REVIEW_NOTES_KEY = "review_notes";
const REVIEWED_AT_KEY = "reviewed_at";
const REVIEWED_BY_KEY = "reviewed_by";

export function getReviewStatus(doc: Document): ReviewStatus | null {
  const status = doc.meta.get(REVIEW_STATUS_KEY);
  if (typeof status === "string" && (status === "pending" || status === "approved" || status === "rejected")) {
    return status;
  }
  return null;
}

export function getReviewNotes(doc: Document): string | undefined {
  const value = doc.meta.get(REVIEW_NOTES_KEY);
  return typeof value === "string" ? value : undefined;
}

export function getReviewedAt(doc: Document): string | undefined {
  const value = doc.meta.get(REVIEWED_AT_KEY);
  return typeof value === "string" ? value : undefined;
}

export const statusLabels: Record<ReviewStatus, string> = {
  pending: "待复核",
  approved: "已通过",
  rejected: "已拒绝",
};

export const statusColors: Record<ReviewStatus, string> = {
  pending: "#fbbf24",
  approved: "#10b981",
  rejected: "#ef4444",
};

export const categoryLabels: Record<ReviewCategory, string> = {
  account_mismatch: "账户问题",
  amount_discrepancy: "金额差异",
  missing_fields: "缺失字段",
};

export function updateJournalReviewBadge(
  container: HTMLElement | Document,
  entryHash: string,
  status: ReviewStatus | null,
): boolean {
  const row = container.querySelector(`li[data-entry-hash="${entryHash}"]`);
  if (!row) return false;

  const description = row.querySelector(":scope > p > .description");
  if (!description) return false;

  const existingBadge = description.querySelector(".review-status-badge");

  if (status === null) {
    if (existingBadge) {
      existingBadge.remove();
    }
    return true;
  }

  const label = statusLabels[status] ?? status;
  const color = statusColors[status] ?? "#6b7280";

  if (existingBadge) {
    existingBadge.textContent = label;
    existingBadge.setAttribute("title", label);
    (existingBadge as HTMLElement).style.backgroundColor = color;
  } else {
    const badge = document.createElement("span");
    badge.className = "review-status-badge";
    badge.textContent = label;
    badge.setAttribute("title", label);
    badge.style.backgroundColor = color;
    description.appendChild(badge);
  }

  return true;
}

export function detectIssues(
  doc: Document,
  transactions: Transaction[],
  accounts: string[],
): ReviewIssue[] {
  const issues: ReviewIssue[] = [];

  if (!accounts.includes(doc.account)) {
    issues.push({
      category: "account_mismatch",
      description: "账户不存在或无效",
      details: `账户 "${doc.account}" 不在有效账户列表中`,
    });
  }

  const linkedTransactions = transactions.filter((txn) =>
    doc.links?.some((link) => txn.links.includes(link)) ||
    txn.postings.some((p) => p.meta?.get("document") === doc.filename),
  );

  if (linkedTransactions.length === 0) {
    issues.push({
      category: "missing_fields",
      description: "未关联交易记录",
      details: "该文档尚未关联任何交易记录",
    });
  }

  const docAmount = extractAmountFromFilename(doc.filename);
  if (docAmount != null) {
    for (const txn of linkedTransactions) {
      const txnTotal = calculateTransactionTotal(txn);
      if (txnTotal != null && Math.abs(docAmount - txnTotal) > 0.01) {
        issues.push({
          category: "amount_discrepancy",
          description: "金额差异",
          details: `文档金额 ${docAmount} 与交易总金额 ${txnTotal} 不匹配`,
        });
      }
    }
  }

  if (!doc.date || doc.date === "") {
    issues.push({
      category: "missing_fields",
      description: "缺少日期",
      details: "文档日期字段为空",
    });
  }

  if (!doc.filename || doc.filename === "") {
    issues.push({
      category: "missing_fields",
      description: "缺少文件名",
      details: "文档文件名字段为空",
    });
  }

  return issues;
}

function extractAmountFromFilename(filename: string): number | null {
  const match = filename.match(/(\d+\.?\d*)/);
  if (match) {
    const parsed = parseFloat(match[1]);
    return isNaN(parsed) ? null : parsed;
  }
  return null;
}

function calculateTransactionTotal(txn: Transaction): number | null {
  let total = 0;
  let hasAmount = false;
  for (const posting of txn.postings) {
    const amount = parseAmount(posting.amount);
    if (amount != null) {
      total += amount;
      hasAmount = true;
    }
  }
  return hasAmount ? total : null;
}

function parseAmount(amountStr: string): number | null {
  const match = amountStr.match(/-?\d+\.?\d*/);
  if (match) {
    const parsed = parseFloat(match[0]);
    return isNaN(parsed) ? null : parsed;
  }
  return null;
}

export function getReviewInfo(
  doc: Document,
  transactions: Transaction[],
  accounts: string[],
): ReviewInfo {
  const status = getReviewStatus(doc) ?? "pending";
  const issues = detectIssues(doc, transactions, accounts);

  const notes = getReviewNotes(doc);
  const reviewed_at = getReviewedAt(doc);
  const reviewed_by = doc.meta.get(REVIEWED_BY_KEY)?.toString();

  return {
    status,
    issues,
    notes,
    reviewed_at,
    reviewed_by,
  };
}

export function groupByCategory(
  docs: Document[],
  transactions: Transaction[],
  accounts: string[],
): Record<ReviewCategory, Document[]> {
  const grouped: Record<ReviewCategory, Document[]> = {
    account_mismatch: [],
    amount_discrepancy: [],
    missing_fields: [],
  };

  for (const doc of docs) {
    const issues = detectIssues(doc, transactions, accounts);
    for (const issue of issues) {
      if (!grouped[issue.category].includes(doc)) {
        grouped[issue.category].push(doc);
      }
    }
  }

  return grouped;
}

export function getPendingDocuments(
  docs: Document[],
  transactions: Transaction[],
  accounts: string[],
): Document[] {
  return docs.filter((doc) => {
    const status = getReviewStatus(doc);
    if (status === "approved" || status === "rejected") {
      return false;
    }
    const issues = detectIssues(doc, transactions, accounts);
    return issues.length > 0;
  });
}
