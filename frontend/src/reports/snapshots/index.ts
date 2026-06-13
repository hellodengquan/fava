import { _ } from "../../i18n.ts";
import { DatalessRoute } from "../route.ts";
import Snapshots from "./Snapshots.svelte";

export const snapshots = new DatalessRoute(
  "snapshots",
  Snapshots,
  () => _("Snapshots"),
);
