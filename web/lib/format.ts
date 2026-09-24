// Small pure helper for English count copy (e.g. "1 player" / "12 players").
// Only handles the regular "+s" plural; pass `plural` explicitly for the rest.
export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
