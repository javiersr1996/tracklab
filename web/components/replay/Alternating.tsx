"use client";

import { useCallback, useEffect, useState } from "react";
import type { IndexEntry } from "../../lib/data";
import { usePrefersReducedMotion } from "../../lib/motion";
import type { Possession } from "../../lib/replay/types";
import { Replay } from "./Replay";

// How far behind each player and the ball the hero's trail reaches.
const HERO_TRAIL_MS = 1400;

// Plays the given possessions one after another, forever, starting on load. As the home's hero
// (P12) it fills its box with trails; under `prefers-reduced-motion` it shows the first frame,
// still and without trails, until the visible button is pressed.
export function Alternating({ entries, hero = false }: { entries: IndexEntry[]; hero?: boolean }) {
  const reduceMotion = usePrefersReducedMotion();
  const [k, setK] = useState(0);
  const [possession, setPossession] = useState<Possession | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`/data/${entries[k].file}`)
      .then((r) => r.json() as Promise<Possession>)
      .then((p) => live && setPossession(p));
    return () => {
      live = false;
    };
  }, [entries, k]);

  const next = useCallback(() => setK((i) => (i + 1) % entries.length), [entries.length]);

  if (!possession) return <div className="replay-placeholder" />;
  return (
    <Replay
      key={possession.possession_id}
      possession={possession}
      autoplay={!reduceMotion}
      onEnded={next}
      hero={hero}
      trailMs={hero && !reduceMotion ? HERO_TRAIL_MS : 0}
    />
  );
}
