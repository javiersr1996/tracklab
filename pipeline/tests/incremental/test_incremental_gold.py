"""Task 129: gold is skipped when nothing it depends on changed.

Two parts. The first is fast: the fingerprint of the gold step on a copy of the fixtures' inputs,
one test per class of input (leaving a class out of the digest fails its test), and the plan over
a hand-made gold tree. The second runs the real job (`run_build`, Dagster's multiprocess executor
and dbt) on a temporary copy of the fixtures' bronze, in chained module fixtures: a first build,
a rerun that skips, a rerun after `aggregates_shots` changed, `TRACKLAB_REQUIRE_FULL`, and a run
whose dbt test fails followed by the old bronze put back.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tracklab.build import run_build
from tracklab.silver import dbt_plugin
from tracklab.silver.incremental import (
    FULL_ENV,
    GOLD,
    STATE_VERSION,
    GoldFingerprint,
    Inputs,
    engine_versions,
    external_models,
    finish_gold,
    forget_gold,
    full_reason,
    gold_fingerprint,
    gold_sources,
    make_gold_plan,
    read_state,
    silver_sources,
    state_path,
    write_state,
)

PIPELINE = Path(__file__).resolve().parents[2]
FIXTURES = PIPELINE / "tests" / "fixtures" / "data"
DBT_TARGET = PIPELINE / "dbt" / "target"
DBT_MANIFEST = PIPELINE / "dbt" / "target" / "manifest.json"
SHOTS = Path("bronze/basketball/aggregates_shots/data.parquet")
AGGREGATES = {
    "basketball": ("aggregates_drives", "aggregates_picks", "aggregates_shots"),
    "football": ("aggregates_obr", "aggregates_passing", "aggregates_physical"),
}


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(DBT_MANIFEST.read_text(encoding="utf-8"))
    return loaded


@pytest.fixture
def inputs(tmp_path: Path) -> Inputs:
    data = tmp_path / "data"
    shutil.copytree(FIXTURES / "bronze", data / "bronze")
    dbt = tmp_path / "dbt"
    dbt.mkdir()
    for name in ("dbt_project.yml", "profiles.yml"):
        shutil.copyfile(PIPELINE / "dbt" / name, dbt / name)
    for folder in ("models", "macros", "seeds", "tests"):
        shutil.copytree(PIPELINE / "dbt" / folder, dbt / folder)
    plugin = tmp_path / "dbt_plugin.py"
    shutil.copyfile(dbt_plugin.__file__, plugin)
    return Inputs(data, tmp_path / "reports", tmp_path / "manifest", dbt, plugin, engine_versions())


@pytest.fixture
def sources(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    return gold_sources(manifest)


def _touch(path: Path) -> None:
    with path.open("ab") as handle:
        handle.write(b"\n")


def _groups_moved(sources: list[tuple[str, str]], inputs: Inputs, path: Path) -> set[str]:
    before = gold_fingerprint(sources, inputs)
    _touch(path)
    after = gold_fingerprint(sources, inputs)
    assert (before.digest != after.digest) == (before.groups != after.groups)
    return {g for g in before.groups if before.groups[g] != after.groups[g]}


def test_gold_reads_the_six_season_aggregates_and_nothing_else(
    sources: list[tuple[str, str]],
) -> None:
    expected = {
        (f"bronze_{sport}", table) for sport, tables in AGGREGATES.items() for table in tables
    }
    assert set(sources) == expected


@pytest.mark.parametrize(
    "relative",
    [f"bronze/{sport}/{table}/data.parquet" for sport, ts in AGGREGATES.items() for table in ts],
)
def test_each_season_aggregate_moves_the_bronze_group(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str
) -> None:
    assert _groups_moved(sources, inputs, inputs.data_dir / relative) == {"bronze"}


def test_another_parquet_in_a_season_folder_moves_it_too(
    sources: list[tuple[str, str]], inputs: Inputs
) -> None:
    """dbt reads `<table>/*.parquet`: a second file there is an input."""
    folder = inputs.data_dir / "bronze" / "basketball" / "aggregates_shots"
    before = gold_fingerprint(sources, inputs)
    shutil.copyfile(folder / "data.parquet", folder / "extra.parquet")
    assert gold_fingerprint(sources, inputs).groups["bronze"] != before.groups["bronze"]


@pytest.mark.parametrize(
    "relative",
    [
        "models/gold/agg_bb_shots.sql",
        "models/gold/dim_player.sql",
        "models/gold/schema.yml",
        "models/sources/basketball.yml",
        "macros/agg_long.sql",
        "tests/assert_gold_fact_joins_its_dimensions.sql",
        "dbt_project.yml",
        "profiles.yml",
    ],
)
def test_the_dbt_project_moves_the_dbt_group(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str
) -> None:
    assert _groups_moved(sources, inputs, inputs.dbt_dir / relative) == {"dbt"}


def test_the_plugin_moves_the_plugin_group(sources: list[tuple[str, str]], inputs: Inputs) -> None:
    assert _groups_moved(sources, inputs, inputs.plugin) == {"plugin"}


@pytest.mark.parametrize("package", ["duckdb", "dbt-core", "dbt-adapters", "dbt-duckdb"])
def test_the_engine_moves_the_engine_group(
    sources: list[tuple[str, str]], inputs: Inputs, package: str
) -> None:
    before = gold_fingerprint(sources, inputs)
    after = gold_fingerprint(sources, replace(inputs, engine={**inputs.engine, package: "999.0.0"}))
    assert [g for g in before.groups if before.groups[g] != after.groups[g]] == ["engine"]
    assert before.digest != after.digest


@pytest.mark.parametrize(
    "relative",
    [
        "data/bronze/basketball/games/114243.parquet",
        "data/bronze/basketball/matches/data.parquet",
        "data/bronze/football/tracking_objects/1874553.parquet",
        "data/bronze/common/orientation/data.parquet",
        "dbt/models/silver/frames.sql",
        "dbt/models/silver/schema.yml",
        "dbt/seeds/event_type_map.csv",
    ],
)
def test_what_gold_does_not_read_changes_nothing(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str
) -> None:
    assert _groups_moved(sources, inputs, inputs.data_dir.parent / relative) == set()


def test_a_source_of_an_unknown_family_fails(inputs: Inputs) -> None:
    for source in ("elsewhere", "bronze_common"):
        with pytest.raises(ValueError, match=source):
            gold_fingerprint([(source, "table")], inputs)


def test_a_gold_model_reading_silver_fails(manifest: dict[str, Any]) -> None:
    silver = next(key for key, node in manifest["nodes"].items() if node["name"] == "dim_match")
    gold = next(key for key, node in manifest["nodes"].items() if node["name"] == "dim_player")
    nodes = {**manifest["nodes"]}
    nodes[gold] = {**nodes[gold], "depends_on": {"nodes": [silver]}}
    with pytest.raises(ValueError, match="dim_player.*outside gold"):
        gold_sources({**manifest, "nodes": nodes})


def test_silver_and_gold_read_disjoint_models(manifest: dict[str, Any]) -> None:
    assert not set(external_models(manifest)) & set(external_models(manifest, gold=True))
    assert len(external_models(manifest, gold=True)) == 10
    assert not {t for _, t in gold_sources(manifest)} & {t for _, t in silver_sources(manifest)}


# --- the plan --------------------------------------------------------------------

MODELS = ["agg_a", "dim_b"]


def _fp(**moved: str) -> GoldFingerprint:
    groups = {"bronze": "b", "dbt": "d", "plugin": "p", "engine": "e", **moved}
    return GoldFingerprint("|".join(sorted(groups.values())), groups)


def _state(fp: GoldFingerprint) -> dict[str, Any]:
    return {"version": STATE_VERSION, "run_id": "run-1", "digest": fp.digest, "groups": fp.groups}


def _tree(data: Path, models: list[str] = MODELS) -> None:
    for model in models:
        out = data / "gold" / model / "data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"PAR1")


def test_no_state_is_a_full_build(tmp_path: Path) -> None:
    _tree(tmp_path)
    plan = make_gold_plan(_fp(), None, tmp_path, MODELS, None)
    assert (plan.mode, plan.reason) == (
        "full",
        "no state left by a successful run of the whole step",
    )


def test_unchanged_inputs_and_outputs_skip_and_say_which_run(tmp_path: Path) -> None:
    _tree(tmp_path)
    plan = make_gold_plan(_fp(), _state(_fp()), tmp_path, MODELS, None)
    assert (plan.mode, plan.reason) == ("skip", "no input changed since run run-1")
    assert plan.record() == {
        "mode": "skip",
        "reason": plan.reason,
        "written": [],
        "skipped": [],
        "deleted": [],
    }


@pytest.mark.parametrize("group", ["bronze", "dbt", "plugin", "engine"])
def test_a_moved_group_is_a_full_build_that_names_it(tmp_path: Path, group: str) -> None:
    _tree(tmp_path)
    plan = make_gold_plan(_fp(**{group: "x"}), _state(_fp()), tmp_path, MODELS, None)
    assert (plan.mode, plan.reason) == ("full", f"gold inputs changed: {group}")


def test_a_missing_output_is_a_full_build(tmp_path: Path) -> None:
    _tree(tmp_path, ["agg_a"])
    plan = make_gold_plan(_fp(), _state(_fp()), tmp_path, MODELS, None)
    assert (plan.mode, plan.reason) == ("full", "gold output missing: dim_b")


@pytest.mark.parametrize(
    ("full", "require", "whole", "reason"),
    [
        (True, False, True, "--full"),
        (False, True, True, "TRACKLAB_REQUIRE_FULL is set"),
        (False, False, False, "a subset of the gold step was selected"),
    ],
)
def test_a_forced_build_never_skips(
    tmp_path: Path, full: bool, require: bool, whole: bool, reason: str
) -> None:
    _tree(tmp_path)
    forced = full_reason(full=full, require_full=require, whole_step=whole, step="gold")
    plan = make_gold_plan(_fp(), _state(_fp()), tmp_path, MODELS, forced)
    assert (plan.mode, plan.reason) == ("full", reason)


def test_the_state_is_forgotten_before_dbt_and_written_only_after_it(tmp_path: Path) -> None:
    write_state(tmp_path, _state(_fp()), GOLD)
    write_state(tmp_path, {"version": STATE_VERSION, "marker": "silver"})
    forget_gold(tmp_path)
    assert read_state(tmp_path, GOLD) is None
    assert read_state(tmp_path) is not None, "silver's state is not gold's"
    finish_gold(_fp(), tmp_path, "run-2", whole_step=False)
    assert read_state(tmp_path, GOLD) is None, "a subset leaves no state"
    finish_gold(_fp(), tmp_path, "run-2", whole_step=True)
    assert read_state(tmp_path, GOLD) == {**_state(_fp()), "run_id": "run-2"}
    assert b"\r" not in state_path(tmp_path, GOLD).read_bytes()


# --- the step through `tracklab build` ---------------------------------------------


def _build(root: Path, **env: str) -> dict[str, Any]:
    """One `tracklab build --select group:gold` on `root`: the gold step's record, the exit code
    and how many dbt target folders the run left (then removed)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(PIPELINE)
        patch.setenv("TRACKLAB_DATA_ROOT", str(root))
        patch.delenv("TRACKLAB_REQUIRE_FULL", raising=False)
        patch.delenv(FULL_ENV, raising=False)
        for name, value in env.items():
            patch.setenv(name, value)
        before = set((root / "build").glob("*.json"))
        code = run_build("group:gold", root / "build", root, web_data_dir=root / "web")
    (path,) = set((root / "build").glob("*.json")) - before
    record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    path.unlink()
    (gold,) = record["steps"]
    targets = sorted(DBT_TARGET.glob(f"gold-{record['run_id'][:7]}-*"))
    for target in targets:
        shutil.rmtree(target, ignore_errors=True)
    return {"code": code, "gold": gold, "dbt_target_folders": len(targets)}


def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
    return {
        p.relative_to(root).as_posix(): (
            p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in sorted((root / "gold").rglob("*.parquet"))
    }


def _rewrite(path: Path, change: Any) -> None:
    pq.write_table(change(pq.read_table(path)), path, compression="zstd")


def _one_more_game(table: pa.Table) -> pa.Table:
    games = table.column("games_played").to_pylist()
    games[0] += 1
    index = table.schema.get_field_index("games_played")
    return table.set_column(index, "games_played", pa.array(games, pa.int64()))


def _games(root: Path) -> int:
    shots = (root / "gold" / "agg_bb_shots" / "data.parquet").as_posix()
    row = duckdb.sql(f"SELECT sum(games_played) FROM read_parquet('{shots}')").fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture(scope="module")
def first(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("gold") / "data"
    shutil.copytree(FIXTURES / "bronze", root / "bronze")
    run = _build(root)
    return {"root": root, "run": run, "snapshot": _snapshot(root), "games": _games(root)}


@pytest.fixture(scope="module")
def unchanged(first: dict[str, Any]) -> dict[str, Any]:
    return {"run": _build(first["root"]), "snapshot": _snapshot(first["root"])}


@pytest.fixture(scope="module")
def touched(first: dict[str, Any], unchanged: dict[str, Any]) -> dict[str, Any]:
    root: Path = first["root"]
    _rewrite(root / SHOTS, _one_more_game)
    return {"run": _build(root), "snapshot": _snapshot(root), "games": _games(root)}


@pytest.fixture(scope="module")
def required(first: dict[str, Any], touched: dict[str, Any]) -> dict[str, Any]:
    return {"run": _build(first["root"], TRACKLAB_REQUIRE_FULL="1")}


@pytest.fixture(scope="module")
def failed(first: dict[str, Any], required: dict[str, Any]) -> Iterator[dict[str, Any]]:
    root: Path = first["root"]
    good = (root / SHOTS).read_bytes()
    # The same rows twice: the unique_combination test of `agg_bb_shots` fails.
    _rewrite(root / SHOTS, lambda t: pa.concat_tables([t, t.slice(0, 5)]))
    failure = _build(root)
    remembered = read_state(root, GOLD)
    (root / SHOTS).write_bytes(good)
    yield {"failure": failure, "remembered": remembered, "after": _build(root)}


def test_a_first_run_without_state_builds_gold(first: dict[str, Any]) -> None:
    gold = first["run"]["gold"]
    assert first["run"]["code"] == 0
    assert gold["incremental"] == {
        "mode": "full",
        "reason": "no state left by a successful run of the whole step",
    }
    assert gold["dbt"]["tests"]["pass"] > 0 and gold["dbt"]["tests"]["fail"] == 0
    assert gold["dbt"]["nodes"]["success"] == 10
    assert len(first["snapshot"]) == 10


def test_nothing_changed_launches_no_dbt_and_touches_no_file(
    first: dict[str, Any], unchanged: dict[str, Any]
) -> None:
    run = unchanged["run"]
    gold = run["gold"]
    assert run["code"] == 0 and gold["status"] == "success"
    assert gold["incremental"]["mode"] == "skip"
    assert gold["incremental"]["reason"].startswith("no input changed since run ")
    assert gold["dbt"] is None and run["dbt_target_folders"] == 0
    assert gold["partitions"] == {"written": [], "skipped": [], "deleted": []}
    assert unchanged["snapshot"] == first["snapshot"]


def test_touching_aggregates_shots_rebuilds_gold(
    first: dict[str, Any], touched: dict[str, Any]
) -> None:
    gold = touched["run"]["gold"]
    assert touched["run"]["code"] == 0
    assert gold["incremental"] == {"mode": "full", "reason": "gold inputs changed: bronze"}
    assert gold["dbt"]["tests"]["fail"] == 0 and gold["dbt"]["nodes"]["success"] == 10
    shots = "gold/agg_bb_shots/data.parquet"
    assert touched["snapshot"][shots][1] != first["snapshot"][shots][1]
    assert touched["games"] == first["games"] + 1, "the changed value reached gold"


def test_require_full_never_skips(required: dict[str, Any]) -> None:
    gold = required["run"]["gold"]
    assert required["run"]["code"] == 0
    assert gold["incremental"] == {"mode": "full", "reason": "TRACKLAB_REQUIRE_FULL is set"}
    assert gold["dbt"]["tests"]["pass"] > 0


def test_a_failed_run_is_rebuilt_even_with_the_old_bronze_back(failed: dict[str, Any]) -> None:
    failure, after = failed["failure"], failed["after"]
    assert failure["code"] == 1 and failure["gold"]["status"] == "failure"
    assert failure["gold"]["dbt"]["tests"]["fail"] > 0, "the models ran, a test failed"
    assert failed["remembered"] is None, "state is written only after dbt succeeds"
    # Same bronze as the last success, outputs on disk: only the missing state can tell.
    assert after["code"] == 0
    assert after["gold"]["incremental"]["mode"] == "full"
    assert after["gold"]["dbt"]["tests"]["fail"] == 0
