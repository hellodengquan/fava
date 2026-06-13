import { get_document_gaps } from "../../api/index.ts";
import { _ } from "../../i18n.ts";
import { getURLFilters } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import DocumentGaps from "./DocumentGaps.svelte";

export interface TransactionGap {
  entry_hash: string;
  date: string;
  payee: string;
  narration: string;
  accounts: string[];
  total_amount: string;
  has_document_metadata: boolean;
  has_linked_documents: boolean;
  handled: boolean;
  tag_count: number;
  link_count: number;
}

export interface AccountGapSummary {
  account: string;
  total_transactions: number;
  transactions_with_docs: number;
  transactions_without_docs: number;
  handled_count: number;
  total_amount: string;
  missing_amount: string;
}

export interface DocumentGapStats {
  total_transactions: number;
  transactions_with_docs: number;
  transactions_without_docs: number;
  handled_count: number;
  unhandled_count: number;
  total_amount: string;
  missing_amount: string;
  accounts_with_gaps: number;
  total_accounts: number;
}

export interface DocumentGapReport {
  stats: DocumentGapStats;
  transaction_gaps: TransactionGap[];
  account_summaries: AccountGapSummary[];
}

export interface DocumentGapsReportProps {
  report: DocumentGapReport;
}

export const document_gaps = new Route(
  "document_gaps",
  DocumentGaps,
  async (url: URL) =>
    get_document_gaps(getURLFilters(url)).then((data) => ({
      report: data as unknown as DocumentGapReport,
    })),
  () => _("Document Gaps"),
);
