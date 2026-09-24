"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Replay } from "../../components/replay/Replay";
import type { Possession } from "../../lib/replay/types";

// `/replay?p=<file>` plays one published possession; task 22 adds the selector.
function ReplayFromQuery() {
  const file = useSearchParams().get("p");
  const [possession, setPossession] = useState<Possession | null>(null);

  useEffect(() => {
    if (!file) return;
    fetch(`/data/possessions/${encodeURIComponent(file)}`)
      .then((r) => r.json() as Promise<Possession>)
      .then(setPossession);
  }, [file]);

  if (!file) return <p>No possession selected.</p>;
  if (!possession) return <p>Loading…</p>;
  return <Replay key={possession.possession_id} possession={possession} />;
}

export default function ReplayPage() {
  return (
    <main>
      <Suspense>
        <ReplayFromQuery />
      </Suspense>
    </main>
  );
}
