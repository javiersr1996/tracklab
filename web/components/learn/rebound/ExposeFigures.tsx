"use client";

import { useEffect } from "react";
import { expose } from "../../../lib/learn/expose";
import type { ReboundFile } from "../../../lib/learn/rebound-data";
import { reboundFigures } from "../../../lib/learn/rebound-figures";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ file }: { file: ReboundFile }) {
  useEffect(() => {
    expose(reboundFigures(file));
  }, [file]);
  return null;
}
