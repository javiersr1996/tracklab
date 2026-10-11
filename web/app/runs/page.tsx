"use client";

import { useEffect, useState } from "react";
import { RunsView } from "../../components/runs/RunsView";
import type { Runs } from "../../lib/runs/types";

// `runs.json` is fetched, like the possessions the replay pages play, so the page renders
// whatever the file says: the e2e hands it a fixture for each branch.
export default function RunsPage() {
  const [runs, setRuns] = useState<Runs | "failed" | null>(null);

  useEffect(() => {
    let live = true;
    fetch("/data/runs.json")
      .then((r) => r.json() as Promise<Runs>)
      .then((data) => live && setRuns(data))
      .catch(() => live && setRuns("failed"));
    return () => {
      live = false;
    };
  }, []);

  return (
    <main className="page runs" data-loaded={runs === null ? "false" : "true"}>
      {runs === null || runs === "failed" ? (
        <>
          <h1>The run that moves nobody</h1>
          {runs === "failed" ? <p role="alert">runs.json could not be loaded.</p> : null}
        </>
      ) : (
        <RunsView runs={runs} />
      )}
    </main>
  );
}
