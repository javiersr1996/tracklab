"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Replay } from "../../../components/replay/Replay";
import { Band, PageHead } from "../../../components/site/Band";
import { POSSESSIONS, SPORTS } from "../../../lib/data";
import type { Possession, Sport } from "../../../lib/replay/types";

const fileName = (file: string) => file.replace(/^possessions\//, "");

// `/tracking/replay?p=<file>`: a sport, a match and a possession from index.json.
function Picker() {
  const router = useRouter();
  const file = useSearchParams().get("p") ?? fileName(POSSESSIONS[0].file);
  const current = POSSESSIONS.find((p) => fileName(p.file) === file) ?? POSSESSIONS[0];
  const [possession, setPossession] = useState<Possession | null>(null);

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
          {inMatch.map((p) => (
            <option key={p.possession_id} value={p.possession_id}>
              {p.possession_id} ({p.duration_s} s)
            </option>
          ))}
        </select>
      </div>
      {possession?.possession_id === current.possession_id ? (
        <Replay key={possession.possession_id} possession={possession} />
      ) : (
        <div className="replay-placeholder" />
      )}
    </>
  );
}

export default function ReplayPage() {
  return (
    <main className="page">
      <PageHead eyebrow="One renderer">
        <h1>Replay any possession</h1>
      </PageHead>
      <Band dark>
        <Suspense fallback={<div className="replay-placeholder" />}>
          <Picker />
        </Suspense>
      </Band>
    </main>
  );
}
