import { derived } from "svelte/store";

import { currentDateFormat } from "../stores/format.ts";
import { currencies } from "../stores/index.ts";
import { operating_currency } from "../stores/options.ts";
import {
  type ReportFilterContext,
  report_filter_context,
} from "../stores/filters.ts";

export interface ChartContext {
  readonly currencies: readonly string[];
  readonly dateFormat: (date: Date) => string;
  readonly filterContext: ReportFilterContext;
}

const operatingCurrenciesWithConversion = derived(
  [operating_currency, currencies, report_filter_context],
  ([$operating_currency, $currencies, $context]) =>
    $currencies.includes($context.conversion) &&
    !$operating_currency.includes($context.conversion)
      ? [...$operating_currency, $context.conversion]
      : $operating_currency,
);

export const chartContext = derived(
  [operatingCurrenciesWithConversion, currentDateFormat, report_filter_context],
  (
    [$operatingCurrenciesWithConversion, $currentDateFormat, $filterContext],
  ): ChartContext => ({
    currencies: $operatingCurrenciesWithConversion,
    dateFormat: $currentDateFormat,
    filterContext: $filterContext,
  }),
);
