import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/gravity/Lesson";

// The query "Reproduce it" shows is the one `tracklab learn gravity --check` runs (task 76), read
// at build time from the pipeline, one directory up from `web/`, like `docs/bulletin.md` on
// /bulletin: the page and the check cannot drift apart.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "gravity.sql");

export default function GravityLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
