"use client";

import { useCallback, useEffect, useState } from "react";
import { type IndexEntry, replayHref } from "../../lib/data";
import { usePrefersReducedMotion } from "../../lib/motion";
import type { Possession } from "../../lib/replay/types";
import { Replay, TRAIL_MS } from "./Replay";

// Plays the given possessions one after another, forever, starting on load. As the home's hero
// (P12) it fills its box with trails; under `prefers-reduced-motion` it shows the first frame,
// still and without trails, until the visible button is pressed. `onEntry` hears which
// possession is up, so the hero's link can follow it.
export function Alternating({
  entries,
  hero = false,
  onEntry,
}: {
  entries: IndexEntry[];
  hero?: boolean;
  onEntry?: (entry: IndexEntry) => void;
}) {
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

  useEffect(() => {
    onEntry?.(entries[k]);
  }, [entries, k, onEntry]);

  const next = useCallback(() => setK((i) => (i + 1) % entries.length), [entries.length]);

  if (!possession) return <div className="replay-placeholder" />;
  return (
    <Replay
      key={possession.possession_id}
      possession={possession}
      autoplay={!reduceMotion}
      onEnded={next}
      hero={hero}
      trailMs={hero && !reduceMotion ? TRAIL_MS : 0}
      href={hero ? replayHref(entries[k]) : undefined}
    />
  );
}
