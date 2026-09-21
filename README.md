# Track Lab

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
