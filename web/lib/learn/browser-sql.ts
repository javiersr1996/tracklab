import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { LearnQuery } from "./engine";
import { learnFile } from "./files";

// A lesson's `pipeline/src/tracklab/learn/<slug>.browser.sql` (task 86), read at build time like
// the SQL of "Reproduce it", so the box and `tracklab learn browser --check` run the same text. Its
// `-- files:` line names what the engine registers, every statement but the last is a CREATE VIEW
// the engine runs when a query names its view, and the last is the query the box starts with. The
// rules are `tracklab.learn.browser.parse`'s.
const DIR = join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn");
const FILES_LINE = /^-- files: (.+)$/m;
const VIEW = /^CREATE VIEW (\w+) AS/m;

export interface BrowserSql {
  query: LearnQuery;
  // The views' statements as the file writes them, for the reader.
  views: string;
  sql: string;
}

export function parseBrowserSql(slug: string, text: string): Omit<BrowserSql, "query"> & { files: string[]; tables: { table: string; sql: string }[] } {
  const files = FILES_LINE.exec(text)?.[1].split(/\s+/);
  if (!files) throw new Error(`${slug}.browser.sql: no "-- files:" line`);
  const statements = text
    .split(/;[ \t]*\n/)
    .map((s) => s.trim())
    .filter(Boolean);
  const query = statements.pop()!.replace(/;\s*$/, "");
  const tables = statements.map((sql) => {
    const table = VIEW.exec(sql)?.[1];
    if (!table) throw new Error(`${slug}.browser.sql: a statement before the query is not a CREATE VIEW`);
    return { table, sql };
  });
  if (tables.length === 0 || VIEW.test(query)) throw new Error(`${slug}.browser.sql: not views followed by one query`);
  return { files, tables, views: statements.map((s) => `${s};`).join("\n\n"), sql: query };
}

export function browserSql(slug: string): BrowserSql {
  const { files, tables, views, sql } = parseBrowserSql(slug, readFileSync(join(DIR, `${slug}.browser.sql`), "utf-8"));
  return { query: { slug, files: files.map(learnFile), views: tables }, views, sql };
}
