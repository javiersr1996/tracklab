import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { tableFromArrays, tableFromIPC } from "apache-arrow";
import { cellText, columnCell, columnValue } from "../lib/warehouse/cell";

// How /warehouse writes a result value (`lib/warehouse/cell.ts`), fed what Arrow's `get()`
// returns for each type: a decimal's unscaled integer (a BigNum whose text is its digits; a
// bigint here), milliseconds since 1970 for DATE and TIMESTAMP, units since midnight for TIME.
// The e2e runs the same types through the engine (e2e/warehouse-console.spec.ts).
//
// Mutation checked by hand (restored): `String(value)` for every type, as the console did
// before, fails the decimal, date, timestamp and time cases.
//
// fixtures/nested.arrow is what DuckDB 1.5 hands over for INTERVAL, LIST, STRUCT, MAP and UNION
// (written by its Python client: `duckdb.sql(q).arrow()` to an IPC stream; q below). The expected
// text is what DuckDB itself prints for the same values (`CAST(x AS VARCHAR)`).
// q: SELECT i, age(DATE '2025-01-01', DATE '2001-02-14') AS aged, INTERVAL '-1 day 02:03:04.5' AS neg,
//   [DATE '2001-02-14', DATE '1990-05-06'] AS births, [1.5, 2.5] AS dec_list,
//   {'name': 'Jay Barnett', 'born': DATE '2001-02-14'} AS person, MAP {'k': 1.5} AS dec_map,
//   union_value(k := 1.5) AS u, ['a', NULL] AS strs, [INTERVAL 1 DAY, INTERVAL 14 MONTH] AS ivs,
//   {'span': INTERVAL 3 HOUR} AS st_iv
//   FROM (VALUES (INTERVAL 1 DAY), (INTERVAL 2 MONTH), (INTERVAL 3 HOUR), (CAST(NULL AS INTERVAL))) t(i)

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

describe("columnCell on what DuckDB sends", () => {
  const table = tableFromIPC(readFileSync(new URL("./fixtures/nested.arrow", import.meta.url)));
  const column = (name: string, row: number) => columnCell(table.getChild(name)!, row);

  it("writes an INTERVAL per row, not the first word of its buffer", () => {
    expect([0, 1, 2, 3].map((r) => column("i", r))).toEqual(["1 day", "2 months", "03:00:00", "NULL"]);
    expect(column("aged", 0)).toBe("23 years 10 months 15 days");
    expect(column("neg", 0)).toBe("-1 day 02:03:04.5");
  });

  it("writes the elements of a LIST by their own type", () => {
    expect(column("births", 0)).toBe("[2001-02-14, 1990-05-06]");
    expect(column("dec_list", 0)).toBe("[1.5, 2.5]");
    expect(column("strs", 0)).toBe("[a, NULL]");
    expect(column("ivs", 0)).toBe("[1 day, 1 year 2 months]");
  });

  it("writes STRUCT, MAP and UNION members by their own type", () => {
    expect(column("person", 0)).toBe("{'name': Jay Barnett, 'born': 2001-02-14}");
    expect(column("dec_map", 0)).toBe("{k=1.5}");
    expect(column("u", 0)).toBe("1.5");
    expect(column("st_iv", 0)).toBe("{'span': 03:00:00}");
  });
});

describe("columnValue", () => {
  const table = tableFromArrays({
    n: [1.5, null],
    i: new BigInt64Array([BigInt(2) ** BigInt(60), BigInt(7)]),
    s: ["a", null],
    b: [true, false],
  });
  const col = (name: "n" | "i" | "s" | "b") => table.getChild(name)!;

  it("gives numbers, strings and booleans as themselves and NULL as null", () => {
    expect(columnValue(col("n"), 0)).toBe(1.5);
    expect(columnValue(col("n"), 1)).toBeNull();
    expect(columnValue(col("s"), 0)).toBe("a");
    expect(columnValue(col("s"), 1)).toBeNull();
    expect(columnValue(col("b"), 1)).toBe(false);
  });

  it("gives a BIGINT as a number when it is safe and as its digits when it is not", () => {
    expect(columnValue(col("i"), 1)).toBe(7);
    expect(columnValue(col("i"), 0)).toBe(String(BigInt(2) ** BigInt(60)));
  });

  it("gives what is not a plain value (a date) as the text the table shows", () => {
    const dates = tableFromArrays({ d: [new Date(Date.UTC(2001, 1, 14))] }).getChild("d")!;
    expect(columnValue(dates, 0)).toBe(columnCell(dates, 0));
    expect(typeof columnValue(dates, 0)).toBe("string");
  });
});
