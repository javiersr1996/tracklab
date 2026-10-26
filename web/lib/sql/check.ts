import { ROW_LIMIT } from "../duckdb/engine";
import { fingerprint, NotComparable } from "./normalize";

// The verdict of an exercise box (task 101): the reader's result against what `course.json`
// says of the reference (`tracklab sql course`). Shape first, in the order the reader can act on
// it (too many rows for the engine to keep, then columns, then rows), and only when the shape
// matches is the result normalized and hashed. The expected rows are never shown: the reader
// gets "Correct", the first shape difference, "Same shape, different values", or the reason the
// result cannot be compared.

export type Verdict = "correct" | "columns" | "rows" | "values" | "over_limit" | "uncomparable";

// What the checker needs of an exercise, as `course.json` carries it.
export interface ExerciseMeta {
  ordered: boolean;
  columns: number;
  rows: number;
  sha256: string;
}

// The shape of the reader's result: the columns of its schema and the full row count (the
// engine keeps `ROW_LIMIT` rows but counts them all).
export interface Shape {
  columns: number;
  rowCount: number;
}

// The shape's verdict alone, or null when the shape matches and the values decide.
export function shapeVerdict(meta: ExerciseMeta, shape: Shape): Verdict | null {
  if (shape.rowCount > ROW_LIMIT) return "over_limit";
  if (shape.columns !== meta.columns) return "columns";
  if (shape.rowCount !== meta.rows) return "rows";
  return null;
}

// `texts` are the rows of the wrapped query (`wrap` in normalize.ts), one JSON array each.
export async function check(meta: ExerciseMeta, shape: Shape, texts: string[]): Promise<Verdict> {
  const early = shapeVerdict(meta, shape);
  if (early) return early;
  try {
    const { sha256 } = await fingerprint(texts, meta.ordered);
    return sha256 === meta.sha256 ? "correct" : "values";
  } catch (error) {
    if (error instanceof NotComparable) return "uncomparable";
    throw error;
  }
}

const count = (n: number, noun: string) => `${n.toLocaleString("en-US")} ${noun}${n === 1 ? "" : "s"}`;

export function verdictText(verdict: Verdict, meta: ExerciseMeta, shape: Shape): string {
  switch (verdict) {
    case "correct":
      return "Correct";
    case "columns":
      return `${count(meta.columns, "column")} expected, you have ${shape.columns.toLocaleString("en-US")}`;
    case "rows":
      return `${count(meta.rows, "row")} expected, you have ${shape.rowCount.toLocaleString("en-US")}`;
    case "values":
      return "Same shape, different values";
    case "over_limit":
      return `More than ${ROW_LIMIT.toLocaleString("en-US")} rows; ${meta.rows.toLocaleString("en-US")} expected`;
    case "uncomparable":
      return "Your result has values the checker cannot compare (NaN, Infinity or very large numbers)";
  }
}
