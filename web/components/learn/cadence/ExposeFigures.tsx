"use client";

import { useEffect } from "react";
import type { HookWindow, PlayerRow } from "../../../lib/learn/cadence-data";
import { cadenceFigures } from "../../../lib/learn/cadence-figures";
import { expose } from "../../../lib/learn/expose";

// The figures the text quotes as `data-fig="learn.<key>"`, computed again in the browser and put
// in `window.__learn`, so the e2e compares the printed text with a second computation.
export function ExposeFigures({ hooks, fast }: { hooks: readonly HookWindow[]; fast: Readonly<Record<string, readonly PlayerRow[]>> }) {
  useEffect(() => {
    expose(cadenceFigures(hooks, fast));
  }, [hooks, fast]);
  return null;
}
