import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/clock/Lesson";
import { lessonMetadata } from "../../../lib/learn/metadata";

// The query "Reproduce it" shows is the one `tracklab learn clock --check` runs on the raw files,
// read at build time from the pipeline: the page and the check cannot drift.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "clock.sql");

export const metadata = lessonMetadata("clock");

export default function ClockLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
