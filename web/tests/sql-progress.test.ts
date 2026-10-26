import { afterEach, describe, expect, it, vi } from "vitest";
import { markSolved, solved, STORAGE_KEY } from "../lib/sql/progress";

// The progress of /sql (task 101, `lib/sql/progress.ts`): solved ids under one key, and a course
// that works when storage throws (a private window, a blocked origin) or holds something else.

function fakeStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    store,
  };
}

const throwing = {
  getItem: () => {
    throw new Error("SecurityError");
  },
  setItem: () => {
    throw new Error("SecurityError");
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("progress", () => {
  it("reads nothing solved where there is no storage at all", () => {
    vi.stubGlobal("localStorage", undefined);
    expect(solved()).toEqual([]);
  });

  it("keeps what was solved in memory when storage throws", () => {
    vi.stubGlobal("localStorage", throwing);
    expect(solved()).toEqual([]);
    expect(() => markSolved("select-1")).not.toThrow();
    expect(solved()).toContain("select-1");
  });

  it("writes the ids under one key and reads them back, the same array while nothing changed", () => {
    const storage = fakeStorage();
    vi.stubGlobal("localStorage", storage);
    markSolved("select-2");
    expect(JSON.parse(storage.store.get(STORAGE_KEY)!)).toContain("select-2");
    const a = solved();
    expect(solved()).toBe(a);
    markSolved("select-2");
    expect(solved()).toBe(a);
  });

  it("ignores a key that holds something that is not a list of ids", () => {
    vi.stubGlobal("localStorage", fakeStorage({ [STORAGE_KEY]: "{not json" }));
    expect(solved()).toEqual([]);
    vi.stubGlobal("localStorage", fakeStorage({ [STORAGE_KEY]: JSON.stringify({ a: 1 }) }));
    expect(solved()).toEqual([]);
    vi.stubGlobal("localStorage", fakeStorage({ [STORAGE_KEY]: JSON.stringify(["where-1", 3, null]) }));
    expect(solved()).toEqual(["where-1"]);
  });
});
