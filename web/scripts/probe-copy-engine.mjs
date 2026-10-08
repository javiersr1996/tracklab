// Task 38 probe only (deleted when the task closes): the "self-hosted" option of decision 9,
// copying the engine out of node_modules before `next build`, as the plan describes it,
// plus the parquet extension, which duckdb-wasm 1.32.0 does not carry in its .wasm and
// otherwise autoloads from extensions.duckdb.org at query time.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

// DuckDB inside duckdb-wasm 1.32.0, as `db.getVersion()` reports it in the probe.
const DUCKDB = "v1.4.3";

const dist = new URL("../node_modules/@duckdb/duckdb-wasm/", import.meta.url);
const { version } = JSON.parse(readFileSync(new URL("package.json", dist), "utf8"));
const out = new URL(`../public/duckdb/${version}/`, import.meta.url);
mkdirSync(out, { recursive: true });
for (const file of [
  "duckdb-eh.wasm",
  "duckdb-browser-eh.worker.js",
  "duckdb-mvp.wasm",
  "duckdb-browser-mvp.worker.js",
]) {
  copyFileSync(new URL(`dist/${file}`, dist), new URL(file, out));
}
for (const platform of ["wasm_eh", "wasm_mvp"]) {
  const path = `${DUCKDB}/${platform}/parquet.duckdb_extension.wasm`;
  const res = await fetch(`https://extensions.duckdb.org/${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  const target = new URL(`../public/duckdb/ext/${path}`, import.meta.url);
  mkdirSync(new URL(".", target), { recursive: true });
  writeFileSync(target, Buffer.from(await res.arrayBuffer()));
}
console.log(`duckdb-wasm ${version} and the ${DUCKDB} parquet extension copied to public/duckdb/`);
