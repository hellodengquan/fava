import { deepEqual, equal, ok } from "node:assert/strict";
import { test } from "node:test";

import { all_matching, stratify, stratifyAccounts, type TreeNode } from "../src/lib/tree.ts";

test("tree: stratifyAccounts", () => {
  const empty = stratifyAccounts(
    [],
    () => "",
    () => null,
  );
  deepEqual(empty, { children: [] });
  const emptyWithData = stratifyAccounts(
    [],
    () => "",
    () => ({ test: "test" }),
  );
  deepEqual(emptyWithData, { children: [], test: "test" });
  const tree = stratifyAccounts(
    ["aName:cName", "aName", "aName:bName"],
    (s) => s,
    (name) => ({ name }),
  );

  deepEqual(tree, {
    children: [
      {
        children: [
          { children: [], name: "aName:bName" },
          { children: [], name: "aName:cName" },
        ],
        name: "aName",
      },
    ],
    name: "",
  });
  deepEqual(
    stratifyAccounts(
      ["Assets:Cash"],
      (s) => s,
      (name) => ({ name }),
    ),
    {
      children: [
        {
          children: [{ children: [], name: "Assets:Cash" }],
          name: "Assets",
        },
      ],
      name: "",
    },
  );
});

test("tree: stratify", () => {
  const empty = stratify(
    [],
    () => "",
    () => null,
    (s) => slash_parent(s),
  );
  deepEqual(empty, { children: [] });
  const emptyWithData = stratify(
    [],
    () => "",
    () => ({ test: "test" }),
    (s) => slash_parent(s),
  );
  deepEqual(emptyWithData, { children: [], test: "test" });
  const tree = stratify(
    ["aName/cName", "aName", "aName/bName"],
    (s) => s,
    (name) => ({ name }),
    (s) => slash_parent(s),
  );

  deepEqual(tree, {
    children: [
      {
        children: [
          { children: [], name: "aName/cName" },
          { children: [], name: "aName/bName" },
        ],
        name: "aName",
      },
    ],
    name: "",
  });
  deepEqual(
    stratify(
      ["Assets/Cash"],
      (s) => s,
      (name) => ({ name }),
      (s) => slash_parent(s),
    ),
    {
      children: [
        {
          children: [{ children: [], name: "Assets/Cash" }],
          name: "Assets",
        },
      ],
      name: "",
    },
  );
});

function slash_parent(name: string): string {
  const parent_end = name.lastIndexOf("/");
  return parent_end > 0 ? name.slice(0, parent_end) : "";
}

type AccountNode = TreeNode<{ name: string; balance: Record<string, number> }>;

function buildAccountTree(): AccountNode {
  const data = [
    { account: "Assets:Bank:Checking", balance: { EUR: 1000, USD: 500 } },
    { account: "Assets:Bank:Savings", balance: { EUR: 5000 } },
    { account: "Assets:Cash", balance: { EUR: 200, GBP: 100 } },
    { account: "Liabilities:CreditCard", balance: { EUR: -500 } },
    { account: "Income:Salary", balance: { EUR: -3000 } },
    { account: "Expenses:Food:Groceries", balance: { EUR: 300 } },
    { account: "Expenses:Food:Restaurant", balance: { EUR: 150 } },
    { account: "Expenses:Transport", balance: { EUR: 100 } },
  ];
  return stratifyAccounts(
    data,
    (d) => d.account,
    (name, datum) => ({
      name,
      balance: datum?.balance ?? {},
    }),
  );
}

test("tree: stratifyAccounts deep hierarchy", () => {
  const accounts = [
    "A:B:C:D:E",
    "A:B:C:D:F",
    "A:B:X",
    "A:Y:Z",
  ];
  const tree = stratifyAccounts(
    accounts,
    (s) => s,
    (name) => ({ name }),
  );

  equal(tree.children.length, 1);
  equal(tree.children[0].name, "A");
  equal(tree.children[0].children.length, 2);

  const bNode = tree.children[0].children.find((c) => c.name === "A:B");
  ok(bNode);
  equal(bNode.children.length, 2);

  const cNode = bNode.children.find((c) => c.name === "A:B:C");
  ok(cNode);
  equal(cNode.children.length, 1);

  const dNode = cNode.children[0];
  equal(dNode.name, "A:B:C:D");
  equal(dNode.children.length, 2);
  equal(dNode.children[0].name, "A:B:C:D:E");
  equal(dNode.children[1].name, "A:B:C:D:F");
});

test("tree: stratifyAccounts multiple top-level roots", () => {
  const accounts = [
    "Assets:Cash",
    "Liabilities:CreditCard",
    "Income:Salary",
    "Expenses:Food",
    "Equity:Opening",
  ];
  const tree = stratifyAccounts(
    accounts,
    (s) => s,
    (name) => ({ name }),
  );

  equal(tree.children.length, 5);
  const rootNames = tree.children.map((c) => c.name).sort();
  deepEqual(rootNames, ["Assets", "Equity", "Expenses", "Income", "Liabilities"]);
});

test("tree: stratifyAccounts implicit intermediate nodes", () => {
  const accounts = ["A:B:C:D:E:F"];
  const tree = stratifyAccounts(
    accounts,
    (s) => s,
    (name) => ({ name, isLeaf: name === "A:B:C:D:E:F" }),
  );

  const expected = {
    name: "",
    isLeaf: false,
    children: [
      {
        name: "A",
        isLeaf: false,
        children: [
          {
            name: "A:B",
            isLeaf: false,
            children: [
              {
                name: "A:B:C",
                isLeaf: false,
                children: [
                  {
                    name: "A:B:C:D",
                    isLeaf: false,
                    children: [
                      {
                        name: "A:B:C:D:E",
                        isLeaf: false,
                        children: [
                          { name: "A:B:C:D:E:F", isLeaf: true, children: [] },
                        ],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  };
  deepEqual(tree, expected);
});

test("tree: stratifyAccounts preserves extra data", () => {
  interface Data {
    balance: number;
    currency: string;
  }
  const items: Data[] = [
    { balance: 100, currency: "EUR" },
  ];
  const tree = stratifyAccounts(
    items.map((item, i) => ({ account: `Assets:Account${i + 1}`, ...item })),
    (d) => d.account,
    (name, datum) => ({
      name,
      balance: datum?.balance ?? 0,
      currency: datum?.currency ?? "",
    }),
  );

  equal(tree.children[0].children[0].balance, 100);
  equal(tree.children[0].children[0].currency, "EUR");
});

test("tree: stratifyAccounts with duplicate names merges data", () => {
  const data = [
    { account: "Assets:Cash", value: 1 },
    { account: "Assets:Cash", value: 2 },
  ];
  const tree = stratifyAccounts(
    data,
    (d) => d.account,
    (name, datum) => ({
      name,
      lastValue: datum?.value ?? 0,
    }),
  );

  equal(tree.children[0].children[0].lastValue, 2);
});

test("tree: stratify not sorted input", () => {
  const items = ["Z", "A", "M", "B"];
  const tree = stratify(
    items,
    (s) => s,
    (name) => ({ name }),
    () => "",
  );

  const names = tree.children.map((c) => c.name);
  deepEqual(names, ["Z", "A", "M", "B"]);
});

test("tree: stratifyAccounts sorted output", () => {
  const accounts = [
    "Expenses:Zebra",
    "Expenses:Apple",
    "Expenses:Mango",
    "Expenses:Banana",
  ];
  const tree = stratifyAccounts(
    accounts,
    (s) => s,
    (name) => ({ name }),
  );

  const childNames = tree.children[0].children.map((c) => c.name);
  deepEqual(childNames, [
    "Expenses:Apple",
    "Expenses:Banana",
    "Expenses:Mango",
    "Expenses:Zebra",
  ]);
});

test("tree: all_matching matches all", () => {
  const tree = buildAccountTree();

  const all = [...all_matching(tree, () => true)];
  ok(all.length > 0);

  function countNodes(node: AccountNode): number {
    return 1 + node.children.reduce((sum, c) => sum + countNodes(c), 0);
  }
  equal(all.length, countNodes(tree));
});

test("tree: all_matching matches none", () => {
  const tree = buildAccountTree();

  const none = [...all_matching(tree, () => false)];
  deepEqual(none, []);
});

test("tree: all_matching filter by name prefix", () => {
  const tree = buildAccountTree();

  const assets = [...all_matching(tree, (n) => n.name.startsWith("Assets") || n.name === "")];
  ok(assets.some((n) => n.name === ""));
  ok(assets.some((n) => n.name === "Assets"));
  ok(assets.some((n) => n.name === "Assets:Bank"));
  ok(assets.some((n) => n.name === "Assets:Cash"));
  ok(!assets.some((n) => n.name.startsWith("Liabilities")));
  ok(!assets.some((n) => n.name.startsWith("Expenses")));
});

test("tree: all_matching filter by balance currency", () => {
  const tree = buildAccountTree();

  const hasUSD = [...all_matching(tree, (n) => "USD" in n.balance)];
  ok(hasUSD.length >= 1);
  ok(hasUSD.every((n) => "USD" in n.balance));
  equal(hasUSD[0].name, "Assets:Bank:Checking");
});

test("tree: all_matching filter by balance threshold", () => {
  const tree = buildAccountTree();

  const highBalance = [
    ...all_matching(tree, (n) => (n.balance.EUR ?? 0) > 1000),
  ];
  const names = highBalance.map((n) => n.name).sort();
  deepEqual(names, ["Assets:Bank:Savings"]);
});

test("tree: all_matching leaf nodes only", () => {
  const tree = buildAccountTree();

  const leaves = [...all_matching(tree, (n) => n.children.length === 0)];
  ok(leaves.length > 0);
  ok(leaves.every((n) => n.children.length === 0));
});

test("tree: all_matching multi-currency accounts", () => {
  const tree = buildAccountTree();

  const multiCurrency = [
    ...all_matching(tree, (n) => Object.keys(n.balance).length >= 2),
  ];
  ok(multiCurrency.length >= 2);
  const names = multiCurrency.map((n) => n.name).sort();
  ok(names.includes("Assets:Bank:Checking"));
  ok(names.includes("Assets:Cash"));
});

test("tree: all_matching negative balances", () => {
  const tree = buildAccountTree();

  const negative = [
    ...all_matching(
      tree,
      (n) => Object.values(n.balance).some((v) => v < 0),
    ),
  ];
  const names = negative.map((n) => n.name).sort();
  ok(names.includes("Income:Salary"));
  ok(names.includes("Liabilities:CreditCard"));
});

test("tree: stratifyAccounts single root only", () => {
  const tree = stratifyAccounts(
    ["SingleRoot"],
    (s) => s,
    (name) => ({ name }),
  );

  deepEqual(tree, {
    name: "",
    children: [{ name: "SingleRoot", children: [] }],
  });
});

test("tree: stratify single-level tree", () => {
  const items = ["a", "b", "c"];
  const tree = stratify(
    items,
    (s) => s,
    (name) => ({ name, id: name.toUpperCase() }),
    () => "",
  );

  equal(tree.children.length, 3);
  deepEqual(tree.children.map((c) => c.id).sort(), ["A", "B", "C"]);
});

type TimeFilteredNode = TreeNode<{
  name: string;
  balance: Record<string, number>;
  period: string;
}>;

function buildTreeForPeriod(period: string): TimeFilteredNode {
  const datasets: Record<string, { account: string; balance: Record<string, number> }[]> = {
    "2024-01": [
      { account: "Assets:Cash", balance: { EUR: 1900, USD: -50 } },
      { account: "Income:Salary", balance: { EUR: -2000 } },
      { account: "Expenses:Food:Groceries", balance: { EUR: 100, USD: 50 } },
    ],
    "2024-02": [
      { account: "Assets:Bank:Checking", balance: { EUR: 2200 } },
      { account: "Income:Salary", balance: { EUR: -2200 } },
      { account: "Expenses:Food:Restaurant", balance: { EUR: 80 } },
    ],
    "2024-03": [
      { account: "Assets:Cash", balance: { EUR: 1980 } },
      { account: "Income:Salary", balance: { EUR: -2100 } },
      { account: "Expenses:Food:Groceries", balance: { EUR: 120 } },
    ],
    "2024-Q1": [
      { account: "Assets:Cash", balance: { EUR: 3800, USD: -50 } },
      { account: "Assets:Bank:Checking", balance: { EUR: 2200 } },
      { account: "Income:Salary", balance: { EUR: -6300 } },
      { account: "Expenses:Food:Groceries", balance: { EUR: 220, USD: 50 } },
      { account: "Expenses:Food:Restaurant", balance: { EUR: 80 } },
    ],
    empty: [],
  };
  const data = datasets[period] ?? [];
  return stratifyAccounts(
    data,
    (d) => d.account,
    (name, datum) => ({
      name,
      balance: datum?.balance ?? {},
      period,
    }),
  );
}

test("tree: time-filtered january balances and hierarchy", () => {
  const tree = buildTreeForPeriod("2024-01");

  const assets = tree.children.find((c) => c.name === "Assets");
  ok(assets);
  equal(assets.children.length, 1);
  equal(assets.children[0].name, "Assets:Cash");
  deepEqual(assets.children[0].balance, { EUR: 1900, USD: -50 });

  const income = tree.children.find((c) => c.name === "Income");
  ok(income);
  deepEqual(income.children[0].balance, { EUR: -2000 });

  const expenses = tree.children.find((c) => c.name === "Expenses");
  ok(expenses);
  equal(expenses.children.length, 1);
  equal(expenses.children[0].name, "Expenses:Food");

  const groceries = expenses.children[0].children.find(
    (c) => c.name === "Expenses:Food:Groceries",
  );
  ok(groceries);
  deepEqual(groceries.balance, { EUR: 100, USD: 50 });

  const restaurant = expenses.children[0].children.find(
    (c) => c.name === "Expenses:Food:Restaurant",
  );
  ok(!restaurant, "restaurant should not appear in January");
});

test("tree: time-filtered february excludes january-only accounts", () => {
  const tree = buildTreeForPeriod("2024-02");

  const expenses = tree.children.find((c) => c.name === "Expenses");
  ok(expenses);
  equal(expenses.children.length, 1);

  const food = expenses.children[0];
  equal(food.name, "Expenses:Food");
  equal(food.children.length, 1);
  equal(food.children[0].name, "Expenses:Food:Restaurant");
  deepEqual(food.children[0].balance, { EUR: 80 });

  const groceries = food.children.find(
    (c) => c.name === "Expenses:Food:Groceries",
  );
  ok(!groceries, "groceries should not appear in February");

  const assets = tree.children.find((c) => c.name === "Assets");
  ok(assets);
  equal(assets.children.length, 1);
  equal(assets.children[0].name, "Assets:Bank");
  equal(assets.children[0].children.length, 1);
  equal(assets.children[0].children[0].name, "Assets:Bank:Checking");
  deepEqual(assets.children[0].children[0].balance, { EUR: 2200 });
});

test("tree: time-filtered empty interval has no accounts", () => {
  const tree = buildTreeForPeriod("empty");
  equal(tree.children.length, 0);
  deepEqual(tree.balance, {});
});

test("tree: time-filtered multi-currency Q1 aggregated correctly", () => {
  const tree = buildTreeForPeriod("2024-Q1");

  const assets = tree.children.find((c) => c.name === "Assets");
  ok(assets);
  const assetNames = assets.children.map((c) => c.name).sort();
  deepEqual(assetNames, ["Assets:Bank", "Assets:Cash"]);

  const cash = assets.children.find((c) => c.name === "Assets:Cash");
  ok(cash);
  deepEqual(cash.balance, { EUR: 3800, USD: -50 });

  const bank = assets.children.find((c) => c.name === "Assets:Bank");
  ok(bank);
  equal(bank.children.length, 1);
  equal(bank.children[0].name, "Assets:Bank:Checking");
  deepEqual(bank.children[0].balance, { EUR: 2200 });

  const expenses = tree.children.find((c) => c.name === "Expenses");
  ok(expenses);
  const food = expenses.children[0];
  equal(food.children.length, 2);

  const groceries = food.children.find((c) => c.name === "Expenses:Food:Groceries");
  ok(groceries);
  deepEqual(groceries.balance, { EUR: 220, USD: 50 });

  const restaurant = food.children.find(
    (c) => c.name === "Expenses:Food:Restaurant",
  );
  ok(restaurant);
  deepEqual(restaurant.balance, { EUR: 80 });
});

test("tree: time-filtered march excludes USD transactions from january", () => {
  const tree = buildTreeForPeriod("2024-03");

  const expenses = tree.children.find((c) => c.name === "Expenses");
  ok(expenses);
  const food = expenses.children[0];

  const groceries = food.children.find(
    (c) => c.name === "Expenses:Food:Groceries",
  );
  ok(groceries);
  deepEqual(groceries.balance, { EUR: 120 });
  ok(!("USD" in groceries.balance));
});

test("tree: time-filtered hierarchy structure preserved across periods", () => {
  const janTree = buildTreeForPeriod("2024-01");
  const q1Tree = buildTreeForPeriod("2024-Q1");

  function collectAccounts(node: TimeFilteredNode): Set<string> {
    const set = new Set<string>();
    function walk(n: TimeFilteredNode) {
      set.add(n.name);
      n.children.forEach(walk);
    }
    walk(node);
    return set;
  }

  const janAccounts = collectAccounts(janTree);
  const q1Accounts = collectAccounts(q1Tree);

  for (const acc of janAccounts) {
    ok(q1Accounts.has(acc), `Q1 should contain all January accounts: ${acc}`);
  }
});

test("tree: all_matching within a time-filtered view", () => {
  const tree = buildTreeForPeriod("2024-Q1");

  const multiCurrency = [...all_matching(tree, (n) => Object.keys(n.balance).length >= 2)];
  ok(multiCurrency.length >= 2);
  const names = multiCurrency.map((n) => n.name).sort();
  ok(names.includes("Assets:Cash"));
  ok(names.includes("Expenses:Food:Groceries"));

  const usdAccounts = [...all_matching(tree, (n) => "USD" in n.balance)];
  ok(usdAccounts.every((n) => "USD" in n.balance));
});

