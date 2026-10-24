"use client";

import { useEffect } from "react";
import type { ClockExample, ClockFile } from "../../../lib/learn/clock-data";
import { clockFigures } from "../../../lib/learn/clock-figures";
import { expose } from "../../../lib/learn/expose";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ file, examples, g, G }: { file: ClockFile; examples: readonly ClockExample[]; g: number; G: number }) {
  useEffect(() => {
    expose(clockFigures(file, examples, g, G));
  }, [file, examples, g, G]);
  return null;
}
