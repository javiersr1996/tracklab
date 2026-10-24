// Every outside source a lesson cites: where it was read, when, and the words it is quoted by.
// A lesson cites by id (`<Cite id>`), so a source has one place to be corrected.
export interface Source {
  label: string;
  url: string;
  read: string; // ISO date the original was read
  quote?: string;
}

export const SOURCES: Readonly<Record<string, Source>> = {};

export function sourceProblems(id: string, s: Source): string[] {
  const problems: string[] = [];
  if (s.label.trim() === "") problems.push(`${id}: no label`);
  if (!/^https:\/\/\S+$/.test(s.url)) problems.push(`${id}: url is not https`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s.read) || Number.isNaN(Date.parse(s.read))) problems.push(`${id}: read is not a date`);
  return problems;
}

export function source(id: string): Source {
  const s = SOURCES[id];
  if (!s) throw new Error(`unknown source "${id}"`);
  return s;
}
