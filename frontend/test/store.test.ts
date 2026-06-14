import { deepEqual, equal, throws } from "node:assert/strict";
import { test } from "node:test";

import { get as store_get, writable } from "svelte/store";

import { derived_array, localStorageSyncedStore } from "../src/lib/store.ts";
import { chartToggledCurrencies } from "../src/stores/chart.ts";
import { string } from "../src/lib/validation.ts";
import { setup_jsdom } from "./dom.ts";

test.beforeEach(setup_jsdom);

test("derived store", () => {
  const source = writable<string[]>([]);
  const derived = derived_array(source, (s) => s);
  let source_count = 0;
  source.subscribe(() => {
    source_count += 1;
  });
  let derived_count = 0;
  derived.subscribe(() => {
    derived_count += 1;
  });
  source.set([]);
  source.set([]);
  source.set(["a", "b"]);
  source.set(["a", "b"]);
  source.set(["a", "b"]);
  equal(source_count, 6);
  equal(derived_count, 2);
});

test("localStorage-synced stores", () => {
  const a = localStorageSyncedStore("test-store", string, () => "default");
  equal(a.key, "fava-test-store");
  deepEqual(a.values(), []);

  // Getting the value will temporarily attach a subscriber (and unsubscribe as well).
  localStorage.removeItem(a.key);
  equal(store_get(a), "default");

  localStorage.setItem(a.key, "invalid-non-json-stringified");
  equal(store_get(a), "default");

  localStorage.setItem(a.key, JSON.stringify("value"));
  equal(store_get(a), "value");

  a.set("another-value");
  equal(store_get(a), "another-value");
  equal(localStorage.getItem(a.key), JSON.stringify("another-value"));

  a.update(() => "a-value");
  equal(store_get(a), "a-value");
  equal(localStorage.getItem(a.key), JSON.stringify("a-value"));

  const seen_values: string[] = [];
  const unsubscribe = a.subscribe((v) => {
    seen_values.push(v);
  });
  window.dispatchEvent(
    new StorageEvent("storage", {
      key: a.key,
      newValue: JSON.stringify("event-value-different-storage-area"),
      storageArea: sessionStorage,
    }),
  );
  window.dispatchEvent(
    new StorageEvent("storage", {
      key: "fava-wrong-key",
      newValue: JSON.stringify("event-value-wrong-key"),
      storageArea: localStorage,
    }),
  );
  window.dispatchEvent(
    new StorageEvent("storage", {
      key: a.key,
      newValue: JSON.stringify("event-value"),
      storageArea: localStorage,
    }),
  );
  unsubscribe();
  deepEqual(seen_values, ["a-value", "event-value"]);

  throws(() => {
    // The prefix is added automatically.
    localStorageSyncedStore("fava-test-store", string, () => "value");
  });
  throws(() => {
    // No duplicate stores
    localStorageSyncedStore("test-store", string, () => "value");
  });
});

test("localStorage-synced store reset via storage event (cross-tab sync)", () => {
  const store = localStorageSyncedStore(
    "sync-reset-test",
    string,
    () => "default-val",
  );

  store.set("current-value");
  equal(store_get(store), "current-value");

  const seen_values: string[] = [];
  const unsubscribe = store.subscribe((v) => {
    seen_values.push(v);
  });

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("new-tab-value"),
      storageArea: localStorage,
    }),
  );
  equal(store_get(store), "new-tab-value");

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: null,
      storageArea: localStorage,
    }),
  );
  equal(store_get(store), "default-val");

  unsubscribe();
  deepEqual(seen_values, [
    "current-value",
    "new-tab-value",
    "default-val",
  ]);
});

test("localStorage-synced store ignores storage events from other storage areas", () => {
  const store = localStorageSyncedStore(
    "sync-area-test",
    string,
    () => "default",
  );
  store.set("original");

  const seen_values: string[] = [];
  const unsubscribe = store.subscribe((v) => {
    seen_values.push(v);
  });

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("from-session"),
      storageArea: sessionStorage,
    }),
  );
  equal(store_get(store), "original");

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: "wrong-key",
      newValue: JSON.stringify("from-wrong"),
      storageArea: localStorage,
    }),
  );
  equal(store_get(store), "original");

  unsubscribe();
  deepEqual(seen_values, ["original"]);
});

test("localStorage-synced store invalid JSON via storage event falls back to default", () => {
  const store = localStorageSyncedStore(
    "sync-invalid-test",
    string,
    () => "fallback",
  );
  store.set("valid-value");

  const seen_values: string[] = [];
  const unsubscribe = store.subscribe((v) => {
    seen_values.push(v);
  });

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: "not-valid-json{{{",
      storageArea: localStorage,
    }),
  );
  equal(store_get(store), "fallback");

  unsubscribe();
  deepEqual(seen_values, ["valid-value", "fallback"]);
});

test("chartToggledCurrencies syncs across tabs via storage event", () => {
  localStorage.removeItem(chartToggledCurrencies.key);
  equal(store_get(chartToggledCurrencies).length, 0);

  chartToggledCurrencies.set(["USD", "EUR"]);
  deepEqual(store_get(chartToggledCurrencies), ["USD", "EUR"]);

  const seen: string[][] = [];
  const unsubscribe = chartToggledCurrencies.subscribe((v) => {
    seen.push([...v]);
  });

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: chartToggledCurrencies.key,
      newValue: JSON.stringify(["GBP", "JPY"]),
      storageArea: localStorage,
    }),
  );
  deepEqual(store_get(chartToggledCurrencies), ["GBP", "JPY"]);

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: chartToggledCurrencies.key,
      newValue: null,
      storageArea: localStorage,
    }),
  );
  deepEqual(store_get(chartToggledCurrencies), []);

  unsubscribe();
  deepEqual(seen, [
    ["USD", "EUR"],
    ["GBP", "JPY"],
    [],
  ]);
});

test("localStorage-synced store multiple rapid storage events (rapid tab switches)", () => {
  const store = localStorageSyncedStore(
    "sync-rapid-test",
    string,
    () => "initial",
  );

  const seen_values: string[] = [];
  const unsubscribe = store.subscribe((v) => {
    seen_values.push(v);
  });

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("val1"),
      storageArea: localStorage,
    }),
  );
  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("val2"),
      storageArea: localStorage,
    }),
  );
  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("val3"),
      storageArea: localStorage,
    }),
  );

  equal(store_get(store), "val3");
  unsubscribe();
  deepEqual(seen_values, ["initial", "val1", "val2", "val3"]);
});

test("localStorage-synced store set after unsubscribe does not trigger listener", () => {
  const store = localStorageSyncedStore(
    "sync-unsub-test",
    string,
    () => "default",
  );

  let count = 0;
  const unsubscribe = store.subscribe(() => {
    count += 1;
  });

  equal(count, 1);

  unsubscribe();

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("after-unsub"),
      storageArea: localStorage,
    }),
  );

  equal(count, 1);
});

test("multi-instance: stores with different keys are isolated (namespace isolation)", () => {
  const storeA = localStorageSyncedStore(
    "multi-instance-a",
    string,
    () => "default-a",
  );
  const storeB = localStorageSyncedStore(
    "multi-instance-b",
    string,
    () => "default-b",
  );

  equal(store_get(storeA), "default-a");
  equal(store_get(storeB), "default-b");

  storeA.set("value-for-a");
  equal(store_get(storeA), "value-for-a");
  equal(store_get(storeB), "default-b");

  storeB.set("value-for-b");
  equal(store_get(storeA), "value-for-a");
  equal(store_get(storeB), "value-for-b");

  localStorage.removeItem(storeA.key);
  equal(store_get(storeB), "value-for-b");
});

test("multi-instance: storage event from different URL is handled (cross-page sync)", () => {
  const store = localStorageSyncedStore(
    "multi-instance-url",
    string,
    () => "initial",
  );

  const seen: string[] = [];
  const unsubscribe = store.subscribe((v) => {
    seen.push(v);
  });

  equal(store_get(store), "initial");

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("from-other-tab"),
      storageArea: localStorage,
      url: "http://other.example.com/fava/",
    }),
  );

  equal(store_get(store), "from-other-tab");
  deepEqual(seen, ["initial", "from-other-tab"]);

  unsubscribe();
});

test("multi-instance: multiple subscribers on same store all receive updates", () => {
  const store = localStorageSyncedStore(
    "multi-instance-subs",
    string,
    () => "start",
  );

  const seen1: string[] = [];
  const seen2: string[] = [];

  const unsub1 = store.subscribe((v) => {
    seen1.push(v);
  });
  const unsub2 = store.subscribe((v) => {
    seen2.push(v);
  });

  deepEqual(seen1, ["start"]);
  deepEqual(seen2, ["start"]);

  store.set("updated");

  deepEqual(seen1, ["start", "updated"]);
  deepEqual(seen2, ["start", "updated"]);

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("from-storage"),
      storageArea: localStorage,
    }),
  );

  deepEqual(seen1, ["start", "updated", "from-storage"]);
  deepEqual(seen2, ["start", "updated", "from-storage"]);

  unsub1();
  unsub2();
});

test("multi-instance: cross-origin storage event is ignored (security boundary)", () => {
  const store = localStorageSyncedStore(
    "multi-instance-xorigin",
    string,
    () => "safe",
  );

  const seen: string[] = [];
  const unsubscribe = store.subscribe((v) => {
    seen.push(v);
  });

  const fakeSessionStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
    clear: () => {},
    length: 0,
    key: () => null,
  } as unknown as Storage;

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store.key,
      newValue: JSON.stringify("from-xorigin"),
      storageArea: fakeSessionStorage,
    }),
  );

  equal(store_get(store), "safe");
  deepEqual(seen, ["safe"]);

  unsubscribe();
});

test("multi-instance: unrelated fava instance key does not trigger update", () => {
  const store1 = localStorageSyncedStore(
    "instance-1-filter",
    string,
    () => "default",
  );
  const store2 = localStorageSyncedStore(
    "instance-2-filter",
    string,
    () => "default",
  );

  const seen1: string[] = [];
  const seen2: string[] = [];

  const unsub1 = store1.subscribe((v) => {
    seen1.push(v);
  });
  const unsub2 = store2.subscribe((v) => {
    seen2.push(v);
  });

  window.dispatchEvent(
    new StorageEvent("storage", {
      key: store1.key,
      newValue: JSON.stringify("only-for-1"),
      storageArea: localStorage,
    }),
  );

  deepEqual(seen1, ["default", "only-for-1"]);
  deepEqual(seen2, ["default"]);
  equal(store_get(store1), "only-for-1");
  equal(store_get(store2), "default");

  unsub1();
  unsub2();
});
