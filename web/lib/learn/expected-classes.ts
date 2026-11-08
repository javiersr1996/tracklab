// The three zone classes of lesson 12, apart from expected-data.ts so that code the Playwright
// specs import (expected.ts) does not pull in the JSON file, which Node's loader refuses to import
// without an attribute.
export const CLASSES = ["rim", "mid", "three"] as const;
export type ZoneClass = (typeof CLASSES)[number];
