"use client";

import { useEffect } from "react";
import { expose } from "../../../lib/learn/expose";
import type { GravityHook, MatchGravity } from "../../../lib/learn/gravity-data";
import { lessonFigures } from "../../../lib/learn/lesson-figures";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ hook, matches }: { hook: GravityHook; matches: readonly MatchGravity[] }) {
  useEffect(() => {
    expose(lessonFigures(hook, matches));
  }, [hook, matches]);
  return null;
}
