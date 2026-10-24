"use client";

import { useEffect } from "react";
import { expose } from "../../../lib/learn/expose";
import type { CoordinatesFigures } from "../../../lib/learn/coordinates-data";

// The figures the text quotes as `data-fig="learn.<key>"`, put in `window.__learn` so the e2e
// compares the printed text with them. They are computed at build time from published files only
// (passing the files here would ship every possession to the browser).
export function ExposeFigures({ figures }: { figures: CoordinatesFigures }) {
  useEffect(() => {
    expose(figures);
  }, [figures]);
  return null;
}
