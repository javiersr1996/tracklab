import { readRuns } from "../../../lib/runs/data";
import { RunsClient } from "./RunsClient";
import { sectionMetadata } from "../../../lib/page-metadata";

export const metadata = sectionMetadata("/tracking/runs");

export default function RunsPage() {
  return <RunsClient initial={readRuns()} />;
}
