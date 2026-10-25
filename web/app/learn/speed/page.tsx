import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/speed/Lesson";
import { lessonMetadata } from "../../../lib/learn/metadata";

// The query "Reproduce it" shows is the one `tracklab learn speed --check` runs on the raw files,
// read at build time from the pipeline, like lesson 1's: the page and the check cannot drift apart.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "speed.sql");

export const metadata = lessonMetadata("speed");

export default function SpeedLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
