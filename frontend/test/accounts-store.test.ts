import { deepEqual, equal, ok } from "node:assert/strict";
import { get as store_get } from "svelte/store";
import { test } from "node:test";

import { setup_jsdom } from "./dom.ts";
import { initialiseLedgerData } from "./helpers.ts";

import { is_descendant, parent } from "../src/lib/account.ts";
import { get_internal_accounts } from "../src/lib/account.ts";
import { expand_all, is_closed_account, toggle_account, toggled_accounts } from "../src/stores/accounts.ts";
import { account_details, accounts, accounts_internal } from "../src/stores/index.ts";
import { current_url } from "../src/stores/url.ts";
import { time_filter } from "../src/stores/filters.ts";

test.before(initialiseLedgerData);
test.beforeEach(setup_jsdom);

test("accounts-store: accounts and accounts_internal populated", () => {
  const $accounts = store_get(accounts);
  const $accounts_internal = store_get(accounts_internal);

  ok($accounts.length > 0, "accounts should not be empty");

  const expected_internal = get_internal_accounts($accounts);
  deepEqual([...$accounts_internal].sort(), [...expected_internal].sort());

  const topLevel = new Set<string>();
  for (const acc of $accounts) {
    const root = acc.split(":")[0];
    if (root) topLevel.add(root);
  }
  ok(topLevel.size >= 3, "should have multiple top-level account types");
});

test("accounts-store: toggled_accounts is a Set", () => {
  const $toggled = store_get(toggled_accounts);
  ok($toggled instanceof Set);
});

function makeMouseEvent(overrides: Partial<MouseEvent> = {}): MouseEvent {
  return {
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    ...overrides,
  } as MouseEvent;
}

test("accounts-store: toggle_account simple toggle", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length === 0) {
    return;
  }
  const target = $accounts_internal[0];

  expand_all("");
  const $initial = store_get(toggled_accounts);
  const wasToggled = $initial.has(target);

  toggle_account(target, makeMouseEvent());

  const $after = store_get(toggled_accounts);
  equal($after.has(target), !wasToggled);

  toggle_account(target, makeMouseEvent());
  const $back = store_get(toggled_accounts);
  equal($back.has(target), wasToggled);
});

test("accounts-store: expand_all expands descendants", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length === 0) {
    return;
  }

  $accounts_internal.forEach((a) => toggle_account(a, makeMouseEvent()));
  let $toggled = store_get(toggled_accounts);
  ok($toggled.size > 0, "should have some toggled accounts");

  expand_all("");
  $toggled = store_get(toggled_accounts);
  equal($toggled.size, 0, "expand_all root should clear all");
});

test("accounts-store: toggle_account with shiftKey when opening expands deeply", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length === 0) {
    return;
  }

  expand_all("");

  const parentAccount = $accounts_internal.find(
    (a) => $accounts_internal.some((c) => is_descendant(a)(c)),
  );
  if (!parentAccount) {
    return;
  }

  const descendants = $accounts_internal.filter((a) => is_descendant(parentAccount)(a));
  ok(descendants.length > 0);

  descendants.forEach((d) => toggle_account(d, makeMouseEvent()));
  toggle_account(parentAccount, makeMouseEvent());

  let $toggled = store_get(toggled_accounts);
  ok($toggled.has(parentAccount));
  descendants.forEach((d) => ok($toggled.has(d)));

  toggle_account(parentAccount, makeMouseEvent({ shiftKey: true }));

  $toggled = store_get(toggled_accounts);
  ok(!$toggled.has(parentAccount));
  descendants.forEach((d) => ok(!$toggled.has(d)));
});

test("accounts-store: toggle_account with ctrlKey when opening toggles direct children", () => {
  const $accounts_internal = store_get(accounts_internal);

  const parentAccount = $accounts_internal.find(
    (a) => $accounts_internal.filter((c) => parent(c) === a).length >= 1,
  );
  if (!parentAccount) {
    return;
  }
  const directChildren = $accounts_internal.filter((c) => parent(c) === parentAccount);
  ok(directChildren.length >= 1, "need direct children");

  expand_all("");
  toggle_account(parentAccount, makeMouseEvent());
  let $toggled = store_get(toggled_accounts);
  ok($toggled.has(parentAccount));
  directChildren.forEach((c) => ok(!$toggled.has(c)));

  toggle_account(parentAccount, makeMouseEvent({ ctrlKey: true }));

  $toggled = store_get(toggled_accounts);
  ok(!$toggled.has(parentAccount));
  for (const c of directChildren) {
    ok($toggled.has(c), `direct child ${c} should be toggled`);
  }
});

test("accounts-store: is_closed_account function type", () => {
  const $is_closed = store_get(is_closed_account);
  ok(typeof $is_closed === "function");
});

test("accounts-store: is_closed_account without close_date returns false", () => {
  const $is_closed = store_get(is_closed_account);
  const $accounts = store_get(accounts);
  const $account_details = store_get(account_details);

  const openAccount = $accounts.find(
    (acc) => !($account_details[acc]?.close_date),
  );
  if (openAccount) {
    equal($is_closed(openAccount, null), false);
    equal($is_closed(openAccount, new Date("2050-01-01")), false);
  }
});

test("accounts-store: is_closed_account with close_date respects date", () => {
  const $is_closed = store_get(is_closed_account);
  const $account_details = store_get(account_details);

  for (const [acc, details] of Object.entries($account_details)) {
    const closeDate = details?.close_date;
    if (closeDate != null) {
      equal($is_closed(acc, null), true);

      const closeDateObj = new Date(closeDate);
      const afterClose = new Date(closeDateObj);
      afterClose.setDate(afterClose.getDate() + 1);
      equal($is_closed(acc, afterClose), true);

      const beforeClose = new Date(closeDateObj);
      beforeClose.setDate(beforeClose.getDate() - 1);
      equal($is_closed(acc, beforeClose), false);
      break;
    }
  }
});

test("accounts-store: multi-currency accounts list populated", () => {
  const $accounts = store_get(accounts);
  ok($accounts.length > 0);

  const hasMulti = $accounts.some((a) => a.includes("ETrade") || a.includes("Cash"));
  ok(hasMulti || $accounts.length > 10);
});

test("accounts-store: toggle state persists across multiple toggles", () => {
  const $accounts_internal = store_get(accounts_internal);
  const testAccounts = $accounts_internal.slice(0, Math.min(5, $accounts_internal.length));
  if (testAccounts.length === 0) {
    return;
  }

  expand_all("");
  let $toggled = store_get(toggled_accounts);
  testAccounts.forEach((a) => ok(!$toggled.has(a)));

  testAccounts.forEach((a) => toggle_account(a, makeMouseEvent()));
  $toggled = store_get(toggled_accounts);
  testAccounts.forEach((a) => ok($toggled.has(a)));

  testAccounts.forEach((a) => toggle_account(a, makeMouseEvent()));
  $toggled = store_get(toggled_accounts);
  testAccounts.forEach((a) => ok(!$toggled.has(a)));
});

test("accounts-store: expand_all on specific subtree", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length === 0) {
    return;
  }

  $accounts_internal.forEach((a) => toggle_account(a, makeMouseEvent()));
  let $toggled = store_get(toggled_accounts);
  const initialSize = $toggled.size;
  ok(initialSize > 0);

  const firstRoot = $accounts_internal[0].split(":")[0];
  expand_all(firstRoot);

  $toggled = store_get(toggled_accounts);
  const rootDescendants = $accounts_internal.filter(
    (a) => is_descendant(firstRoot)(a) || a === firstRoot,
  );
  for (const acc of rootDescendants) {
    ok(!$toggled.has(acc));
  }
});

function snapshotToggleState(): Set<string> {
  return new Set(store_get(toggled_accounts));
}

test("accounts-store: time_filter change does not reset toggled state", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length < 3) {
    return;
  }

  expand_all("");
  let $toggledBefore = snapshotToggleState();
  equal($toggledBefore.size, 0);

  const testAccounts = $accounts_internal.slice(0, 3);
  testAccounts.forEach((a) => toggle_account(a, makeMouseEvent()));
  $toggledBefore = snapshotToggleState();
  testAccounts.forEach((a) => ok($toggledBefore.has(a)));

  const beforeTime = store_get(time_filter);

  current_url.set(new URL(`http://localhost/example?time=2017`));

  const afterTime = store_get(time_filter);
  equal(afterTime, "2017");
  ok(beforeTime !== afterTime);

  const $toggledAfter = snapshotToggleState();
  deepEqual([...$toggledAfter].sort(), [...$toggledBefore].sort());
  testAccounts.forEach((a) => ok($toggledAfter.has(a)));
});

test("accounts-store: switching between multiple time filters preserves toggled state", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length < 5) {
    return;
  }

  expand_all("");

  const toggledAccounts = $accounts_internal.slice(0, 5);
  toggledAccounts.forEach((a) => toggle_account(a, makeMouseEvent()));
  const state0 = snapshotToggleState();
  toggledAccounts.forEach((a) => ok(state0.has(a)));

  current_url.set(new URL("http://localhost/example?time=2016"));
  const state1 = snapshotToggleState();
  deepEqual([...state1].sort(), [...state0].sort());

  toggle_account(toggledAccounts[0], makeMouseEvent());
  const state2 = snapshotToggleState();
  ok(!state2.has(toggledAccounts[0]));

  current_url.set(new URL("http://localhost/example?time=2017-Q1"));
  const state3 = snapshotToggleState();
  deepEqual([...state3].sort(), [...state2].sort());
  ok(!state3.has(toggledAccounts[0]));
  toggledAccounts.slice(1).forEach((a) => ok(state3.has(a)));
});

test("accounts-store: clearing time filter preserves toggled state", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length < 3) {
    return;
  }

  current_url.set(new URL("http://localhost/example?time=2016"));
  equal(store_get(time_filter), "2016");

  expand_all("");
  const targets = $accounts_internal.slice(0, 3);
  targets.forEach((a) => toggle_account(a, makeMouseEvent()));
  const before = snapshotToggleState();
  targets.forEach((a) => ok(before.has(a)));

  current_url.set(new URL("http://localhost/example"));
  equal(store_get(time_filter), "");

  const after = snapshotToggleState();
  deepEqual([...after].sort(), [...before].sort());
  targets.forEach((a) => ok(after.has(a)));
});

test("accounts-store: time filter change does not affect expand_all reset", () => {
  const $accounts_internal = store_get(accounts_internal);
  if ($accounts_internal.length < 3) {
    return;
  }

  current_url.set(new URL("http://localhost/example?time=2017"));

  expand_all("");
  equal(snapshotToggleState().size, 0);

  const toToggle = $accounts_internal.slice(0, 5);
  toToggle.forEach((a) => toggle_account(a, makeMouseEvent()));
  ok(snapshotToggleState().size >= toToggle.length);

  expand_all("");
  equal(snapshotToggleState().size, 0);
});

