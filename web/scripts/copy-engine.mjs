// Task 42, decision 9 (confirmed 2026-10-08): the DuckDB-WASM engine and its parquet
// extension are served from this deployment, so the page never fetches from another origin.
// Runs before `next build` and `next dev`; what it writes (public/duckdb/) is ignored by git.
//
// - The engine (both bundles: `selectBundle` picks eh, or mvp where WebAssembly exceptions are
//   missing) is copied out of node_modules into public/duckdb/<package version>/.
// - duckdb-wasm 1.32.0 does not carry parquet inside its .wasm and otherwise autoloads it from
//   extensions.duckdb.org at query time (task 38). The build downloads it once into
//   public/duckdb/ext/, the custom extension repository the engine is pointed at, and keeps it
//   only if its sha256 is the pinned one.
// - Nor json, which /learn's "Run it here" reads (task 85: in the browser `read_json` asked for it,
//   though DuckDB 1.4.3 in Node has it inside), pinned and served the same way.
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

// The DuckDB inside duckdb-wasm 1.32.0 (`db.getVersion()`, task 38) and the sha256 of each
// extension per bundle, as extensions.duckdb.org served them (parquet on 2026-10-08, json on
// 2026-10-24). All belong to one engine version: bumping @duckdb/duckdb-wasm means re-pinning them.
const PINNED_PACKAGE = "1.32.0";
const DUCKDB = "v1.4.3";
const EXTENSIONS = {
  parquet: {
    wasm_eh: "22765c8f7dc741cda2b571a66ac7bb355295d7d69a6c37e5315b265672984f55",
    wasm_mvp: "0785c6c95d003eff4faa7b3b4b660f02c9c92f6d68d135ddf330d42e3a650600",
  },
  json: {
    wasm_eh: "b997276c8e15cc3ebdeda340d73d15dc1c4f4755ad281280451cb0a2f79302e9",
    wasm_mvp: "5771b6d57335eca8e2ba4fdaacb491a53b49577bd7f1b0c39e2cd7a39b4e9313",
  },
};
const ENGINE_FILES = [
  "duckdb-eh.wasm",
  "duckdb-browser-eh.worker.js",
  "duckdb-mvp.wasm",
  "duckdb-browser-mvp.worker.js",
];

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

const pkg = new URL("../node_modules/@duckdb/duckdb-wasm/", import.meta.url);
const { version } = JSON.parse(readFileSync(new URL("package.json", pkg), "utf8"));
if (version !== PINNED_PACKAGE) {
  throw new Error(`@duckdb/duckdb-wasm ${version} installed; the extension pins are for ${PINNED_PACKAGE}`);
}

const engineDir = new URL(`../public/duckdb/${version}/`, import.meta.url);
mkdirSync(engineDir, { recursive: true });
for (const file of ENGINE_FILES) copyFileSync(new URL(`dist/${file}`, pkg), new URL(file, engineDir));

// `wasm_eh/parquet`, `wasm_mvp/json`, ... and the sha256 each must have.
const PINS = Object.entries(EXTENSIONS).flatMap(([name, pins]) =>
  Object.entries(pins).map(([platform, sha]) => [`${platform}/${name}`, sha]),
);
for (const [file, pinned] of PINS) {
  const path = `${DUCKDB}/${file}.duckdb_extension.wasm`;
  const target = new URL(`../public/duckdb/ext/${path}`, import.meta.url);
  if (existsSync(target) && sha256(readFileSync(target)) === pinned) continue;
  const res = await fetch(`https://extensions.duckdb.org/${path}`);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  const bytes = Buffer.from(await res.arrayBuffer());
  if (sha256(bytes) !== pinned) throw new Error(`${path}: sha256 ${sha256(bytes)}, pinned ${pinned}`);
  mkdirSync(new URL(".", target), { recursive: true });
  writeFileSync(target, bytes);
}
console.log(`duckdb-wasm ${version} and the ${DUCKDB} ${Object.keys(EXTENSIONS).join(" and ")} extensions are in public/duckdb/`);
