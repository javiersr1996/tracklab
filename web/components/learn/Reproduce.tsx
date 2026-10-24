import type { ReactNode } from "react";

// "Reproduce it": the public query, shown as text, and the pointers that let a reader run it.
export function Reproduce({ sql, children }: { sql: string; children: ReactNode }) {
  return (
    <section className="reproduce" aria-labelledby="reproduce-h">
      <h2 id="reproduce-h">Reproduce it</h2>
      {children}
      <pre>
        <code>{sql}</code>
      </pre>
    </section>
  );
}
