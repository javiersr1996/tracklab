"use client";

import { useEffect } from "react";
import type { Sample } from "../../../lib/learn/entry";
import type { EntryFile, EntryMatch } from "../../../lib/learn/entry-data";
import { entryFigures } from "../../../lib/learn/entry-figures";
import { expose } from "../../../lib/learn/expose";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ file, run, matches, hookG }: { file: EntryFile; run: readonly Sample[]; matches: readonly EntryMatch[]; hookG: number }) {
  useEffect(() => {
    expose(entryFigures(file, run, matches, hookG));
  }, [file, run, matches, hookG]);
  return null;
}
