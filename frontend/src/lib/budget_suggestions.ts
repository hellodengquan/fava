import { _ } from "../i18n.ts";
import { leaf } from "./account.ts";

export type AccountType =
  | "Expenses"
  | "Income"
  | "Assets"
  | "Liabilities"
  | "Equity"
  | "Unknown";

export type AmountTier = "micro" | "small" | "medium" | "large" | "huge";

export function get_account_type(account: string): AccountType {
  if (account.startsWith("Expenses")) {
    return "Expenses";
  }
  if (account.startsWith("Income")) {
    return "Income";
  }
  if (account.startsWith("Assets")) {
    return "Assets";
  }
  if (account.startsWith("Liabilities")) {
    return "Liabilities";
  }
  if (account.startsWith("Equity")) {
    return "Equity";
  }
  return "Unknown";
}

export function get_amount_tier(budget_value: number): AmountTier {
  const abs = Math.abs(budget_value);
  if (abs < 50) {
    return "micro";
  }
  if (abs < 500) {
    return "small";
  }
  if (abs < 5000) {
    return "medium";
  }
  if (abs < 50000) {
    return "large";
  }
  return "huge";
}

export function get_over_budget_label(
  pct: number | null,
  account_type: AccountType,
): string {
  if (pct == null) {
    return _("Over Budget");
  }

  const base = account_type === "Income"
    ? _("Income Shortfall")
    : account_type === "Assets"
      ? _("Asset Overrun")
      : account_type === "Liabilities"
        ? _("Liability Growth")
        : _("Over Budget");

  if (pct > 50) {
    return `${base} — ${_("Critical: significantly exceeded")}`;
  }
  if (pct > 20) {
    return `${base} — ${_("Warning: moderately exceeded")}`;
  }
  return `${base} — ${_("Slight: minor overrun")}`;
}

function get_category_specific_suggestion(account_name: string): string {
  const leaf_name = leaf(account_name).toLowerCase();

  const patterns: Array<[RegExp, string]> = [
    [
      /(grocer|food|meal|dine|cafe|restaur|foodie|eat|lunch|breakfast|dinner|餐饮|食|餐)/i,
      _("Tip: reduce restaurant visits, cook at home, compare prices at different grocery stores."),
    ],
    [
      /(transport|travel|transit|gas|fuel|park|taxi|uber|car|flight|hotel|交通|旅行|出行|打车|加油)/i,
      _("Tip: use public transit, carpool, or review travel plans for cost-saving alternatives."),
    ],
    [
      /(entertain|movie|game|stream|sport|concert|event|娱乐|电影|游戏|演出)/i,
      _("Tip: look for free activities, share subscriptions with family, use off-peak pricing."),
    ],
    [
      /(util|electric|water|gas|phone|internet|bill|水电|电费|水费|宽带|话费)/i,
      _("Tip: review utility providers for better rates, conserve resources, check for plan optimizations."),
    ],
    [
      /(health|medical|doctor|clinic|pharm|dental|hospital|医疗|医生|医院|药品)/i,
      _("Tip: verify insurance coverage, compare prices across providers, consider preventive care."),
    ],
    [
      /(educ|book|course|class|school|tuition|学习|教育|课程|书籍|学费)/i,
      _("Tip: look for free/affordable alternatives (MOOCs, libraries), consider if the expense is essential."),
    ],
    [
      /(cloth|wear|shoe|apparel|fashion|wardrobe|衣服|服装|鞋)/i,
      _("Tip: wait for sales, buy quality items less frequently, consider second-hand options."),
    ],
    [
      /(gift|donat|charity|donate|礼物|捐赠|慈善)/i,
      _("Tip: plan gift budgets in advance, consider homemade or experience-based gifts."),
    ],
    [
      /(child|baby|kid|school|daycare|孩子|儿童|托|育儿)/i,
      _("Tip: explore subsidies, second-hand items, shared childcare arrangements."),
    ],
    [
      /(salary|wage|payroll|revenue|sale|dividend|interest|rent|工资|收入|销售|股利|利息|租金)/i,
      _("Tip: analyze causes of shortfall — explore additional revenue sources or review forecasts."),
    ],
  ];

  for (const [pattern, suggestion] of patterns) {
    if (pattern.test(leaf_name) || pattern.test(account_name)) {
      return suggestion;
    }
  }

  return "";
}

export function get_over_budget_suggestion(
  pct: number | null,
  account_type: AccountType,
  budget_value: number,
  diff_value: number,
  account_name: string,
): string {
  if (pct == null) {
    return "";
  }

  const tier = get_amount_tier(budget_value);
  const category_tip = get_category_specific_suggestion(account_name);

  const suggestions: string[] = [];

  if (account_type === "Income") {
    if (pct > 50) {
      suggestions.push(
        _("Critical income shortfall — reassess revenue projections and explore new sources."),
      );
    } else if (pct > 20) {
      suggestions.push(
        _("Significant income shortfall — review client pipeline and invoicing schedule."),
      );
    } else {
      suggestions.push(
        _("Minor income shortfall — monitor next period to identify trends."),
      );
    }
  } else if (account_type === "Liabilities") {
    suggestions.push(
      _("Liability growth detected — review repayment schedule, check for unexpected interest charges."),
    );
    if (tier === "huge" || tier === "large") {
      suggestions.push(
        _("Large liability — consider debt consolidation or refinancing options."),
      );
    }
  } else if (account_type === "Assets") {
    suggestions.push(
      _("Asset allocation deviation — verify if this exceeds planned capital expenditures."),
    );
    if (tier === "huge" || tier === "large") {
      suggestions.push(
        _("Large asset purchase — ensure ROI analysis was completed and financing is optimal."),
      );
    }
  } else {
    if (pct > 50) {
      suggestions.push(
        _("Consider reallocating funds from other categories or reviewing this expense in detail."),
      );
    } else if (pct > 20) {
      suggestions.push(
        _("Review spending pattern and adjust budget or cut non-essential items."),
      );
    } else {
      suggestions.push(
        _("Minor overrun — monitor if this trend continues in upcoming periods."),
      );
    }
  }

  if (tier === "micro") {
    suggestions.push(
      _("Note: Small absolute amount — this overrun may not be actionable, but track the pattern."),
    );
  } else if (tier === "huge") {
    suggestions.push(
      _("High-impact budget item — prioritize this for immediate review and approvals."),
    );
  }

  if (category_tip) {
    suggestions.push(category_tip);
  }

  if (diff_value > budget_value * 2) {
    suggestions.push(
      _("Check for data entry errors — the actual value is more than double the budget."),
    );
  }

  return suggestions.join(" ");
}
