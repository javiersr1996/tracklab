import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/entry/Lesson";

// "Reproduce it" shows the script `tracklab learn entry --check` runs on the raw files of every
// match against quality.json, read at build time from the pipeline: they cannot drift apart.
const SCRIPT_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "entry.py");

export default function EntryLesson() {
  return <Lesson script={readFileSync(SCRIPT_PATH, "utf-8")} />;
}
