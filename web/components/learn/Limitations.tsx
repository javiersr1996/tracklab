import type { ReactNode } from "react";

export function Limitations({ children }: { children: ReactNode }) {
  return (
    <section className="limitations" aria-labelledby="limitations-h">
      <h2 id="limitations-h">Limitations</h2>
      {children}
    </section>
  );
}
