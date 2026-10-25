import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/dribble/Lesson";
import { lessonMetadata } from "../../../lib/learn/metadata";

// The query "Reproduce it" shows is the one `tracklab learn dribble --check` runs on the raw files,
// read at build time from the pipeline: the page and the check cannot drift.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "dribble.sql");

export const metadata = lessonMetadata("dribble");

export default function DribbleLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
