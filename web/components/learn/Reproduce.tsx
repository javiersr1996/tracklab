import type { ReactNode } from "react";
import { browserSql } from "../../lib/learn/browser-sql";
import { RunHere } from "./RunHere";

// "Reproduce it": the public query, shown as text, and the pointers that let a reader run it; then
// "Run it here" (tasks 85 and 86), the lesson's `<browser>.browser.sql` run in the browser on the
// files this page reads.
export function Reproduce({ sql, browser, children }: { sql: string; browser: string; children: ReactNode }) {
  return (
    <section className="reproduce" aria-labelledby="reproduce-h">
      <h2 id="reproduce-h">Reproduce it</h2>
      {children}
      <pre>
        <code>{sql}</code>
      </pre>
      <h3 id="run-here-h">Run it here</h3>
      <p>
        The same figures again, from the files this page already reads: the query below runs in this browser, in DuckDB
        compiled to WebAssembly, and each row names a figure of this lesson and the value it gives for it.
      </p>
      <RunHere {...browserSql(browser)} />
    </section>
  );
}
