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
weigh 3,583,918,346 bytes as pinned (`bytes.raw.total`); the site ships 1,110,509 bytes of
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
`publish_stats` (group `publish`), the five assets of [P5](#the-run-that-moves-nobody) (group
`runs`) and the four of [P6](#body-pose) (group `pose`). The job `build` runs all of them. From `pipeline/`:

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
`web/public/data` publishes, split by use: to watch, the possessions and the JSON the other pages
are built from; to query, what only `/warehouse` uses, the Parquet and the `warehouse*.json` that
describe them (`lineage.json` and `platform.json` excluded, as they describe the platform rather
than its data).

```
title: 3.6 GB in, 7.5 MB out
subtitle: 5.5 MB to watch, 2.1 MB to query
```

`uv run dagster asset list -m tracklab.dagster_defs` lists `88` assets, the graph
`web/public/data/lineage.json` exports for the page.

## The run that moves nobody

[`/runs`](https://tracklab-sable.vercel.app/runs) is the project that died, published dead. It
asked which off-ball run types move the defence in the tracking, with a protocol written before
any outcome was computed (`pipeline/reports/runs_protocol.json`) and death criteria M1 to M5b.
It stopped at M5a: no subtype was left to take to the held-out matches, which were never opened.

M2 passed: the instrument sees a displacement it is forced to see, so the instrument works. M3 is
what removed every probable subtype: the displacement before the run's `frame_start` already
reaches more than half of the one after it. A look at the runners' speed written after the
verdict (post hoc, it decides nothing) says why: `frame_start` comes late, the runner is already
at speed at the instant the cause is measured (`t_c`), and M3 cannot separate the run from its own
acceleration. The page says this design and this data could not tell a run from its acceleration;
it does not say what any run does to the defence.

```
dead_at: M5a
candidates: 0
M2 marker mean: 1.423 m, same sign in 10 of 10 matches
M3 pre-trend ratio, run_ahead_of_the_ball: 1.5254
post hoc, run_ahead_of_the_ball, runner at 4.0 m/s or more at t_c: 0.987
```

In the graph the five assets of group `runs` do not write: each runs the `--check` of its command,
which recomputes the versioned artefact from the warehouse and compares it. CI runs the checks on
the fixtures (they say how much they verified) and `full-build` on the whole warehouse, after the
build.

```
uv run tracklab runs protocol --check      # the split and the death criteria
uv run tracklab runs coverage --check      # runs, windows and placebos per match
uv run tracklab runs probe --check         # M1 and M2 (takes minutes)
uv run tracklab runs effect --check        # M3 to M5a
uv run tracklab publish runs --check       # runs.json and the two clips
```

## Body pose

[`/pose`](https://tracklab-sable.vercel.app/pose) is the Body Pose SkillCorner publishes for two
full matches: the joints of the players it resolves in each frame, each with its predicted error. It
is meant for detected players, but a few rows with a pose are not flagged as detected (counted below). The question is narrow, the cadence and the step in the high-speed stretches,
per match and per player, and the instrument is the signal of the ankles' separation along the
run. The protocol (`pipeline/reports/pose_protocol.json`) was written and frozen on one match
before the other was read, and the other was read once. The page says the state the project
reached, and what the data do not say: pose exists only for detected players, z is relative to the
player's centroid and is no height, and the tracking and the pose are generated apart. The tables
carry the number of windows behind every value and the error propagated from the joints' predicted
error beside it. Nothing on the page ranks players, reads intent or measures an absolute height.

```
status: alive
M4: 27 of 27 players, median propagated sd 0.040166 Hz against 0.131793 Hz
pose in the player-frames: 0.3143 of 1925299 and 0.3638 of 1996435
pose.json: 51570 bytes, hook clips: 784665 and 696714 bytes
pose rows not flagged as detected: 2 of 1540715 in 1925299 and 1357 of 1571830 in 1996435
```

The clips are a few seconds of each match, chosen by rule (the window of the high band whose cadence
is nearest to the match's median, never the maximum) and drawn from the Parquet the pose zips become;
the inflated JSON is read as a stream and never reaches the disk.
In the graph the four assets of group `pose` only check, like the runs ones; CI runs the checks on
the fixtures and `full-build` on the whole bronze.

```
uv run tracklab ingest opendata-bodypose        # the two zips, verified against the manifest
uv run tracklab bronze football --tables bodypose
uv run tracklab pose coverage --check           # frames and joints with a pose, per match
uv run tracklab pose protocol --check           # the frozen protocol against the code
uv run tracklab pose metric --check             # the metric in both matches (takes a while)
uv run tracklab publish pose --check            # pose.json and the clips
```

## Learn

[`/learn`](https://tracklab-sable.vercel.app/learn) is a series of short lessons that start from one
question the data can answer and build the tool by hand, grouped by level. The text carries no figure
of its own: every number on a page is read from a published file or computed in the browser from one,
and the end-to-end test compares each with its source. Where a lesson needs the data it says what the
numbers do not explain and leaves the cause open.

Foundations: does the ball obey gravity (a least-squares parabola through a shot), where the
provider's speed comes from (finite differences and noise), whether a court and a pitch can share one
table (coordinates and interpolation), and whether the game clock keeps the video's time (a line
through two clocks). Intermediate: who gets to the rebound first, how fast a pass travels, at what
angle the ball reaches the rim, how many bounces per second, and how often possession changes hands.
Advanced: how many steps per second (periodicity in body pose) and which way a player is facing (a
direction from two shoulders and a nose, and circular statistics).

Each lesson ends with "Reproduce it": the query or script that gives its figures on the provider's
public files, and, for the SQL ones, "Run it here", the same query in the DuckDB-WASM the warehouse
uses, over the JSON files the page already reads (it adds no data). Every browser query has a twin in
`pipeline/src/tracklab/learn/<lesson>.browser.sql` that `learn browser --check` runs against
`web/public/data`. The lessons that publish a table (`web/public/data/learn/<lesson>.json`) have a
publisher whose `--check` rebuilds the file from bronze, compares its bytes and runs the lesson's SQL
on the raw files. Every link to a lesson carries its own social card (the question, the lesson number
and level, no figure), and `/sitemap.xml` and `/robots.txt` list them.

CI runs the checks on the fixtures (they print PARTIAL and what they verified); `full-build` runs them
on the whole bronze with `TRACKLAB_REQUIRE_FULL=1`, under which a `--check` that says PARTIAL exits non-zero.

```
uv run tracklab learn gravity --check           # the first lesson's SQL against quality.json
uv run tracklab learn hypotheses --check        # gravity.json, the data against the first lesson's hypotheses
uv run tracklab learn speed --check             # speed.json and the second lesson's SQL
uv run tracklab learn clock --check             # clock.json and its SQL
uv run tracklab learn rebound --check           # rebound.json and its SQL
uv run tracklab learn pass --check              # pass.json and its SQL
uv run tracklab learn entry --check             # entry.json and its script
uv run tracklab learn dribble --check           # dribble.json and its SQL
uv run tracklab learn possession --check        # possession.json, football and basketball
uv run tracklab learn browser --check           # every "Run it here" query against web/public/data
TRACKLAB_REQUIRE_FULL=1 uv run tracklab learn speed --check   # fail on PARTIAL
```

The coordinates, cadence and facing lessons publish nothing of their own: the page computes from
files that already exist, and `learn browser --check` covers their queries.

## Warehouse

Gold is the season aggregates, queryable. `uv run tracklab publish warehouse` writes each gold
table as a Parquet file with its content hash in the name (`web/public/data/warehouse/`), written by
pyarrow with a fixed compression, row group size and row order so the bytes are reproducible, and
describes them in `web/public/data/warehouse.json`: rows, row groups with their key ranges and bytes
per table. The long fact table (one row per player, season and metric) has `366962` rows in row
groups of `50000` ordered by metric, so a query for one metric skips the others.

[`/warehouse`](web/app/warehouse) runs SQL over those files in the visitor's browser with DuckDB-WASM,
loaded only when a query is run, and shows next to each result the bytes the engine and the data
cost, counted by the engine itself. The example queries have their answers in
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
uv run --env-file .env tracklab load postgres       # TRACKLAB_PG_DSN in pipeline/.env (ignored)
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
