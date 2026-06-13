import { format } from "d3-format";
import type { NumberValue } from "d3-scale";
import { derived } from "svelte/store";

import type { FormatterContext } from "../format.ts";
import {
  dateFormat,
  formatter_context,
  localeFormatter,
  replaceNumbers,
  timeFilterDateFormat,
} from "../format.ts";
import { getInterval } from "../lib/interval.ts";
import { locale } from "./fava_options.ts";
import { incognito, precisions } from "./index.ts";
import { report_filter_context } from "./filters.ts";

const short_format = format(".3s");

export const short = derived(incognito, ($incognito) =>
  $incognito
    ? (n: NumberValue) => replaceNumbers(short_format(n))
    : short_format,
);

export const num = derived(locale, ($locale) => localeFormatter($locale));

export const ctx = derived(
  [incognito, locale, precisions],
  ([$incognito, $locale, $precisions]): FormatterContext =>
    formatter_context($incognito, $locale, $precisions),
);

export const currentDateFormat = derived(
  report_filter_context,
  ($context) => dateFormat[getInterval($context.interval)],
);
export const currentTimeFilterDateFormat = derived(
  report_filter_context,
  ($context) => timeFilterDateFormat[getInterval($context.interval)],
);
