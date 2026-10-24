import type { ReactNode } from "react";

// A display formula in native MathML (no library). globals.css pins every element inside to the
// formula's own size, because MathML shrinks subscripts and superscripts below the 16 px floor.
export function Formula({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="formula" role="group" aria-label={label}>
      <math display="block">{children}</math>
    </div>
  );
}
