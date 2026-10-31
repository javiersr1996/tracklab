import type { ReactNode } from "react";

// A full-width band with its content in the centred wrap: the page's near-black for prose and
// tables, the alternate band (a step lighter) for the canvases and viewers.
export function Band({ dark = false, className, children }: { dark?: boolean; className?: string; children: ReactNode }) {
  return (
    <div className={["band", dark && "surface-dark", className].filter(Boolean).join(" ")}>
      <div className="wrap">{children}</div>
    </div>
  );
}

// The head of an inner page: an eyebrow, then the page's own h1 and whatever follows it. With an
// `aside` (task 112), a neon panel beside the text from 1000 px and under it below.
export function PageHead({ eyebrow, aside, children }: { eyebrow: string; aside?: ReactNode; children: ReactNode }) {
  if (!aside) {
    return (
      <Band className="page-head">
        <p className="eyebrow">{eyebrow}</p>
        {children}
      </Band>
    );
  }
  return (
    <Band className="page-head">
      <div className="page-head-grid">
        <div className="page-head-text">
          <p className="eyebrow">{eyebrow}</p>
          {children}
        </div>
        {aside}
      </div>
    </Band>
  );
}
