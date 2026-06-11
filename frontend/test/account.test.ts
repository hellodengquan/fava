import { deepEqual, equal, ok } from "node:assert/strict";
import { test } from "node:test";

import {
  ancestors,
  get_internal_accounts,
  is_descendant,
  is_descendant_or_equal,
  leaf,
  parent,
} from "../src/lib/account.ts";

test("account: split account names", () => {
  deepEqual(ancestors("Assets:Cash:Sub"), [
    "Assets",
    "Assets:Cash",
    "Assets:Cash:Sub",
  ]);
  deepEqual(ancestors("Assets:Cash"), ["Assets", "Assets:Cash"]);
  deepEqual(ancestors("Assets"), ["Assets"]);
  deepEqual(ancestors(""), []);

  equal(parent("Assets:Cash:Sub"), "Assets:Cash");
  equal(parent("Assets:Cash"), "Assets");
  equal(parent("Assets"), "");
  equal(parent(""), "");

  equal(leaf("asd:asdf"), "asdf");
  equal(leaf("asd"), "asd");
  equal(leaf(""), "");
});

test("account: get internal accounts", () => {
  deepEqual(
    get_internal_accounts([
      "Assets:Cash:Sub",
      "Income:Something",
      "Income:Something:Subaccount",
    ]),
    ["Assets", "Assets:Cash", "Income", "Income:Something"],
  );
});

test("account: check whether account is descendant of another", () => {
  const is_descendant_of_root = is_descendant_or_equal("");
  equal(true, is_descendant_of_root("A"));
  equal(true, is_descendant_of_root("A:Test"));
  const is_descendant_of_assets = is_descendant_or_equal("Assets");
  equal(true, is_descendant_of_assets("Assets"));
  equal(true, is_descendant_of_assets("Assets:Cash"));
  equal(false, is_descendant_of_assets("AssetsOther"));
  equal(false, is_descendant_of_assets("Income:Other"));
  const is_descendant_of_assets_cash = is_descendant_or_equal("Assets:Cash");
  equal(true, is_descendant_of_assets_cash("Assets:Cash"));
  equal(false, is_descendant_of_assets_cash("Assets"));

  const is_true_descendant_of_root = is_descendant("");
  equal(true, is_true_descendant_of_root("A"));
  equal(true, is_true_descendant_of_root("A:Test"));
  equal(false, is_true_descendant_of_root(""));
  const is_true_descendant_of_assets = is_descendant("Assets");
  equal(false, is_true_descendant_of_assets("Assets"));
  equal(true, is_true_descendant_of_assets("Assets:Cash"));
});

test("account: deeply nested ancestors", () => {
  const deep = "A:B:C:D:E:F:G";
  const result = ancestors(deep);
  deepEqual(result, [
    "A",
    "A:B",
    "A:B:C",
    "A:B:C:D",
    "A:B:C:D:E",
    "A:B:C:D:E:F",
    "A:B:C:D:E:F:G",
  ]);
  equal(result.length, 7);
});

test("account: deeply nested parent", () => {
  equal(parent("A:B:C:D:E:F"), "A:B:C:D:E");
  equal(parent("A:B:C:D:E"), "A:B:C:D");
});

test("account: deeply nested leaf", () => {
  equal(leaf("Assets:US:Bank:Checking:Joint"), "Joint");
  equal(leaf("Income:Salary:Monthly:Net"), "Net");
});

test("account: get internal accounts - deeply nested", () => {
  const internal = get_internal_accounts([
    "A:B:C:D:E",
    "X:Y:Z",
  ]);
  deepEqual(internal, [
    "A",
    "A:B",
    "A:B:C",
    "A:B:C:D",
    "X",
    "X:Y",
  ]);
});

test("account: get internal accounts - no internals for single-segment", () => {
  const internal = get_internal_accounts(["Assets", "Liabilities", "Income"]);
  deepEqual(internal, []);
});

test("account: get internal accounts - duplicates deduplicated", () => {
  const internal = get_internal_accounts([
    "Assets:Cash:EUR",
    "Assets:Cash:USD",
    "Assets:Bank:Checking",
  ]);
  deepEqual(internal, ["Assets", "Assets:Bank", "Assets:Cash"]);
});

test("account: is_descendant_or_equal - deep nesting", () => {
  const tester = is_descendant_or_equal("Assets:US:Bank");
  equal(true, tester("Assets:US:Bank"));
  equal(true, tester("Assets:US:Bank:Checking"));
  equal(true, tester("Assets:US:Bank:Checking:Joint"));
  equal(true, tester("Assets:US:Bank:Savings"));
  equal(false, tester("Assets:US"));
  equal(false, tester("Assets"));
  equal(false, tester("Assets:EU:Bank"));
});

test("account: is_descendant - strict descendant only", () => {
  const tester = is_descendant("Expenses:Food");
  equal(false, tester("Expenses:Food"));
  equal(true, tester("Expenses:Food:Groceries"));
  equal(true, tester("Expenses:Food:Groceries:Supermarket"));
  equal(false, tester("Expenses"));
  equal(false, tester("Expenses:Transport"));
});

test("account: parent - edge cases", () => {
  equal(parent(""), "");
  equal(parent("A"), "");
  equal(parent("A:B"), "A");
  equal(parent(":A"), "");
  equal(parent("A:"), "A");
  equal(parent("::"), ":");
});

test("account: ancestors - edge cases", () => {
  deepEqual(ancestors("A"), ["A"]);
  deepEqual(ancestors("A:B"), ["A", "A:B"]);
});

test("account: is_descendant_or_equal exact match vs prefix", () => {
  const tester = is_descendant_or_equal("Assets");
  equal(true, tester("Assets"));
  equal(true, tester("Assets:Cash"));
  equal(false, tester("AssetsBacked"));
  equal(false, tester("AssetsCash"));
  equal(false, tester("Assets2"));
});

test("account: is_descendant excludes exact match", () => {
  const tester = is_descendant("A");
  equal(false, tester("A"));
  equal(true, tester("A:B"));
  equal(false, tester("AB"));
  equal(false, tester("AB:C"));
});

test("account: closed account with subaccounts", () => {
  const closedAccount = "Assets:ClosedBank";
  const closedChildren = ["Assets:ClosedBank:Account1", "Assets:ClosedBank:Account2"];

  const isChild = is_descendant_or_equal(closedAccount);
  ok(closedChildren.every((acc) => isChild(acc)));
  equal(true, isChild(closedAccount));
});

test("account: virtual accounts hierarchy", () => {
  const virtualAccounts = [
    "Assets:Virtual:Placeholder",
    "Assets:Virtual:Placeholder:Sub1",
    "Assets:Virtual:Placeholder:Sub2",
  ];

  const internals = get_internal_accounts(virtualAccounts);
  ok(internals.includes("Assets"));
  ok(internals.includes("Assets:Virtual"));
  ok(internals.includes("Assets:Virtual:Placeholder"));

  const parentTester = is_descendant_or_equal("Assets:Virtual");
  ok(virtualAccounts.every((acc) => parentTester(acc)));
});
