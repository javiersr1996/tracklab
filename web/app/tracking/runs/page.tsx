import { readFileSync } from "node:fs";
import path from "node:path";
import type { Runs } from "../../../lib/runs/types";
import { RunsClient } from "./RunsClient";
import { sectionMetadata } from "../../../lib/page-metadata";

export const metadata = sectionMetadata("/tracking/runs");

export default function RunsPage() {
  const runs = JSON.parse(
    readFileSync(path.join(process.cwd(), "public", "data", "runs.json"), "utf-8"),
  ) as Runs;
  return <RunsClient initial={runs} />;
}
