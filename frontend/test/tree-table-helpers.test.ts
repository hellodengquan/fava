import { deepEqual, equal, ok } from "node:assert/strict";
import { get as store_get } from "svelte/store";
import { test } from "node:test";

import type { AccountTreeNode } from "../src/charts/hierarchy.ts";
import { setup_jsdom } from "./dom.ts";
import { initialiseLedgerData } from "./helpers.ts";

import { stratifyAccounts } from "../src/lib/tree.ts";
import { get_not_shown } from "../src/tree-table/helpers.ts";

test.before(initialiseLedgerData);
test.beforeEach(setup_jsdom);

function buildSimpleTree(): AccountTreeNode {
  const data = [
    {
      account: "Assets:Bank:Checking",
      balance: { EUR: 1000, USD: 500 },
      balance_children: { EUR: 1000, USD: 500 },
      has_txns: true,
    },
    {
      account: "Assets:Bank:Savings",
      balance: { EUR: 5000 },
      balance_children: { EUR: 5000 },
      has_txns: true,
    },
    {
      account: "Assets:Cash",
      balance: { EUR: 200 },
      balance_children: { EUR: 200 },
      has_txns: true,
    },
    {
      account: "Expenses:Food",
      balance: {},
      balance_children: { EUR: 450 },
      has_txns: false,
    },
    {
      account: "Expenses:Food:Groceries",
      balance: { EUR: 300 },
      balance_children: { EUR: 300 },
      has_txns: true,
    },
    {
      account: "Expenses:Food:Restaurant",
      balance: { EUR: 150 },
      balance_children: { EUR: 150 },
      has_txns: true,
    },
    {
      account: "Expenses:Empty",
      balance: {},
      balance_children: {},
      has_txns: false,
    },
  ];
  return stratifyAccounts(
    data,
    (d) => d.account,
    (name, datum) => ({
      account: name,
      balance: datum?.balance ?? {},
      balance_children: datum?.balance_children ?? {},
      cost: null,
      cost_children: null,
      has_txns: datum?.has_txns ?? false,
    }),
  );
}

test("tree-table-helpers: get_not_shown is a derived function", () => {
  const $not_shown_fn = store_get(get_not_shown);
  ok(typeof $not_shown_fn === "function");
});

test("tree-table-helpers: simple tree with no end date", () => {
  const $not_shown_fn = store_get(get_not_shown);
  const tree = buildSimpleTree();
  const result = $not_shown_fn(tree, null);
  ok(result instanceof Set);
});

test("tree-table-helpers: accounts with transactions shown", () => {
  const $not_shown_fn = store_get(get_not_shown);
  const tree = buildSimpleTree();
  const notShown = $not_shown_fn(tree, null);

  ok(!notShown.has("Assets:Bank:Checking"));
  ok(!notShown.has("Assets:Bank:Savings"));
  ok(!notShown.has("Assets:Cash"));
  ok(!notShown.has("Expenses:Food:Groceries"));
  ok(!notShown.has("Expenses:Food:Restaurant"));
});

test("tree-table-helpers: multi-currency balances shown correctly", () => {
  const $not_shown_fn = store_get(get_not_shown);
  const tree = buildSimpleTree();
  const notShown = $not_shown_fn(tree, null);

  const checking = tree.children
    .find((c) => c.account === "Assets")!
    .children.find((c) => c.account === "Assets:Bank")!
    .children.find((c) => c.account === "Assets:Bank:Checking")!;

  ok("EUR" in checking.balance);
  ok("USD" in checking.balance);
  equal(checking.balance.EUR, 1000);
  equal(checking.balance.USD, 500);
  ok(!notShown.has(checking.account));
});

test("tree-table-helpers: parent accounts shown if children shown", () => {
  const $not_shown_fn = store_get(get_not_shown);
  const tree = buildSimpleTree();
  const notShown = $not_shown_fn(tree, null);

  ok(!notShown.has("Assets"));
  ok(!notShown.has("Assets:Bank"));
  ok(!notShown.has("Expenses:Food"));
  ok(!notShown.has("Expenses"));
});

test("tree-table-helpers: tree hierarchy integrity", () => {
  const tree = buildSimpleTree();

  equal(tree.account, "");
  equal(tree.children.length, 2);

  const assets = tree.children.find((c) => c.account === "Assets")!;
  equal(assets.children.length, 2);
  ok(assets.children.some((c) => c.account === "Assets:Bank"));
  ok(assets.children.some((c) => c.account === "Assets:Cash"));

  const bank = assets.children.find((c) => c.account === "Assets:Bank")!;
  equal(bank.children.length, 2);
  deepEqual(
    bank.children.map((c) => c.account).sort(),
    ["Assets:Bank:Checking", "Assets:Bank:Savings"],
  );
});

test("tree-table-helpers: balance_children from data preserved", () => {
  const tree = buildSimpleTree();

  const checking = tree.children
    .find((c) => c.account === "Assets")!
    .children.find((c) => c.account === "Assets:Bank")!
    .children.find((c) => c.account === "Assets:Bank:Checking")!;

  equal(checking.balance.EUR, 1000);
  equal(checking.balance.USD, 500);
  equal(checking.balance_children.EUR, 1000);
  equal(checking.balance_children.USD, 500);

  const savings = tree.children
    .find((c) => c.account === "Assets")!
    .children.find((c) => c.account === "Assets:Bank")!
    .children.find((c) => c.account === "Assets:Bank:Savings")!;

  equal(savings.balance.EUR, 5000);
  equal(savings.balance_children.EUR, 5000);

  const groceries = tree.children
    .find((c) => c.account === "Expenses")!
    .children.find((c) => c.account === "Expenses:Food")!
    .children.find((c) => c.account === "Expenses:Food:Groceries")!;

  equal(groceries.balance.EUR, 300);
  equal(groceries.balance_children.EUR, 300);
});

test("tree-table-helpers: get_not_shown with specific date", () => {
  const $not_shown_fn = store_get(get_not_shown);
  const tree = buildSimpleTree();
  const date = new Date("2020-01-01");
  const notShown = $not_shown_fn(tree, date);
  ok(notShown instanceof Set);
});

test("tree-table-helpers: has_txns flag propagation", () => {
  const tree = buildSimpleTree();

  const checking = tree.children
    .find((c) => c.account === "Assets")!
    .children.find((c) => c.account === "Assets:Bank")!
    .children.find((c) => c.account === "Assets:Bank:Checking")!;
  equal(checking.has_txns, true);

  const empty = tree.children
    .find((c) => c.account === "Expenses")!
    .children.find((c) => c.account === "Expenses:Empty")!;
  equal(empty.has_txns, false);
  equal(Object.keys(empty.balance).length, 0);
  equal(Object.keys(empty.balance_children).length, 0);
});
