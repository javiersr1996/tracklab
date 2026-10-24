import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/pass/Lesson";

// The query "Reproduce it" shows is the one `tracklab learn pass --check` runs on the raw files,
// read at build time from the pipeline: the page and the check cannot drift.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "pass.sql");

export default function PassLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
