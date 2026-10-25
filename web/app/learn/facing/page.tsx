import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/facing/Lesson";
import { lessonMetadata } from "../../../lib/learn/metadata";

// "Reproduce it" shows the script `tests/unit/test_learn_facing.py` runs against the clips and
// `tracklab learn browser --check` sets against the browser's query, read at build time one
// directory up from `web/`, like lesson 5's: they cannot drift apart.
const SCRIPT_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "facing.py");

export const metadata = lessonMetadata("facing");

export default function FacingLesson() {
  return <Lesson script={readFileSync(SCRIPT_PATH, "utf-8")} />;
}
