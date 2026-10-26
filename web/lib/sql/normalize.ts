// The fingerprint of a query's result: the one rule Python and the browser both implement, ported
// line by line from `pipeline/src/tracklab/sqlcourse/normalize.py` (the spec's "Normalization",
// docs/superpowers/specs/2026-10-26-sql-course-design.md). DuckDB types the values itself: the
// query runs inside `wrap`, whose one column is each row as JSON text. Each number becomes the
// integer `sign(x) * floor(|x| * 10000 + 0.5)` in IEEE doubles (`-0` is `0`); strings, null and
// booleans stay as JSON gives them; a list or a struct is normalized inside. Unordered rows are
// sorted by the UTF-8 bytes of their canonical JSON (the encoded bytes, not UTF-16 units), and the
// hash is the SHA-256 of the canonical JSON of all rows. `NaN`, `Infinity` and numbers with
// `|x| * 10000` at or above 2^53 cannot be compared: `NotComparable`.
//
// `tests/fixtures/sql-normalize.json` pins the rule from wrapper text to hash; pytest and vitest
// both read it, so a change here that Python does not make fails a test.

export const SCALE = 10000;
export const LIMIT = 2 ** 53;

export class NotComparable extends Error {}

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

// The wrapper of the spec around a query, its trailing `;` stripped. The newlines keep a trailing
// line comment of the query from swallowing the closing parenthesis.
export function wrap(query: string): string {
  const body = query.trim().replace(/;+$/, "").trimEnd();
  return `SELECT json_array(*COLUMNS(*))::VARCHAR FROM (\n${body}\n) q`;
}

export function number(x: number): number {
  if (!Number.isFinite(x) || Math.abs(x) * SCALE >= LIMIT) throw new NotComparable(String(x));
  const n = Math.floor(Math.abs(x) * SCALE + 0.5);
  return x < 0 && n !== 0 ? -n : n;
}

export function value(v: Json): Json {
  if (v === null || typeof v === "boolean" || typeof v === "string") return v;
  if (typeof v === "number") return number(v);
  if (Array.isArray(v)) return v.map(value);
  return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, value(x)]));
}

// `json.dumps(rows, ensure_ascii=False, separators=(",", ":"))`: both escape the quote, the
// backslash and the control characters the same way, and nothing else.
export const canonical = (rows: Json): string => JSON.stringify(rows);

// One row of the wrapper. JSON.parse refuses `NaN` and `Infinity` (Python's json reads them and
// `number` refuses them): either way the row cannot be compared.
export function parseRow(text: string): Json[] {
  let row: Json;
  try {
    row = JSON.parse(text);
  } catch {
    throw new NotComparable(text);
  }
  if (!Array.isArray(row)) throw new TypeError(`a wrapper row is a JSON array, not ${JSON.stringify(text)}`);
  return row;
}

const encoder = new TextEncoder();

function compareBytes(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) if (a[i] !== b[i]) return a[i] - b[i];
  return a.length - b.length;
}

export function normalize(texts: string[], ordered: boolean): Json[][] {
  const rows = texts.map((t) => value(parseRow(t)) as Json[]);
  if (ordered) return rows;
  return rows
    .map((row) => ({ row, key: encoder.encode(canonical(row)) }))
    .sort((a, b) => compareBytes(a.key, b.key))
    .map((x) => x.row);
}

// The canonical JSON of the normalized rows and its SHA-256, hex.
export async function fingerprint(texts: string[], ordered: boolean): Promise<{ canonical: string; sha256: string }> {
  const text = canonical(normalize(texts, ordered));
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(text));
  const sha256 = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  return { canonical: text, sha256 };
}
