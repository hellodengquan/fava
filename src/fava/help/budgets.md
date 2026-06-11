# Budgets

Budgets on a per-account basis can be added via `custom` directives in the
Beancount file:

<pre><textarea is="beancount-textarea">
2012-01-01 custom "budget" Expenses:Coffee       "daily"         4.00 EUR
2013-01-01 custom "budget" Expenses:Books        "weekly"       20.00 EUR
2014-02-10 custom "budget" Expenses:Groceries    "monthly"      40.00 EUR "living"
2015-05-01 custom "budget" Expenses:Electricity  "quarterly"    85.00 EUR "living"
2016-06-01 custom "budget" Expenses:Holiday      "yearly"     2500.00 EUR "travel"</textarea></pre>

If budgets are specified, Fava's reports and charts will display remaining
budgets and related information.

The budget directives can be specified `daily`, `weekly`, `monthly`, `quarterly`
and `yearly`. The specified budget is valid until another budget directive for
the account is specified. The budget is broken down to a daily budget, and
summed up for a range of dates as needed.

This makes the budgets very flexible, allowing for a monthly budget, being taken
over by a weekly budget, and so on.

## Budget Categories

Optionally, you can assign a **category** to a budget by appending a string as
the last argument (as shown in the example above with `"living"` and `"travel"`).
Multiple accounts can share the same category, allowing you to:

- Filter the account report by category to see budgets of the same group
- Aggregate spending across all accounts in a category
- Visually group related expense budgets

## Overspending & Near-Overspending Detection

Fava automatically monitors budget usage and provides visual indicators:

- **Normal (under 80%)**: Shown in the default positive color
- **Near overspent (80%–100%)**: Highlighted in amber with a `接近` badge
- **Overspent (≥ 100%)**: Highlighted in red with an `超支` badge

You can click the summary counters at the top of the account Changes/Balances
report to quickly filter accounts by their budget status. A progress bar is also
shown next to each difference to visualize the ratio of actual spending to the
budget.

## Date & Currency Consistency

Budget calculations use the same **[begin, end)** date-range convention (begin
inclusive, end exclusive) across all views:

- Interval tree tables (Changes / Balances)
- Bar charts (Net Profit, Income, Expenses)
- The underlying budget-calculation engine

Multiple currencies are supported natively. Each budget is defined in a
specific currency, and status/usage is computed per-currency without any
implicit conversion, keeping the semantics consistent across all displays.
