import { source } from "../../lib/learn/sources";

// Inline, a source goes by its short name; `full` gives its whole label, as in Further reading.
export function Cite({ id, full = false }: { id: string; full?: boolean }) {
  const s = source(id);
  return (
    <cite>
      <a href={s.url}>{full ? s.label : (s.short ?? s.label)}</a>
    </cite>
  );
}

// A source's own words as `sources.ts` holds them, code between backticks shown as code.
export function Quote({ id }: { id: string }) {
  const { quote } = source(id);
  if (!quote) throw new Error(`source "${id}" has no quote`);
  return <q>{quote.split("`").map((part, i) => (i % 2 === 1 ? <code key={i}>{part}</code> : part))}</q>;
}
