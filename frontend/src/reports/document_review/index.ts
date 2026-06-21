import { get_document_review } from "../../api/index.ts";
import type { DocumentReview as DocumentReviewType } from "../../api/validators.ts";
import { _ } from "../../i18n.ts";
import { getURLFilters } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import DocumentReview from "./DocumentReview.svelte";

export interface DocumentReviewReportProps {
  review: DocumentReviewType;
}

export const document_review = new Route(
  "document_review",
  DocumentReview,
  async (url: URL) =>
    get_document_review(getURLFilters(url)).then((data) => ({
      review: data,
    })),
  () => _("Document Review"),
);
