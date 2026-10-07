"""The plugin that creates silver's output directories, on invented model files.

It exists because DuckDB will not create the directory it copies into, so a
clean clone fails on the first external model of the run. There is no way to see
that failure from the built repository (the directories are there once anything
has run), which is exactly the case task 9 argued for fabricated data: the only
place this behaviour can be exercised is a directory that does not exist yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tracklab.silver.dbt_plugin import Plugin, ensure_model_dirs


def _models(root: Path, names: list[str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).write_text("SELECT 1\n", encoding="utf-8")
    return root


def test_creates_one_directory_per_model(tmp_path: Path) -> None:
    models = _models(tmp_path / "models", ["dim_match.sql", "dim_team.sql", "frames.sql"])
    silver = tmp_path / "silver"

    made = ensure_model_dirs(silver, models)

    assert [p.name for p in made] == ["dim_match", "dim_team", "frames"]
    assert all(p.is_dir() for p in made)


def test_creates_the_root_too(tmp_path: Path) -> None:
    """The root is missing on a clean clone, not just the table directory."""
    models = _models(tmp_path / "models", ["dim_match.sql"])
    silver = tmp_path / "deep" / "silver"

    ensure_model_dirs(silver, models)

    assert (silver / "dim_match").is_dir()


def test_is_idempotent_and_keeps_what_is_there(tmp_path: Path) -> None:
    models = _models(tmp_path / "models", ["dim_match.sql"])
    silver = tmp_path / "silver"
    ensure_model_dirs(silver, models)
    built = silver / "dim_match" / "data.parquet"
    built.write_bytes(b"not really parquet")

    ensure_model_dirs(silver, models)

    assert built.read_bytes() == b"not really parquet"


def test_ignores_everything_that_is_not_a_model(tmp_path: Path) -> None:
    models = _models(tmp_path / "models", ["dim_match.sql", "schema.yml", "notes.md"])
    silver = tmp_path / "silver"

    made = ensure_model_dirs(silver, models)

    assert [p.name for p in made] == ["dim_match"]


def test_no_models_creates_nothing(tmp_path: Path) -> None:
    made = ensure_model_dirs(tmp_path / "silver", _models(tmp_path / "models", []))

    assert made == []
    assert not (tmp_path / "silver").exists()


def test_plugin_reads_its_profile_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """What profiles.yml passes is what gets created, so a fixture run of task 14
    can point the same plugin at a throwaway root. The gold defaults are relative to
    the cwd, so a test that leaves them out would write `data/gold` into the repo."""
    monkeypatch.chdir(tmp_path)
    _models(tmp_path / "dbt" / "models" / "gold", ["agg_bb_shots.sql"])  # the default tree
    models = _models(tmp_path / "models", ["dim_sport.sql"])
    silver = tmp_path / "elsewhere"

    Plugin(
        name="tracklab",
        plugin_config={
            "silver_dir": str(silver),
            "models_dir": str(models),
            "gold_dir": str(tmp_path / "gold"),
            "gold_models_dir": str(tmp_path / "dbt" / "models" / "gold"),
        },
    )

    assert (silver / "dim_sport").is_dir()
    assert (tmp_path / "gold" / "agg_bb_shots").is_dir()
    assert not (tmp_path / "data").exists()


def test_plugin_creates_the_gold_directories_too(tmp_path: Path) -> None:
    """Gold is external like silver (task 40), so a clean clone dies the same way
    on its first model unless the plugin also makes `<gold_dir>/<model>/`."""
    silver_models = _models(tmp_path / "silver_models", ["dim_sport.sql"])
    gold_models = _models(tmp_path / "gold_models", ["agg_bb_shots.sql", "dim_player.sql"])
    gold = tmp_path / "data" / "gold"

    Plugin(
        name="tracklab",
        plugin_config={
            "silver_dir": str(tmp_path / "data" / "silver"),
            "models_dir": str(silver_models),
            "gold_dir": str(gold),
            "gold_models_dir": str(gold_models),
        },
    )

    assert sorted(p.name for p in gold.iterdir()) == ["agg_bb_shots", "dim_player"]
