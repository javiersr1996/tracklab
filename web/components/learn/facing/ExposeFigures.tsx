"use client";

import { useEffect } from "react";
import { expose } from "../../../lib/learn/expose";
import type { ClipFacing } from "../../../lib/learn/facing-data";
import { facingFigures } from "../../../lib/learn/facing-figures";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser from the
// hook players' angles and the players' rows, and put in `window.__learn`, so the e2e compares
// the printed text with a second computation.
export function ExposeFigures({ clips }: { clips: readonly ClipFacing[] }) {
  useEffect(() => {
    expose(facingFigures(clips));
  }, [clips]);
  return null;
}
