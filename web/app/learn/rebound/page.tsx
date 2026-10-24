import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/rebound/Lesson";

// The query "Reproduce it" shows is the one `tracklab learn rebound --check` runs on the raw files,
// read at build time from the pipeline, like lessons 1 and 2: the page and the check cannot drift.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "rebound.sql");

export default function ReboundLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
