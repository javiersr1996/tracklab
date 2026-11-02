"""Task 127: the plan of the incremental silver step and its state, on a hand-made silver tree.

Fast and exhaustive over the decision; `test_incremental_silver.py` runs the same decisions
through `tracklab build` on the fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tracklab.silver.incremental import (
    NO_KEY,
    STATE_VERSION,
    Fingerprints,
    Plan,
    finish,
    full_reason,
    make_plan,
    partition_dir,
    prepare,
    read_state,
    state_path,
    write_state,
)

BB, FB, FB2 = "basketball/114243", "football/1874553", "football/1925299"
DIMS = ["dim_match", "dim_sport"]
MODELS = [*DIMS, "events", "frames"]


def fingerprints(matches: dict[str, str], global_digest: str = "g") -> Fingerprints:
    return Fingerprints(global_digest, {"basketball": "s1", "football": "s2"}, matches)


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PAR1")


def silver_tree(
    data: Path, matches: list[str], models: tuple[str, ...] = ("events", "frames")
) -> None:
    (data / "tracklab.duckdb").write_bytes(b"")
    for dim in DIMS:
        _write(data / "silver" / dim / "data.parquet")
    for key in matches:
        for model in models:
            _write(partition_dir(data / "silver", model, key) / "data_0.parquet")


def state(
    matches: dict[str, str], partitions: tuple[str, ...] = ("events", "frames")
) -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "run_id": "run-1",
        "global": "g",
        "season": {"basketball": "s1", "football": "s2"},
        "matches": {
            k: {"fingerprint": v, "partitions": list(partitions)} for k, v in matches.items()
        },
    }


def test_no_state_is_a_full_build(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB])
    plan = make_plan(fingerprints({BB: "a", FB: "b"}), None, tmp_path, MODELS, None)

    assert (plan.mode, plan.written, plan.skipped) == ("full", [BB, FB], [])
    assert plan.reason == "no state left by a successful run of the whole step"
    assert plan.dbt_vars() == {}


def test_nothing_changed_is_a_skip_that_names_the_run_it_compares_with(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB])
    plan = make_plan(
        fingerprints({BB: "a", FB: "b"}), state({BB: "a", FB: "b"}), tmp_path, MODELS, None
    )

    assert plan == Plan("skip", "no input changed since run run-1", [], [BB, FB], [])


def test_one_changed_match_is_incremental_and_the_var_names_it(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB, FB2])
    now = fingerprints({BB: "a", FB: "b2", FB2: "c"})
    plan = make_plan(now, state({BB: "a", FB: "b", FB2: "c"}), tmp_path, MODELS, None)

    assert (plan.mode, plan.written, plan.skipped) == ("incremental", [FB], [BB, FB2])
    assert plan.reason == "1 of 3 matches changed"
    assert plan.dbt_vars() == {"silver_matches": {"football": [1874553]}}


def test_a_new_match_is_built_and_the_others_kept(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB])
    now = fingerprints({BB: "a", FB: "b", FB2: "c"})
    plan = make_plan(now, state({BB: "a", FB: "b"}), tmp_path, MODELS, None)

    assert (plan.mode, plan.written, plan.skipped) == ("incremental", [FB2], [BB, FB])


def test_a_partition_gone_from_disk_rebuilds_its_match(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB, FB2])
    (partition_dir(tmp_path / "silver", "frames", BB) / "data_0.parquet").unlink()
    same = {BB: "a", FB: "b", FB2: "c"}
    plan = make_plan(fingerprints(same), state(same), tmp_path, MODELS, None)

    assert (plan.mode, plan.written) == ("incremental", [BB])


def test_a_partition_the_state_never_recorded_is_not_missing(tmp_path: Path) -> None:
    """A match with no event writes no events partition: that is not a hole to fill."""
    silver_tree(tmp_path, [BB])
    silver_tree(tmp_path, [FB], models=("frames",))
    old = state({BB: "a"})
    old["matches"] |= state({FB: "b"}, partitions=("frames",))["matches"]
    plan = make_plan(fingerprints({BB: "a", FB: "b"}), old, tmp_path, MODELS, None)

    assert plan.mode == "skip"


def test_every_match_changed_is_full_and_says_why(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB])
    now = fingerprints({BB: "a2", FB: "b2"}, global_digest="g2")
    plan = make_plan(now, state({BB: "a", FB: "b"}), tmp_path, MODELS, None)

    assert (plan.mode, plan.written) == ("full", [BB, FB])
    assert plan.reason.startswith("every match changed (a global input changed")


def test_a_match_that_left_bronze_is_deleted_beside_the_ones_that_changed(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB, FB2])
    now = fingerprints({BB: "a2", FB: "b"})
    plan = make_plan(now, state({BB: "a", FB: "b", FB2: "c"}), tmp_path, MODELS, None)

    assert (plan.mode, plan.written, plan.skipped, plan.deleted) == (
        "incremental",
        [BB],
        [FB],
        [FB2],
    )


def test_a_match_that_left_bronze_alone_rebuilds_everything(tmp_path: Path) -> None:
    """The dims follow bronze; a filter keeping no match would write a partition of NULLs."""
    silver_tree(tmp_path, [BB, FB, FB2])
    plan = make_plan(
        fingerprints({BB: "a", FB: "b"}), state({BB: "a", FB: "b"}), tmp_path, MODELS, None
    )

    assert (plan.mode, plan.written, plan.deleted) == ("full", [BB, FB], [FB2])
    assert plan.reason == "1 match(es) left bronze and none changed"


@pytest.mark.parametrize(
    ("remove", "named"),
    [("silver/dim_match/data.parquet", "dim_match"), ("tracklab.duckdb", "tracklab.duckdb")],
)
def test_a_missing_output_rebuilds_everything(tmp_path: Path, remove: str, named: str) -> None:
    silver_tree(tmp_path, [BB, FB])
    (tmp_path / remove).unlink()
    same = {BB: "a", FB: "b"}
    plan = make_plan(fingerprints(same), state(same), tmp_path, MODELS, None)

    assert (plan.mode, plan.reason) == ("full", f"silver output missing: {named}")


def test_a_partition_with_no_match_key_rebuilds_everything(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB])
    junk = tmp_path / "silver" / "events" / f"sport={NO_KEY}" / f"native_match_id={NO_KEY}"
    _write(junk / "data_0.parquet")
    same = {BB: "a", FB: "b"}
    plan = make_plan(fingerprints(same), state(same), tmp_path, MODELS, None)

    assert (plan.mode, plan.reason, plan.deleted) == (
        "full",
        "a partition with no match key is on disk",
        [],
    )


@pytest.mark.parametrize(
    ("full", "require_full", "whole_step", "reason"),
    [
        (True, False, True, "--full"),
        (False, True, True, "TRACKLAB_REQUIRE_FULL is set"),
        (False, False, False, "a subset of the silver step was selected"),
        (False, False, True, None),
    ],
)
def test_full_reasons_override_the_state(
    tmp_path: Path, full: bool, require_full: bool, whole_step: bool, reason: str | None
) -> None:
    forced = full_reason(full=full, require_full=require_full, whole_step=whole_step)
    assert forced == reason
    silver_tree(tmp_path, [BB, FB])
    same = {BB: "a", FB: "b"}
    plan = make_plan(fingerprints(same), state(same), tmp_path, MODELS, forced)
    assert plan.mode == ("skip" if reason is None else "full")


def test_prepare_forgets_and_removes_only_what_it_rebuilds(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB, FB2])
    old = state({BB: "a", FB: "b", FB2: "c"})
    write_state(tmp_path, old)
    plan = Plan("incremental", "", [FB], [BB], [FB2])

    prepare(plan, old, tmp_path, ["events", "frames"])

    silver = tmp_path / "silver"
    for model in ("events", "frames"):
        assert partition_dir(silver, model, BB).is_dir()
        assert not partition_dir(silver, model, FB).exists()
        assert not partition_dir(silver, model, FB2).exists()
    remembered = read_state(tmp_path)
    assert remembered is not None and set(remembered["matches"]) == {BB}


def test_a_full_prepare_removes_every_partition_and_the_state(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB])
    old = state({BB: "a", FB: "b"})
    write_state(tmp_path, old)

    prepare(Plan("full", "--full", [BB, FB], [], []), old, tmp_path, ["frames"])

    assert list((tmp_path / "silver" / "frames").iterdir()) == []
    assert partition_dir(tmp_path / "silver", "events", BB).is_dir(), "not this run's model"
    assert not state_path(tmp_path).exists()


def test_finish_remembers_what_is_on_disk_atomically_and_in_lf(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB, FB])
    (partition_dir(tmp_path / "silver", "events", FB) / "data_0.parquet").unlink()

    finish(fingerprints({BB: "a", FB: "b"}), tmp_path, "run-2", whole_step=True)

    raw = state_path(tmp_path).read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"}\n")
    assert not state_path(tmp_path).with_name("silver.json.tmp").exists()
    written = json.loads(raw)
    assert written["run_id"] == "run-2"
    assert written["matches"] == {
        BB: {"fingerprint": "a", "partitions": ["events", "frames"]},
        FB: {"fingerprint": "b", "partitions": ["frames"]},
    }


def test_a_subset_leaves_no_state(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB])
    finish(fingerprints({BB: "a"}), tmp_path, "run-2", whole_step=False)
    assert not state_path(tmp_path).exists()


def test_finish_refuses_a_partition_with_no_match_key(tmp_path: Path) -> None:
    silver_tree(tmp_path, [BB])
    _write(
        tmp_path
        / "silver"
        / "frames"
        / f"sport={NO_KEY}"
        / f"native_match_id={NO_KEY}"
        / "d.parquet"
    )
    with pytest.raises(RuntimeError, match="no match key"):
        finish(fingerprints({BB: "a"}), tmp_path, "run-2", whole_step=True)
    assert not state_path(tmp_path).exists()


@pytest.mark.parametrize("text", ["not json", '{"version": 999, "matches": {}}', "[]"])
def test_a_state_that_cannot_be_trusted_is_no_state(tmp_path: Path, text: str) -> None:
    state_path(tmp_path).parent.mkdir(parents=True)
    state_path(tmp_path).write_text(text, encoding="utf-8")
    assert read_state(tmp_path) is None
