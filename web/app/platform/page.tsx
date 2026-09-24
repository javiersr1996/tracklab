import { Flow } from "../../components/platform/Flow";
import { PLATFORM } from "../../lib/platform";

export default function PlatformPage() {
  const { run } = PLATFORM;
  return (
    <main className="page">
      <h1>{PLATFORM.title}</h1>
      <p>
        One pipeline run, five layers: raw, bronze, silver, quality, publish. Each layer&apos;s
        counters are the figures <code>tracklab build</code> and <code>tracklab publish
        platform</code> measured on this run, read from{" "}
        <a href="/data/platform.json">platform.json</a>, never typed by hand.
      </p>
      <Flow layers={PLATFORM.layers} />
      <footer className="platform-footer">
        <p>
          Run {run.git_sha} on {run.started_utc.slice(0, 10)}, {run.host.system},{" "}
          {run.host.cpus} CPUs, {run.host.ram_gb} GB RAM, wall clock {run.wall_seconds}s: one run
          on one machine; steps ran in parallel, so per-step seconds do not add up to the wall
          clock.
        </p>
      </footer>
    </main>
  );
}
