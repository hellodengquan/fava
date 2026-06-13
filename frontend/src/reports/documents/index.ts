import { get_documents } from "../../api/index.ts";
import type { Document } from "../../entries/index.ts";
import { _ } from "../../i18n.ts";
import { getReportFilterContext } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import Documents from "./Documents.svelte";

export interface DocumentsReportProps {
  documents: Document[];
}

export const documents = new Route(
  "documents",
  Documents,
  async (url: URL) =>
    get_documents(getReportFilterContext(url)).then((data) => ({
      documents: data,
    })),
  () => _("Documents"),
);
