import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Lesson } from "../../../components/learn/coordinates/Lesson";

// The query "Reproduce it" shows, read at build time from the pipeline like lesson 1's: it was run
// against the two public SkillCorner repositories (DuckDB 1.5.5) and its results match the page.
const SQL_PATH = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "coordinates.sql");

export default function CoordinatesLesson() {
  return <Lesson sql={readFileSync(SQL_PATH, "utf-8")} />;
}
