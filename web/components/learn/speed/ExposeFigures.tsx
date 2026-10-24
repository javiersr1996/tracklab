"use client";

import { useEffect } from "react";
import { expose } from "../../../lib/learn/expose";
import type { SpeedExample, SpeedFile } from "../../../lib/learn/speed-data";
import { speedFigures } from "../../../lib/learn/speed-figures";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ example, file }: { example: SpeedExample; file: SpeedFile }) {
  useEffect(() => {
    expose(speedFigures(example, file));
  }, [example, file]);
  return null;
}
