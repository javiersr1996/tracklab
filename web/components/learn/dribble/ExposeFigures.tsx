"use client";

import { useEffect } from "react";
import type { DribbleFile, TouchExample } from "../../../lib/learn/dribble-data";
import { lessonDribbleFigures } from "../../../lib/learn/dribble-figures";
import { expose } from "../../../lib/learn/expose";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ file, example }: { file: DribbleFile; example: TouchExample }) {
  useEffect(() => {
    expose(lessonDribbleFigures(file, example));
  }, [file, example]);
  return null;
}
