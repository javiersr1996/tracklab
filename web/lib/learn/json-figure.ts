// The value a `data-fig` names in a lesson's own JSON (P9): the name is `<prefix>.` and a dotted
// path into the file, except that under `matches` the next part is a match id
// (`clock.matches.bb:114086.slope_median`). The e2e of each lesson resolves names the same way.
export function figureAt(data: unknown, prefix: string, path: string): unknown {
  const parts = path.split(".");
  if (parts[0] !== prefix) return undefined;
  let at: unknown = data;
  for (let i = 1; i < parts.length; i++) {
    if (Array.isArray(at) && parts[i - 1] === "matches") at = at.find((m: { match_id: string }) => m.match_id === parts[i]);
    else at = at !== null && typeof at === "object" ? (at as Record<string, unknown>)[parts[i]] : undefined;
  }
  return at;
}

// The `data-fig` name of a field of a match's row.
export const matchFig = (prefix: string, match_id: string, field: string): string => `${prefix}.matches.${match_id}.${field}`;
