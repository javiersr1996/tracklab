// The /sql course (task 101): the eight lessons in the order they are read, and
// `web/public/data/sql/course.json` (`tracklab sql course`, task 99), imported at build time like
// `warehouse.json`. The JSON carries, per lesson, the worked example (its SQL, columns and rows),
// the facts the prose prints (`<Fact>`: no number or name is typed) and, per exercise, the prompt,
// the hints, the reference SQL, and the shape and SHA-256 of its normalized result.
import type { Json } from "./normalize";
import courseJson from "../../public/data/sql/course.json";

export interface Exercise {
  id: string;
  prompt: string;
  hints: string[];
  solution: string;
  ordered: boolean;
  columns: number;
  rows: number;
  sha256: string;
}

export interface CourseLesson {
  slug: string;
  example: { sql: string; columns: string[]; rows: Json[][] };
  facts: Record<string, string>;
  exercises: Exercise[];
}

export interface Course {
  schema_version: number;
  duckdb_version: string;
  lessons: CourseLesson[];
}

// Through `unknown`: TypeScript reads each lesson's facts as its own object type, not a record.
export const COURSE = courseJson as unknown as Course;

export const SQL_LESSONS = [
  {
    n: 1,
    slug: "select",
    title: "Who took the most shots?",
    concept: "SELECT, ORDER BY, LIMIT",
    about: "A query names its columns, its table, the order of the rows and how many to keep.",
  },
  {
    n: 2,
    slug: "where",
    title: "Which full backs play the longest?",
    concept: "WHERE, AND, OR, NULL",
    about: "Keeping the rows that pass a test, combining tests, and the value that is not a value.",
  },
  {
    n: 3,
    slug: "expressions",
    title: "Percentages without dividing by zero",
    concept: "Computed columns, CASE, NULLIF, integer division",
    about: "Columns made from other columns, the two divisions, and a zero that must become NULL.",
  },
  {
    n: 4,
    slug: "group-by",
    title: "Which team scored the most?",
    concept: "GROUP BY, HAVING",
    about: "Folding the rows of a team into one, and which filter runs before and which after.",
  },
  {
    n: 5,
    slug: "joins",
    title: "Where does the extra row come from?",
    concept: "JOIN, LEFT JOIN, join keys",
    about: "Two football tables one row apart, the key that pairs them, and the rows with no pair.",
  },
  {
    n: 6,
    slug: "long-wide",
    title: "How can one table hold every metric?",
    concept: "Long and wide, PIVOT and CASE",
    about: "A row per metric instead of a column per metric, and how to turn one shape into the other.",
  },
  {
    n: 7,
    slug: "windows",
    title: "What percentile is a player in?",
    concept: "RANK, PERCENT_RANK, PARTITION BY",
    about: "A rank inside a position without collapsing the rows, the way /warehouse prints percentiles.",
  },
  {
    n: 8,
    slug: "scouting",
    title: "Who makes the shortlist?",
    concept: "CTEs, putting it together",
    about: "Named subqueries, one per pool, joined into a scouting report.",
  },
] as const;

export type SqlSlug = (typeof SQL_LESSONS)[number]["slug"];
export type SqlLessonMeta = (typeof SQL_LESSONS)[number];

export const SQL_SLUGS: readonly SqlSlug[] = SQL_LESSONS.map((l) => l.slug);

export const isSqlSlug = (slug: string): slug is SqlSlug => (SQL_SLUGS as readonly string[]).includes(slug);

export const sqlHref = (slug: SqlSlug) => `/sql/${slug}`;

export function sqlLessonMeta(slug: SqlSlug): SqlLessonMeta {
  return SQL_LESSONS.find((l) => l.slug === slug)!;
}

export function courseLesson(slug: SqlSlug): CourseLesson {
  const lesson = COURSE.lessons.find((l) => l.slug === slug);
  if (!lesson) throw new Error(`course.json has no lesson ${slug}: run \`tracklab sql course\``);
  return lesson;
}

// A fact of a lesson, as `facts.sql` computed it; a name the file does not have fails the build.
export function fact(slug: SqlSlug, name: string): string {
  const value = courseLesson(slug).facts[name];
  if (value === undefined) throw new Error(`lesson ${slug} has no fact ${name}: add it to sqlcourse/${slug}/facts.sql`);
  return value;
}

// What a cell of the worked example shows: NULL as the console shows it, the rest as JSON text.
export function exampleCell(v: Json): string {
  if (v === null) return "NULL";
  return typeof v === "string" ? v : JSON.stringify(v);
}
