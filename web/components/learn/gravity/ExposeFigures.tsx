"use client";

import { useEffect } from "react";
import { expose } from "../../../lib/learn/expose";
import type { GravityHook, MatchGravity } from "../../../lib/learn/gravity-data";
import type { HypothesesFile } from "../../../lib/learn/hypotheses-data";
import { hypothesesFigures } from "../../../lib/learn/hypotheses-figures";
import { lessonFigures } from "../../../lib/learn/lesson-figures";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn` (those of "What the data add" under `hyp`), so the e2e compares the printed
// text with a second computation.
export function ExposeFigures({ hook, matches, hypotheses }: { hook: GravityHook; matches: readonly MatchGravity[]; hypotheses: HypothesesFile }) {
  useEffect(() => {
    expose({ ...lessonFigures(hook, matches), hyp: hypothesesFigures(hypotheses) });
  }, [hook, matches, hypotheses]);
  return null;
}
