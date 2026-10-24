import { display } from "./display";

// "Matches the figures above" (task 86): a query of "Run it here" returns rows of `figure` (the
// name of a `data-fig` the lesson prints) and `value`; a row matches when the page prints that
// figure and every place it does reads `display(value, figure)`, the way the e2e compares a figure
// with its source.
export interface Reproduced {
  figure: string;
  value: string;
  page: string[];
  matched: boolean;
}

export function reproduced(columns: readonly string[], rows: readonly string[][], printed: (figure: string) => string[]): Reproduced[] | null {
  const f = columns.indexOf("figure");
  const v = columns.indexOf("value");
  if (f < 0 || v < 0) return null;
  return rows.map((row) => {
    const page = printed(row[f]);
    return { figure: row[f], value: row[v], page, matched: page.length > 0 && page.every((text) => text === display(row[v], row[f])) };
  });
}
