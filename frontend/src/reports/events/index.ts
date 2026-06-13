import { get_events } from "../../api/index.ts";
import type { Event } from "../../entries/index.ts";
import { _ } from "../../i18n.ts";
import { getReportFilterContext } from "../../stores/filters.ts";
import { Route } from "../route.ts";
import Events from "./Events.svelte";

export interface EventsReportProps {
  events: Event[];
}

export const events = new Route<EventsReportProps>(
  "events",
  Events,
  async (url: URL) =>
    get_events(getReportFilterContext(url)).then((data) => ({ events: data })),
  () => _("Events"),
);
