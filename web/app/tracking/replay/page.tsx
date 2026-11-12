"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ReplayContext } from "../../../components/replay/Context";
import { Replay, TRAIL_MS } from "../../../components/replay/Replay";
import { Band, PageHead } from "../../../components/site/Band";
import { POSSESSIONS, SPORTS } from "../../../lib/data";
import { usePrefersReducedMotion } from "../../../lib/motion";
import type { Possession, Sport } from "../../../lib/replay/types";

const fileName = (file: string) => file.replace(/^possessions\//, "");

// `/tracking/replay?p=<file>`: a sport, a match and a possession from index.json.
function Picker() {
  const router = useRouter();
  const file = useSearchParams().get("p") ?? fileName(POSSESSIONS[0].file);
  const current = POSSESSIONS.find((p) => fileName(p.file) === file) ?? POSSESSIONS[0];
  const [possession, setPossession] = useState<Possession | null>(null);
  // Trails behind every mark, as on the home's hero, unless the reader asked for stillness.
  const reduceMotion = usePrefersReducedMotion();

  useEffect(() => {
    let live = true;
    fetch(`/data/${current.file}`)
      .then((r) => r.json() as Promise<Possession>)
      .then((p) => live && setPossession(p));
    return () => {
      live = false;
    };
  }, [current.file]);

  const choose = (p = current) => router.replace(`/tracking/replay?p=${fileName(p.file)}`);
  const inSport = POSSESSIONS.filter((p) => p.sport === current.sport);
  const matches = [...new Map(inSport.map((p) => [p.match_id, p])).values()];
  const inMatch = inSport.filter((p) => p.match_id === current.match_id);

  return (
    <>
      <div className="controls">
        <select
          aria-label="Sport"
          value={current.sport}
          onChange={(e) => choose(POSSESSIONS.find((p) => p.sport === (e.target.value as Sport)))}
        >
          {SPORTS.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select
          aria-label="Match"
          value={current.match_id}
          onChange={(e) => choose(inSport.find((p) => p.match_id === e.target.value))}
        >
          {matches.map((p) => (
            <option key={p.match_id} value={p.match_id}>
              {p.home} v {p.away}
            </option>
          ))}
        </select>
        <select
          aria-label="Possession"
          value={current.possession_id}
          onChange={(e) => choose(inMatch.find((p) => p.possession_id === e.target.value))}
        >
          {/* The index has no period or clock: the label is the order in the match and the
              length, the id stays the value. */}
          {inMatch.map((p, k) => (
            <option key={p.possession_id} value={p.possession_id} title={p.possession_id}>
              Possession {k + 1} of {inMatch.length}, {p.duration_s} s
            </option>
          ))}
        </select>
      </div>
      {/* The player and, beside it from 1000 px (under it on a phone), what is on show. */}
      <div className="replay-stage">
        {possession?.possession_id === current.possession_id ? (
          <>
            <Replay key={possession.possession_id} possession={possession} trailMs={reduceMotion ? 0 : TRAIL_MS} />
            <ReplayContext possession={possession} entry={current} />
          </>
        ) : (
          <div className="replay-placeholder" />
        )}
      </div>
    </>
  );
}

export default function ReplayPage() {
  return (
    <main id="main" className="page">
      <PageHead eyebrow="One renderer">
        <h1>Replay any possession</h1>
        <p className="lede" data-lede>
          Watch a real possession again from above: every player and the ball, where SkillCorner&apos;s
          open tracking data puts them, many times a second. Pick a sport, a match and a possession,
          then play it, scrub through it or slow it down.
        </p>
      </PageHead>
      <Band dark>
        <Suspense fallback={<div className="replay-placeholder" />}>
          <Picker />
        </Suspense>
      </Band>
    </main>
  );
}
