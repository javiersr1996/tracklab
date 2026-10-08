// How a value of a query result is shown: the one place that turns what Arrow hands back into
// text. Arrow's `get()` returns a DECIMAL as its unscaled integer (1.5 comes back as 15), a DATE
// or TIMESTAMP as milliseconds since 1970 and a TIME as units since midnight, so each is written
// out from the column's type. BIGINT arrives as a `bigint` and HUGEINT as a scale-0 decimal:
// both print every digit. Nested values (LIST, STRUCT, MAP, UNION) are written element by element
// with this same code (`columnCell`). An INTERVAL cannot go by `get()`: DuckDB sends months, days
// and nanoseconds and arrow 17 reads one 32-bit number, so it is read from the column's buffer.

import { type Data, type FixedSizeList, type Struct, type Union, UnionMode, Vector } from "apache-arrow";

// Arrow's type ids (`Type` in Schema.fbs) and time units (`TimeUnit`), as the column type
// carries them.
const DECIMAL = 7;
const DATE = 8;
const TIME = 9;
const TIMESTAMP = 10;
const INTERVAL = 11;
const LIST = 12;
const STRUCT = 13;
const UNION = 14;
const FIXED_SIZE_LIST = 16;
const MAP = 17;
const UNITS_PER_SECOND = [1, 1_000, 1_000_000, 1_000_000_000];

export interface CellType {
  typeId: number;
  scale?: number;
  unit?: number;
  timezone?: string | null;
}

const pad = (n: number, width: number) => String(n).padStart(width, "0");

// The unscaled integer of a decimal with its point put back: "-5" at scale 2 is "-0.05".
function decimal(value: unknown, scale: number): string {
  const digits = String(value);
  if (scale === 0) return digits;
  const negative = digits.startsWith("-");
  const abs = (negative ? digits.slice(1) : digits).padStart(scale + 1, "0");
  return `${negative ? "-" : ""}${abs.slice(0, -scale)}.${abs.slice(-scale)}`;
}

// Fractional seconds as DuckDB prints them: up to microseconds, trailing zeros dropped.
const fraction = (micros: number) => (micros === 0 ? "" : `.${pad(micros, 6).replace(/0+$/, "")}`);

// Milliseconds since 1970 (Arrow's DATE and TIMESTAMP, with a fraction below the millisecond for
// microsecond timestamps) as `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS[.ffffff]`, in UTC.
function instant(ms: number, withTime: boolean, timezone: string | null | undefined): string | null {
  // Microseconds below the millisecond; rounding can carry one into the next millisecond.
  const below = Math.round((ms - Math.floor(ms)) * 1000);
  const whole = Math.floor(ms) + (below === 1000 ? 1 : 0);
  const date = new Date(whole);
  if (Number.isNaN(date.getTime())) return null;
  const iso = date.toISOString();
  if (!withTime) return iso.slice(0, 10);
  const micros = date.getUTCMilliseconds() * 1000 + (below % 1000);
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)}${fraction(micros)}${timezone ? "Z" : ""}`;
}

// Units since midnight: a day has fewer than 2^53 nanoseconds, so a number holds any of them.
function time(value: unknown, unit: number): string {
  const perSecond = UNITS_PER_SECOND[unit] ?? 1;
  const units = Number(value);
  const seconds = Math.floor(units / perSecond);
  const micros = Math.floor(((units % perSecond) * 1_000_000) / perSecond);
  return `${pad(Math.floor(seconds / 3600), 2)}:${pad(Math.floor(seconds / 60) % 60, 2)}:${pad(seconds % 60, 2)}${fraction(micros)}`;
}

const ZERO = BigInt(0);
const THOUSAND = BigInt(1000);
const MILLION = BigInt(1_000_000);
const WORD = BigInt(32);

// DuckDB's text for an INTERVAL: `1 year 2 months 3 days 04:05:06.5`, each part only when not zero.
function interval(months: number, days: number, nanos: bigint): string {
  const parts: string[] = [];
  const unit = (n: number, name: string) => parts.push(`${n} ${name}${Math.abs(n) === 1 ? "" : "s"}`);
  const years = Math.trunc(months / 12);
  if (years) unit(years, "year");
  if (months % 12) unit(months % 12, "month");
  if (days) unit(days, "day");
  if (nanos !== ZERO) {
    const micros = nanos / THOUSAND;
    const abs = micros < ZERO ? -micros : micros;
    const seconds = Number(abs / MILLION);
    const clock = `${pad(Math.floor(seconds / 3600), 2)}:${pad(Math.floor(seconds / 60) % 60, 2)}:${pad(seconds % 60, 2)}`;
    parts.push(`${micros < ZERO ? "-" : ""}${clock}${fraction(Number(abs % MILLION))}`);
  }
  return parts.length ? parts.join(" ") : "00:00:00";
}

// The text of a scalar, from the value `get()` gave and the column's type.
export function cellText(value: unknown, type: CellType): string {
  if (value === null || value === undefined) return "NULL";
  switch (type.typeId) {
    case DECIMAL:
      return decimal(value, type.scale ?? 0);
    case DATE:
      return instant(Number(value), false, null) ?? String(value);
    case TIMESTAMP:
      return instant(Number(value), true, type.timezone) ?? String(value);
    case TIME:
      return time(value, type.unit ?? 0);
    default:
      return String(value);
  }
}

// One value of one chunk of a column, found by its type: a scalar by `cellText`, an INTERVAL from
// the raw buffer (four 32-bit words per value: months, days, nanoseconds as two), and every
// element of a LIST, STRUCT, MAP or UNION through the child chunks, so each is written like a
// column of its own. Chunks and their children start at offset 0 as they come off the wire.
function chunkCell(d: Data, i: number): string {
  const { type } = d;
  if (!new Vector([d]).isValid(i)) return "NULL";
  const range = (): [number, number] =>
    type.typeId === FIXED_SIZE_LIST
      ? [i * (type as FixedSizeList).listSize, (i + 1) * (type as FixedSizeList).listSize]
      : [d.valueOffsets[i], d.valueOffsets[i + 1]];
  switch (type.typeId) {
    case INTERVAL: {
      const w = d.values as Int32Array;
      const k = i * 4;
      return interval(w[k], w[k + 1], (BigInt(w[k + 3]) << WORD) | BigInt(w[k + 2] >>> 0));
    }
    case LIST:
    case FIXED_SIZE_LIST: {
      const [from, to] = range();
      return `[${Array.from({ length: to - from }, (_, j) => chunkCell(d.children[0], from + j)).join(", ")}]`;
    }
    case MAP: {
      const [from, to] = range();
      const [keys, values] = d.children[0].children;
      return `{${Array.from({ length: to - from }, (_, j) => `${chunkCell(keys, from + j)}=${chunkCell(values, from + j)}`).join(", ")}}`;
    }
    case STRUCT: {
      const fields = d.children.map((child, k) => `'${(type as Struct).children[k].name}': ${chunkCell(child, i)}`);
      return `{${fields.join(", ")}}`;
    }
    case UNION: {
      const union = type as Union;
      const child = d.children[union.typeIdToChildIndex[d.typeIds[i]]];
      return chunkCell(child, union.mode === UnionMode.Dense ? d.valueOffsets[i] : i);
    }
    default:
      return cellText(new Vector([d]).get(i), type);
  }
}

// The value at row `index` of a column (arrow's `Vector`, possibly in several chunks).
export function columnCell(column: Vector, index: number): string {
  let i = index;
  for (const d of column.data) {
    if (i < d.length) return chunkCell(d, i);
    i -= d.length;
  }
  return "NULL";
}
