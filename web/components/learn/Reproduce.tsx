import type { ReactNode } from "react";

// "Reproduce it": the public query, shown as text, and the pointers that let a reader run it; then,
// when the lesson has one, "Run it here" (task 85), the same figures from the files this page reads.
export function Reproduce({ sql, children, run }: { sql: string; children: ReactNode; run?: ReactNode }) {
  return (
    <section className="reproduce" aria-labelledby="reproduce-h">
      <h2 id="reproduce-h">Reproduce it</h2>
      {children}
      <pre>
        <code>{sql}</code>
      </pre>
      {run ? (
        <>
          <h3 id="run-here-h">Run it here</h3>
          {run}
        </>
      ) : null}
    </section>
  );
}
