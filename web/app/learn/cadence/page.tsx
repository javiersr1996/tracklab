import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/cadence/Lesson";
import { lessonMetadata } from "../../../lib/learn/metadata";

// "Reproduce it" shows the script `tests/unit/test_learn_cadence.py` runs against the pipeline,
// read at build time one directory up from `web/`, like lesson 1's SQL: they cannot drift apart.
const SCRIPT_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "cadence.py");

export const metadata = lessonMetadata("cadence");

export default function CadenceLesson() {
  return <Lesson script={readFileSync(SCRIPT_PATH, "utf-8")} />;
}
