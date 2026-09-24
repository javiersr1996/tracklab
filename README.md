# Track Lab

[![ci](https://github.com/javiersr1996/tracklab/actions/workflows/ci.yml/badge.svg)](https://github.com/javiersr1996/tracklab/actions/workflows/ci.yml)

Track Lab ingests raw tracking and event data from professional football and basketball
matches, verifies and conforms it through a bronze/silver pipeline built on DuckDB and dbt,
and publishes it as an interactive match replay and stats site.
It exists to demonstrate production-grade data engineering, typed schemas, contract tests,
reproducible ingestion, applied to real sports data rather than toy datasets.
The audience is hiring managers in professional sports evaluating data engineering skill
firsthand.

## Layout

A monorepo with `pipeline/` (Python, DuckDB, dbt, Dagster) and `web/` (Next.js, not built yet).
See `tasks/todo.md` for the full architecture and task breakdown.

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

Python 3.13, pinned in `.python-version`.

## Orchestration

The pipeline is a Dagster graph of **59 assets** (`uv run dagster asset list -m
tracklab.dagster_defs`): `raw_<sport>` (2), `bronze_<sport>_<table>` (40, one step per
`tracklab bronze --tables` group), `bronze_common_orientation` and the two
`reports_orientation_<sport>` CSVs it writes, the dbt seeds (2) and the silver models (10),
whose dbt tests run as asset checks, plus `publish_possessions` and `publish_stats`
(task 17, group `publish`, not part of `group:silver`). The job `build` runs all of them.
From `pipeline/`:

```
uv run dbt parse --project-dir dbt --profiles-dir dbt          # dagster-dbt reads target/manifest.json
uv run dagster job execute -m tracklab.dagster_defs -j build
TRACKLAB_DATA_ROOT=tests/fixtures/data uv run dagster asset materialize -m tracklab.dagster_defs --select "group:silver"
uv run dagster dev -m tracklab.dagster_defs                     # the UI
```

On the fixtures only silver is materialized: the whole graph would ingest the full bundles and
rebuild bronze over the slice. Select with groups rather than a bare `*`, which click expands
against the working directory on Windows.

## Run from a clean clone

Five commands, about 2.3 GB of download (both bundles, verified against the manifest), then
bronze, the orientation probe, silver and every contract test.
`scripts/clean_clone_check.sh` runs this block as written, in a temporary directory, and prints
`CLEAN CLONE OK`.

<!-- clean-clone:begin -->
```sh
git clone https://github.com/javiersr1996/tracklab.git && cd tracklab/pipeline
uv sync --locked
uv run dbt parse --project-dir dbt --profiles-dir dbt
uv run dagster job execute -m tracklab.dagster_defs -j build
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
downloaded again, and `data/raw/<source>/_receipt.json` records the outcome. Exit code 1 means at
least one file could not be verified. LFS files are fetched from `media.githubusercontent.com` by
URL, so neither `git-lfs` nor a clone is needed. `GITHUB_TOKEN`, if set, is used for the API calls.
