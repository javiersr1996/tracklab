"use client";

import { useEffect } from "react";
import type { ExpectedFile } from "../../../lib/learn/expected-data";
import { lessonExpectedFigures } from "../../../lib/learn/expected-figures";
import { expose } from "../../../lib/learn/expose";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser from
// expected-points.json and put in `window.__learn`, so the e2e compares the printed text with them.
export function ExposeFigures({ file }: { file: ExpectedFile }) {
  useEffect(() => {
    expose(lessonExpectedFigures(file));
  }, [file]);
  return null;
}
