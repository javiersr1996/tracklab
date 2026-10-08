import type { Metadata } from "next";
import { Probe } from "./Probe";

// Task 38: a throwaway route, deleted when the task closes. Linked from nowhere and
// kept out of search indexes; e2e/warehouse-probe.spec.ts drives it and writes what it
// measured to pipeline/reports/warehouse_probe.json.
export const metadata: Metadata = {
  title: "DuckDB-WASM probe",
  robots: { index: false, follow: false },
};

export default function ProbePage() {
  return (
    <main className="page">
      <h1>DuckDB-WASM probe</h1>
      <p>
        Three fixed queries over two layouts of the picks table, and one over three layouts of
        the long fact. Nothing runs until a button is pressed.
      </p>
      <Probe />
    </main>
  );
}
