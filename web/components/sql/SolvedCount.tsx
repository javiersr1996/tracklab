"use client";

import { useSolved } from "../../lib/sql/progress";

// "n of m solved" on the index of /sql, from the reader's progress in this browser.
export function SolvedCount({ ids }: { ids: string[] }) {
  const solved = useSolved();
  const n = ids.filter((id) => solved.includes(id)).length;
  return (
    <span className="sql-progress" data-solved={n} data-exercises={ids.length}>
      {n} of {ids.length} solved
    </span>
  );
}
