import { createEngine, type Engine, type EngineView } from "../duckdb/engine";

// "Run it here" (task 85): one engine per lesson, the shared one of `lib/duckdb/engine.ts`, over
// the JSON files the lesson already reads. Each file is registered under its path from the site's
// root, so `read_json('/data/learn/speed.json')` in a query names exactly what the page fetched,
// and those paths are the only ones the engine may open. The json extension is loaded before the
// engine is locked: the plan's hypothesis, from DuckDB 1.4.3 in Node, was that JSON is inside the
// engine, and in the browser `read_json` asked for it (task 85). It comes from this deployment,
// pinned by `scripts/copy-engine.mjs` like parquet.

export interface LearnFile {
  // From the site's root: `/data/learn/speed.json`.
  path: string;
  bytes: number;
}

export interface LearnQuery {
  slug: string;
  files: LearnFile[];
  views: EngineView[];
}

// A path that can go inside a SQL string as it is: no quote, no `..`, a JSON file under /data/.
const PATH = /^\/data\/(?:[a-z0-9_-]+\/)*[a-z0-9_.-]+\.json$/;

export function learnEngine({ slug, files, views }: LearnQuery): Engine {
  return createEngine({
    name: `learn-${slug}`,
    tables: views.map((v) => v.table),
    open: (origin) => {
      for (const f of files) {
        if (!PATH.test(f.path) || f.path.includes("..")) throw new Error(`learn ${slug}: file path ${JSON.stringify(f.path)}`);
      }
      return {
        files: files.map((f) => ({ table: f.path, file: f.path, url: `${origin}${f.path}`, bytes: f.bytes })),
        views,
      };
    },
    extensions: ["json"],
  });
}
