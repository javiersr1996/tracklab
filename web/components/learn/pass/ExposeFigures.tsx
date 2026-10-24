"use client";

import { useEffect } from "react";
import { expose } from "../../../lib/learn/expose";
import type { PassExample, PassFile } from "../../../lib/learn/pass-data";
import { lessonPassFigures } from "../../../lib/learn/pass-figures";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ file, examples }: { file: PassFile; examples: readonly PassExample[] }) {
  useEffect(() => {
    expose(lessonPassFigures(file, examples));
  }, [file, examples]);
  return null;
}
