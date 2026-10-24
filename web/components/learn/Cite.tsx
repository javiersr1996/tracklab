import { source } from "../../lib/learn/sources";

export function Cite({ id }: { id: string }) {
  const s = source(id);
  return (
    <cite>
      <a href={s.url}>{s.label}</a>
    </cite>
  );
}
