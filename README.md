# Track Lab

[![ci](https://github.com/javiersr1996/tracklab/actions/workflows/ci.yml/badge.svg)](https://github.com/javiersr1996/tracklab/actions/workflows/ci.yml)

**Live: https://tracklab-sable.vercel.app**

One schema, two sports, one renderer. Track Lab takes SkillCorner's open tracking and event data
for basketball and football, verifies every provider file against a pinned manifest, conforms
both sports into one silver schema with DuckDB and dbt, and publishes curated possessions that a
single Canvas renderer replays in the browser.

## Layers

```
SkillCorner repos --ingest--> raw ------bronze------> Parquet ---dbt---> silver ---publish---> JSON ---> web
(pinned commit,               (sha256 per file,        (native names,     (one schema,        (possessions,     (Next.js,
 manifest)                     receipt)                 typed)             both sports)        stats.json)       Canvas)
```

- **raw**: the provider's bytes, each file checked against the sha256 in
  `pipeline/manifest/sources.json`.
- **bronze**: one typed Parquet table per provider file family, native names and rows.
- **silver**: the conformed schema, [`docs/schema.md`](docs/schema.md), with the six decisions
  behind it and the evidence for each in [`docs/decisions.md`](docs/decisions.md).
- **publish**: `web/public/data/`, the possessions the site replays and `stats.json`, the only
  figures the site and this README quote.

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
and silver models, whose dbt tests run as asset checks, and `publish_possessions` and
`publish_stats` (group `publish`). The job `build` runs all of them. From `pipeline/`:

```
uv run dbt parse --project-dir dbt --profiles-dir dbt          # dagster-dbt reads target/manifest.json
uv run dagster job execute -m tracklab.dagster_defs -j build
TRACKLAB_DATA_ROOT=tests/fixtures/data uv run dagster asset materialize -m tracklab.dagster_defs --select "group:silver"
uv run dagster dev -m tracklab.dagster_defs                     # the UI
```

On the fixtures only silver is materialized: the whole graph would ingest the full bundles and
rebuild bronze over the slice. Select with groups rather than a bare `*`, which click expands
against the working directory on Windows.

## Platform

The pipeline as a product: [`/platform`](https://tracklab-sable.vercel.app/platform) draws the
Dagster asset graph and animates the five layers with the numbers the latest `tracklab build`
actually produced. Its H1 is the title `uv run tracklab publish platform` prints, from
`web/public/data/platform.json`:

```
title: 2.3 GB in, 1.2 MB out
```

`uv run dagster asset list -m tracklab.dagster_defs` lists `66` assets, the graph
`web/public/data/lineage.json` exports for the page.

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
