import type { ReactNode } from "react";

// A full-width band with its content in the centred wrap: light for prose and tables, dark for
// the canvases and viewers.
export function Band({ dark = false, className, children }: { dark?: boolean; className?: string; children: ReactNode }) {
  return (
    <div className={["band", dark ? "surface-dark" : "", className ?? ""].join(" ").trim()}>
      <div className="wrap">{children}</div>
    </div>
  );
}
