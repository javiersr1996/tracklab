"use client";

import { useEffect, useState } from "react";
import { RunsView } from "../../../components/runs/RunsView";
import { PageHead } from "../../../components/site/Band";
import type { Runs } from "../../../lib/runs/types";

// The server renders the published `runs.json` (so the folded evidence is in the HTML); the
// browser then fetches the file again, like the possessions the replay pages play, and shows
// whatever it says: the e2e hands it a fixture for each branch. `data-loaded` waits for that fetch.
export function RunsClient({ initial }: { initial: Runs }) {
  const [runs, setRuns] = useState<Runs | "failed">(initial);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let live = true;
    fetch("/data/runs.json")
      .then((r) => r.json() as Promise<Runs>)
      .then((data) => {
        if (!live) return;
        setRuns(data);
        setLoaded(true);
      })
      .catch(() => {
        if (!live) return;
        setRuns("failed");
        setLoaded(true);
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <main className="page runs" data-loaded={loaded ? "true" : "false"}>
      {runs === "failed" ? (
        <PageHead eyebrow="Off-ball runs">
          <h1>The run that moves nobody</h1>
          <p role="alert">runs.json could not be loaded.</p>
        </PageHead>
      ) : (
        <RunsView runs={runs} />
      )}
    </main>
  );
}
