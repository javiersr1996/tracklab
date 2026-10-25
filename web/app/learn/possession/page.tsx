import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/possession/Lesson";
import { lessonMetadata } from "../../../lib/learn/metadata";

// The queries "Reproduce it" shows are the ones `tracklab learn possession --check` runs on the raw
// files, read at build time from the pipeline: the page and the check cannot drift.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "possession.sql");

export const metadata = lessonMetadata("possession");

export default function PossessionLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
