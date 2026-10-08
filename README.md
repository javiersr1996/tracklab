# Track Lab

[![ci](https://github.com/javiersr1996/tracklab/actions/workflows/ci.yml/badge.svg)](https://github.com/javiersr1996/tracklab/actions/workflows/ci.yml)

**Live: https://tracklab-sable.vercel.app**

One schema, two sports, one renderer. Track Lab takes SkillCorner's open tracking and event data
for basketball and football, verifies every provider file against a pinned manifest, conforms
both sports into one silver schema with DuckDB and dbt, and publishes curated possessions that a
single Canvas renderer replays in the browser.

## Layers

```
SkillCorner repos --ingest--> raw ------bronze------> Parquet ---dbt---> silver ---dbt---> gold ---publish---> JSON + Parquet ---> web
(pinned commit,               (sha256 per file,        (native names,     (one schema,       (season          (possessions,           (Next.js,
 manifest)                     receipt)                 typed)             both sports)       aggregates)      stats.json, warehouse)  Canvas, DuckDB-WASM)
```

- **raw**: the provider's bytes, each file checked against the sha256 in
  `pipeline/manifest/sources.json`.
- **bronze**: one typed Parquet table per provider file family, native names and rows.
- **silver**: the conformed schema, [`docs/schema.md`](docs/schema.md), with the six decisions
  behind it and the evidence for each in [`docs/decisions.md`](docs/decisions.md).
- **gold**: the season aggregates as wide tables, one per sport and family, and a dimensional
  model of them (players, teams, metrics and one long fact table), see [Warehouse](#warehouse).
- **publish**: `web/public/data/`, the possessions the site replays, the Parquet the browser
  queries and the JSON that describes them (`stats.json`, `warehouse.json`, `platform.json`),
  the only figures the site and this README quote.

The same query reads both sports: `SELECT * FROM frames WHERE sport = ?` returns 9,126,744 rows
of basketball and 20,213,849 of football (`web/public/data/stats.json`). The provider bundles
weigh 2,316,182,304 bytes as pinned (`bytes.raw.total`); the site ships 1,110,509 bytes of
possessions (`bytes.published.total`).

## Layout

A monorepo with `pipeline/` (Python, DuckDB, dbt, Dagster) and `web/` (Next.js). See
`tasks/todo.md` for the plan, task by task, with what each one measured.

## Development

From `pipeline/`:

```
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run tracklab --help
```

Python version pinned in `pipeline/.python-version`. From `web/`:

```
npm ci
npm run lint && npm run typecheck && npm run test && npm run build
npm run e2e                                              # Playwright against a local next start
BASE_URL=https://tracklab-sable.vercel.app npx playwright test   # the same suite, against production
```

## Orchestration

The pipeline is a Dagster graph (`uv run dagster asset list -m tracklab.dagster_defs`):
`raw_<sport>`, `bronze_<sport>_<table>` (one step per `tracklab bronze --tables` group),
`bronze_common_orientation` and the `reports_orientation_<sport>` CSVs it writes, the dbt seeds
and silver models and the season-aggregate gold models (group `gold`), whose dbt tests run as asset checks, and `publish_possessions` and
`publish_stats` (group `publish`). The job `build` runs all of them. From `pipeline/`:

```
uv run dbt parse --project-dir dbt --profiles-dir dbt          # dagster-dbt reads target/manifest.json
uv run dagster job execute -m tracklab.dagster_defs -j build
TRACKLAB_DATA_ROOT=tests/fixtures/data uv run dagster asset materialize -m tracklab.dagster_defs --select "group:silver or group:gold"
uv run dagster dev -m tracklab.dagster_defs                     # the UI
```

On the fixtures only silver and gold are materialized: the whole graph would ingest the full bundles and
rebuild bronze over the slice. Select with groups rather than a bare `*`, which click expands
against the working directory on Windows.

## Platform

The pipeline as a product: [`/platform`](https://tracklab-sable.vercel.app/platform) draws the
Dagster asset graph and animates the layers, raw to publish, with the numbers the latest
`tracklab build` actually produced. Its H1 and the line under it are the title and subtitle
`uv run tracklab publish platform` prints, from `web/public/data/platform.json`. "Out" counts what
the browser downloads from `web/public/data`: the JSON it watches and the Parquet it queries
(`lineage.json` and `platform.json` excluded, as they describe the platform rather than its data).

```
title: 2.3 GB in, 3.3 MB out
subtitle: 1.3 MB to watch, 2.0 MB to query
```

`uv run dagster asset list -m tracklab.dagster_defs` lists `76` assets, the graph
`web/public/data/lineage.json` exports for the page.

## Warehouse

Gold is the season aggregates, queryable. `uv run tracklab publish warehouse` writes each gold
table as a Parquet file with its content hash in the name (`web/public/data/warehouse/`), written by
pyarrow with a fixed compression, row group size and row order so the bytes are reproducible, and
describes them in `web/public/data/warehouse.json`: rows, row groups with their key ranges and bytes
per table. The long fact table (one row per player, season and metric) has `366962` rows in row
groups of `50000` ordered by metric, so a query for one metric skips the others.

[`/warehouse`](web/app/warehouse) runs SQL over those files in the visitor's browser with DuckDB-WASM,
loaded only when a query is run, and shows next to each result the bytes the engine and the data
cost, counted by the engine itself. Five example queries have their answers in
`web/public/data/warehouse_examples.json`, and the page says what each percentile is a percentile
of (people, not rows).

The same model lives in Postgres as the second path: `uv run tracklab load postgres` loads it
incrementally by row fingerprint (a second run prints `inserted=0 updated=0 deleted=0`), and
`uv run tracklab publish warehouse-pg --where local|ci|neon` writes `warehouse_pg.json` with what
Postgres answers to the same queries, its `EXPLAIN` plans and the size of each table. The numbers
in the repository come from a local Postgres in Docker: `127792819` bytes for the whole database,
`366962` rows in the fact table. The Neon project that would serve the queries live is pending the
account: until it exists `/warehouse` runs without `DATABASE_URL` and shows that snapshot, dated
and labelled with where it was measured.

```
uv run tracklab publish warehouse --check          # the Parquet are what gold would write
uv run tracklab publish examples --check           # warehouse_examples.json is what gold answers
uv run tracklab load postgres                      # needs TRACKLAB_PG_DSN in .env
```

## Data quality

`uv run tracklab quality` runs the checks of `pipeline/src/tracklab/quality/` on silver (and
bronze where silver does not carry the field): detection flags, the ball's apparent gravity,
the shot entry angle, horizontal noise against the declared error, the clock, and the format
partitions no field declares. Each writes `pipeline/reports/quality_<check>.csv`, one row per
sport, match and metric. The gravity estimator is validated on synthetic flights of known g
in `pipeline/tests/unit/test_quality_flight.py` before it reads a real ball.

## Run from a clean clone

Five commands: download both bundles (verified against the manifest), then bronze, the
orientation probe, silver, the published JSON and every contract test.
`scripts/clean_clone_check.sh` runs this block as written, in a temporary directory, and prints
`CLEAN CLONE OK`.

<!-- clean-clone:begin -->
```sh
git clone https://github.com/javiersr1996/tracklab.git && cd tracklab/pipeline
uv sync --locked
uv run dbt parse --project-dir dbt --profiles-dir dbt
uv run tracklab build
uv run pytest -q
```
<!-- clean-clone:end -->

## Ingest

Sources are pinned in `pipeline/manifest/sources.json` (commit, bytes and sha256 per file).
From `pipeline/`:

```
uv run tracklab freeze opendata-football    # re-pin: resolve the ref, read LFS pointers, hash the rest
uv run tracklab ingest opendata-football    # download to data/raw/opendata-football/, verify sha256
```

`ingest` is idempotent: files whose sha256 already matches are skipped, mismatches are deleted and
downloaded again, and `data/raw/<source>/_receipt.json` records the outcome. Exit code `1` means at
least one file could not be verified. LFS files are fetched from `media.githubusercontent.com` by
URL, so neither `git-lfs` nor a clone is needed. `GITHUB_TOKEN`, if set, is used for the API calls.
`--from-existing <dir>` verifies a local clone in place instead; if a file fails only because a
Windows checkout turned its line endings into CRLF, the message says so and names
`core.autocrlf`.

## Data and license

The code is MIT ([`LICENSE`](LICENSE)). The data is SkillCorner's open data, published under the
MIT license in [SkillCorner/opendata](https://github.com/SkillCorner/opendata) (football) and
[SkillCorner/opendata-basketball](https://github.com/SkillCorner/opendata-basketball)
(basketball). Credit for the tracking and event data goes to SkillCorner; this repository
redistributes only what the site replays (`web/public/data/`) and the one-possession-per-sport
slice CI builds on (`pipeline/tests/fixtures/data/bronze/`).
