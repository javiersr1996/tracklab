import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/expected/Lesson";
import { lessonMetadata } from "../../../lib/learn/metadata";

// "Reproduce it" shows the query `tracklab euroleague publish --check` runs on the published
// expected-points.json, read at build time from the pipeline: the page and the check cannot drift.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "expected-points.sql");

export const metadata = lessonMetadata("expected-points");

export default function ExpectedPointsLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
