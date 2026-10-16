import type { ReactNode } from "react";

// A full-width band with its content in the centred wrap: light for prose and tables, dark for
// the canvases and viewers.
export function Band({ dark = false, className, children }: { dark?: boolean; className?: string; children: ReactNode }) {
  return (
    <div className={["band", dark && "surface-dark", className].filter(Boolean).join(" ")}>
      <div className="wrap">{children}</div>
    </div>
  );
}

// The head of an inner page: an eyebrow, then the page's own h1 and whatever follows it.
export function PageHead({ eyebrow, children }: { eyebrow: string; children: ReactNode }) {
  return (
    <Band className="page-head">
      <p className="eyebrow">{eyebrow}</p>
      {children}
    </Band>
  );
}
