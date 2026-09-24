"use client";

import { useCallback, useEffect, useState } from "react";
import type { IndexEntry } from "../../lib/data";
import type { Possession } from "../../lib/replay/types";
import { Replay } from "./Replay";

// Plays the given possessions one after another, forever, starting on load.
export function Alternating({ entries }: { entries: IndexEntry[] }) {
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
    <Replay key={possession.possession_id} possession={possession} autoplay onEnded={next} />
  );
}
