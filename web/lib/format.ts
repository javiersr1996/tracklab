// Small pure helper for English count copy (e.g. "1 player" / "12 players").
// Only handles the regular "+s" plural; pass `plural` explicitly for the rest.
export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

// Mirrors `pipeline/src/tracklab/publish/format.py::fmt` (task 34) case for
// case, so the title `tracklab publish platform` prints and this function's
// own output never diverge: base 10 (1000), one decimal past bytes,
// B/KB/MB/GB/TB.
const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

export function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  let value = n;
  let unit = 0;
  while (value >= 1000 && unit < BYTE_UNITS.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value.toFixed(1)} ${BYTE_UNITS[unit]}`;
}
