// How a value of a query result is shown: the one place that turns what Arrow hands back into
// text. Arrow's `get()` returns a DECIMAL as its unscaled integer (1.5 comes back as 15), a DATE
// or TIMESTAMP as milliseconds since 1970 and a TIME as units since midnight, so each is written
// out from the column's type. BIGINT arrives as a `bigint` and HUGEINT as a scale-0 decimal:
// both print every digit.

// Arrow's type ids (`Type` in Schema.fbs) and time units (`TimeUnit`), as the column type
// carries them.
const DECIMAL = 7;
const DATE = 8;
const TIME = 9;
const TIMESTAMP = 10;
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
