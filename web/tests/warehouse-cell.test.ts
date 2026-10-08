import { describe, expect, it } from "vitest";
import { cellText } from "../lib/warehouse/cell";

// How /warehouse writes a result value (`lib/warehouse/cell.ts`), fed what Arrow's `get()`
// returns for each type: a decimal's unscaled integer (a BigNum whose text is its digits; a
// bigint here), milliseconds since 1970 for DATE and TIMESTAMP, units since midnight for TIME.
// The e2e runs the same types through the engine (e2e/warehouse-console.spec.ts).
//
// Mutation checked by hand (restored): `String(value)` for every type, as the console did
// before, fails the decimal, date, timestamp and time cases.

const DECIMAL = 7;
const DATE = 8;
const TIME = 9;
const TIMESTAMP = 10;
const MICROSECOND = 2;

describe("cellText", () => {
  it("puts a decimal's point back at its scale", () => {
    expect(cellText(BigInt("15"), { typeId: DECIMAL, scale: 1 })).toBe("1.5");
    expect(cellText(BigInt("25"), { typeId: DECIMAL, scale: 2 })).toBe("0.25");
    expect(cellText(-BigInt("5"), { typeId: DECIMAL, scale: 2 })).toBe("-0.05");
    expect(cellText(BigInt("650"), { typeId: DECIMAL, scale: 1 })).toBe("65.0");
    expect(cellText(BigInt("12345678901234567890"), { typeId: DECIMAL, scale: 0 })).toBe("12345678901234567890");
  });

  it("writes a date as YYYY-MM-DD and a timestamp with its time, in UTC", () => {
    expect(cellText(982108800000, { typeId: DATE })).toBe("2001-02-14");
    expect(cellText(-86400000, { typeId: DATE })).toBe("1969-12-31");
    expect(cellText(1735787045000, { typeId: TIMESTAMP, unit: MICROSECOND })).toBe("2025-01-02 03:04:05");
    expect(cellText(1735787045123.5, { typeId: TIMESTAMP, unit: MICROSECOND })).toBe("2025-01-02 03:04:05.1235");
    expect(cellText(1735787045000, { typeId: TIMESTAMP, unit: MICROSECOND, timezone: "UTC" })).toBe(
      "2025-01-02 03:04:05Z",
    );
  });

  it("writes a time of day from its units since midnight", () => {
    expect(cellText(BigInt("11045500000"), { typeId: TIME, unit: MICROSECOND })).toBe("03:04:05.5");
  });

  it("keeps every digit of a BIGINT and writes NULL for a missing value", () => {
    expect(cellText(BigInt("9007199254740993"), { typeId: 2 })).toBe("9007199254740993");
    expect(cellText(null, { typeId: DECIMAL, scale: 2 })).toBe("NULL");
    expect(cellText("<b>x</b>", { typeId: 5 })).toBe("<b>x</b>");
  });
});
