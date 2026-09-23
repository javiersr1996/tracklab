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
