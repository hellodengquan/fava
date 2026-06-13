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

test("Snapshots: shows empty state when no snapshots exist", async () => {
  const { snapshot_api } = await import("../src/api/index.ts");

  const original_get = snapshot_api.get_snapshots;

  snapshot_api.get_snapshots = async () => {
    return [];
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

    const table = document.querySelector("table.snapshot-table");
    equal(table, null, "should not render a table when list is empty");

    const empty_msg = document.querySelector(".snapshot-list-section p");
    ok(empty_msg, "should show an empty-state message");
    ok(
      empty_msg!.textContent!.includes("No snapshots"),
      "empty-state message should mention 'No snapshots'",
    );

    const compare_btn = document.querySelector("button.compare-btn");
    equal(compare_btn, null, "compare button should not be shown when empty");

    unmount(component);
  } finally {
    snapshot_api.get_snapshots = original_get;
  }
});

test("Snapshots: shows loading state before API resolves", async () => {
  const { snapshot_api } = await import("../src/api/index.ts");

  const original_get = snapshot_api.get_snapshots;

  let resolve_get!: (value: typeof MOCK_SNAPSHOTS) => void;
  const pending_promise = new Promise<typeof MOCK_SNAPSHOTS>((resolve) => {
    resolve_get = resolve;
  });

  snapshot_api.get_snapshots = async () => {
    return pending_promise;
  };

  try {
    const { default: SnapshotsComponent } = await import(
      "../src/reports/snapshots/Snapshots.svelte"
    );

    const component = mount(SnapshotsComponent, {
      target: document.body,
    });

    flushSync();

    const loading_msg = document.querySelector(".snapshot-list-section p");
    ok(loading_msg, "should show a loading message");
    ok(
      loading_msg!.textContent!.includes("Loading"),
      "loading message should contain 'Loading'",
    );

    const table_before = document.querySelector("table.snapshot-table");
    equal(table_before, null, "table should not render during loading");

    resolve_get(MOCK_SNAPSHOTS);
    await tick();
    await tick();
    flushSync();

    const snapshot_list_section = document.querySelector(".snapshot-list-section");
    ok(snapshot_list_section, "snapshot list section should exist");

    const table_after = document.querySelector("table.snapshot-table");
    if (!table_after) {
      const msg = document.querySelector(".snapshot-list-section p");
      ok(false, `table should render after loading, but got: ${msg?.textContent}`);
    }
    ok(table_after, "table should render after loading completes");

    unmount(component);
  } finally {
    snapshot_api.get_snapshots = original_get;
  }
});

test("Snapshots: error fallback shows empty state without crashing", async () => {
  const { snapshot_api } = await import("../src/api/index.ts");

  const original_get = snapshot_api.get_snapshots;

  snapshot_api.get_snapshots = async () => {
    throw new Error("Network error: Failed to fetch snapshots");
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

    const table = document.querySelector("table.snapshot-table");
    equal(table, null, "should not render a table after error");

    const empty_msg = document.querySelector(".snapshot-list-section p");
    ok(empty_msg, "should show empty-state message after error");
    ok(
      empty_msg!.textContent!.includes("No snapshots"),
      "empty-state message should indicate no snapshots",
    );

    const loading_msg = document.querySelector(".snapshot-list-section p");
    ok(
      !loading_msg!.textContent!.includes("Loading"),
      "should not show loading message after error resolves",
    );

    unmount(component);
  } finally {
    snapshot_api.get_snapshots = original_get;
  }
});

test("Snapshots: HTTP 500 error degrades to empty state with notification", async () => {
  const { snapshot_api } = await import("../src/api/index.ts");
  const { FetchHTTPError } = await import("../src/lib/fetch.ts");

  const original_get = snapshot_api.get_snapshots;

  snapshot_api.get_snapshots = async () => {
    throw new FetchHTTPError("Internal Server Error", 500);
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

    const table = document.querySelector("table.snapshot-table");
    equal(table, null, "should not render a table after 500 error");

    const section = document.querySelector(".snapshot-list-section");
    ok(section, "snapshot list section should exist after 500");

    const msg = section!.querySelector("p");
    ok(msg, "should show a message in the section");
    ok(
      msg!.textContent!.includes("No snapshots"),
      "should show empty-state message, not crash or show raw error",
    );
    ok(
      !msg!.textContent!.includes("Loading"),
      "loading state should be cleared after 500 error",
    );
    ok(
      !msg!.textContent!.includes("500"),
      "should not leak raw HTTP error to the user-facing message",
    );
    ok(
      !msg!.textContent!.includes("Internal Server Error"),
      "should not expose internal error details to the user",
    );

    const compare_btn = document.querySelector("button.compare-btn");
    equal(compare_btn, null, "compare button should not appear after 500 error");

    const clean_btn = document.querySelector("button.clean-btn");
    equal(clean_btn, null, "clean button should not appear after 500 error");

    unmount(component);
  } finally {
    snapshot_api.get_snapshots = original_get;
  }
});

test("Snapshots: HTTP 500 on compare preserves existing snapshot list", async () => {
  const { snapshot_api } = await import("../src/api/index.ts");
  const { FetchHTTPError } = await import("../src/lib/fetch.ts");

  const original_get = snapshot_api.get_snapshots;
  const original_compare = snapshot_api.get_snapshot_compare;

  snapshot_api.get_snapshots = async () => {
    return MOCK_SNAPSHOTS;
  };
  snapshot_api.get_snapshot_compare = async () => {
    throw new FetchHTTPError("Internal Server Error", 500);
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

    const rows_before = document.querySelectorAll("table.snapshot-table tbody tr");
    equal(rows_before.length, 3, "should render 3 snapshot rows before compare");

    const radios_a = document.querySelectorAll('input[name="snapshot_a"]');
    const radios_b = document.querySelectorAll('input[name="snapshot_b"]');
    (radios_a[0] as HTMLInputElement).click();
    flushSync();
    (radios_b[1] as HTMLInputElement).click();
    flushSync();

    const compare_btn = document.querySelector("button.compare-btn") as HTMLButtonElement;
    ok(!compare_btn.disabled, "compare button should be enabled");

    compare_btn.click();
    await tick();
    flushSync();

    const rows_after = document.querySelectorAll("table.snapshot-table tbody tr");
    equal(rows_after.length, 3, "snapshot list should still be intact after 500 on compare");

    const compare_section = document.querySelector(".compare-result-section");
    equal(compare_section, null, "comparison result section should not appear after 500");

    const compare_btn_after = document.querySelector("button.compare-btn") as HTMLButtonElement;
    ok(compare_btn_after, "compare button should still be visible after 500");
    ok(!compare_btn_after.disabled, "compare button should be re-enabled after 500 error resolves");

    unmount(component);
  } finally {
    snapshot_api.get_snapshots = original_get;
    snapshot_api.get_snapshot_compare = original_compare;
  }
});
