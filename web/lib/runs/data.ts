import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Runs } from "./types";

// The published `runs.json` (task 52), read at build time: /tracking/runs renders it first, and
// the home's findings (P20, task 175) quote it.
export function readRuns(): Runs {
  return JSON.parse(readFileSync(join(process.cwd(), "public", "data", "runs.json"), "utf-8")) as Runs;
}
