import { equal, ok } from "node:assert/strict";
import { test } from "node:test";

import { flushSync, mount, tick, unmount } from "svelte";

import { setup_jsdom } from "./dom.ts";
import { initialiseLedgerData } from "./helpers.ts";

const MOCK_SNAPSHOTS = [
  {
    id: "snap-001",
    name: "January Balance",
    created_at: "2024-01-31T23:59:59",
    filters: { time: "2024-01", account: "", filter: "", conversion: "", interval: "" },
    report_type: "balance_sheet",
  },
  {
    id: "snap-002",
    name: "February Balance",
    created_at: "2024-02-29T23:59:59",
    filters: { time: "2024-02", account: "", filter: "", conversion: "", interval: "" },
    report_type: "balance_sheet",
  },
  {
    id: "snap-003",
    name: "March Income",
    created_at: "2024-03-31T23:59:59",
    filters: { time: "2024-03", account: "", filter: "", conversion: "", interval: "" },
    report_type: "income_statement",
  },
];

const MOCK_COMPARE_RESULT = {
  snapshot_a: {
    id: "snap-001",
    name: "January Balance",
    created_at: "2024-01-31T23:59:59",
    filters: { time: "2024-01", account: "", filter: "", conversion: "", interval: "" },
  },
  snapshot_b: {
    id: "snap-002",
    name: "February Balance",
    created_at: "2024-02-29T23:59:59",
    filters: { time: "2024-02", account: "", filter: "", conversion: "", interval: "" },
  },
  balance_diff: {
    "Assets:Cash": { USD: 500 },
    "Assets:Bank": { USD: -200 },
  },
  tree_diff: [],
  budget_diff: null,
  holdings_diff: null,
};

test.before(initialiseLedgerData);
test.beforeEach(setup_jsdom);

test("Snapshots: compare two snapshots via radio selection", async () => {
  const { snapshot_api } = await import("../src/api/index.ts");

  const original_get = snapshot_api.get_snapshots;
  const original_compare = snapshot_api.get_snapshot_compare;

  let get_snapshots_called = false;
  let get_snapshot_compare_called = false;

  snapshot_api.get_snapshots = async () => {
    get_snapshots_called = true;
    return MOCK_SNAPSHOTS;
  };
  snapshot_api.get_snapshot_compare = async () => {
    get_snapshot_compare_called = true;
    return MOCK_COMPARE_RESULT;
  };

  try {
    const { default: SnapshotsComponent } = await import(
      "../src/reports/snapshots/Snapshots.svelte"
    );

    const component = mount(SnapshotsComponent, {
      target: document.body,
    });

    await tick();
    flushSync();

    ok(get_snapshots_called, "get_snapshots should be called on mount");

    const rows = document.querySelectorAll("table.snapshot-table tbody tr");
    equal(rows.length, 3, "should render 3 snapshot rows");

    const radios_a = document.querySelectorAll('input[name="snapshot_a"]');
    const radios_b = document.querySelectorAll('input[name="snapshot_b"]');
    equal(radios_a.length, 3, "should have 3 radio buttons for snapshot_a");
    equal(radios_b.length, 3, "should have 3 radio buttons for snapshot_b");

    (radios_a[0] as HTMLInputElement).click();
    flushSync();
    (radios_b[1] as HTMLInputElement).click();
    flushSync();

    const compare_btn = document.querySelector("button.compare-btn") as HTMLButtonElement;
    ok(compare_btn, "compare button should exist");
    ok(!compare_btn.disabled, "compare button should be enabled after selection");

    compare_btn.click();
    await tick();
    flushSync();

    ok(get_snapshot_compare_called, "get_snapshot_compare should be called");

    await tick();
    flushSync();

    const diff_rows = document.querySelectorAll(".diff-table tbody tr");
    ok(diff_rows.length >= 1, "should render at least one balance diff row");

    unmount(component);
  } finally {
    snapshot_api.get_snapshots = original_get;
    snapshot_api.get_snapshot_compare = original_compare;
  }
});

test("Snapshots: delete a snapshot removes it from the list", async () => {
  const { snapshot_api } = await import("../src/api/index.ts");

  const original_get = snapshot_api.get_snapshots;
  const original_delete = snapshot_api.delete_snapshot;

  let get_snapshots_called = false;
  let delete_called_with_id: string | null = null;

  snapshot_api.get_snapshots = async () => {
    get_snapshots_called = true;
    return MOCK_SNAPSHOTS;
  };
  snapshot_api.delete_snapshot = async (params: { snapshot_id: string }) => {
    delete_called_with_id = params.snapshot_id;
    return "Deleted snapshot";
  };

  try {
    const { default: SnapshotsComponent } = await import(
      "../src/reports/snapshots/Snapshots.svelte"
    );

    const component = mount(SnapshotsComponent, {
      target: document.body,
    });

    await tick();
    flushSync();

    ok(get_snapshots_called, "get_snapshots should be called on mount");

    let rows = document.querySelectorAll("table.snapshot-table tbody tr");
    equal(rows.length, 3, "should render 3 snapshot rows initially");

    const delete_buttons = document.querySelectorAll("button.delete-btn");
    equal(delete_buttons.length, 3, "should have 3 delete buttons");

    (delete_buttons[0] as HTMLButtonElement).click();
    await tick();
    flushSync();

    ok(delete_called_with_id !== null, "delete_snapshot should be called");
    equal(delete_called_with_id, "snap-001", "should delete the correct snapshot");

    rows = document.querySelectorAll("table.snapshot-table tbody tr");
    equal(rows.length, 2, "should have 2 rows after deletion");

    unmount(component);
  } finally {
    snapshot_api.get_snapshots = original_get;
    snapshot_api.delete_snapshot = original_delete;
  }
});
