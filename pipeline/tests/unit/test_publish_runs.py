"""`tracklab publish runs` (task 52): the published `runs.json` and the hook's clips.

What these tests hold:

* every figure of `runs.json` is one of the reports (`pipeline/reports`): the document is
  loaded and compared with the reports leaf by leaf, not with itself, and no number outside the
  hook is absent from the reports;
* the label that promises a criterion (`dead_at`) is derived from the stages, and changes when
  the artefact does;
* the hook is picked by rule from the pairs, never by maximum; the clips are P1 clips;
* the held-out half appears only as counts;
* `--check` fails on a figure edited in `runs.json` and on a clip edited on disk.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from tracklab.publish import runs as publish_runs
from tracklab.publish.runs import (
    HOOK_RULE,
    RunsPublishError,
    choose_pair,
    dead_at,
    figures,
    hook_subtype,
    run_publish_runs,
)
from tracklab.runs.windows import PairEffect

REPO = Path(__file__).resolve().parents[3]
REPORTS = REPO / "pipeline" / "reports"
WEB_DATA = REPO / "web" / "public" / "data"
RUNS_SCHEMA = REPO / "web" / "lib" / "runs" / "schema.json"
REPLAY_SCHEMA = REPO / "web" / "lib" / "replay" / "schema.json"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _leaves(value: Any, path: str = "") -> dict[str, Any]:
    """Every scalar of a JSON value by its path."""
    if isinstance(value, dict):
        return {
            k: v for key, item in value.items() for k, v in _leaves(item, f"{path}/{key}").items()
        }
    if isinstance(value, list):
        return {
            k: v for i, item in enumerate(value) for k, v in _leaves(item, f"{path}/{i}").items()
        }
    return {path: value}


def _differences(published: Any, report: Any) -> list[str]:
    a, b = _leaves(published), _leaves(report)
    return sorted(p for p in a.keys() | b.keys() if a.get(p, "<absent>") != b.get(p, "<absent>"))


def _numbers(value: Any) -> set[float]:
    return {
        float(v)
        for v in _leaves(value).values()
        if isinstance(v, int | float) and not isinstance(v, bool)
    }


def _without_modal_rows(subtypes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The published subtypes as the report holds them: the modal-class effect's rows are the
    ones the publisher joins from `by_class`, the one thing the document adds to the section."""
    out = copy.deepcopy(subtypes)
    for subtype in out:
        modal = subtype["class_at_tc"]["modal_class_effect"]
        if modal is not None:
            del modal["per_match"]
    return out


def _aggregates_without_rows(node: Any, path: str, rows: Any = None) -> list[str]:
    """Paths of the aggregates under `node` that have no per-match rows: a `pooled` block
    whose parent has no `per_match`, and any other block of `pairs` and `mean_m` (not itself a
    row) that has none of its own."""
    if isinstance(node, list):
        return [
            p for i, item in enumerate(node) for p in _aggregates_without_rows(item, f"{path}/{i}")
        ]
    if not isinstance(node, dict):
        return []
    found: list[str] = []
    own = node.get("per_match")
    is_aggregate = "match_id" not in node and "pairs" in node and "mean_m" in node
    if is_aggregate and not own and not rows:
        found.append(path)
    for key, item in node.items():
        if key == "pooled" and not own:
            found.append(f"{path}/pooled")
        found += _aggregates_without_rows(item, f"{path}/{key}", own if key == "pooled" else None)
    return found


@pytest.fixture(scope="module")
def published() -> dict[str, Any]:
    return _json(WEB_DATA / "runs.json")  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def protocol() -> dict[str, Any]:
    return _json(REPORTS / "runs_protocol.json")  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def calibration() -> dict[str, Any]:
    return _json(REPORTS / "runs_calibration.json")  # type: ignore[no-any-return]


# --- the schema -------------------------------------------------------------------------------


def test_runs_json_validates_against_its_schema(published: dict[str, Any]) -> None:
    schema = _json(RUNS_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(published))
    assert [e.message for e in errors[:3]] == []


def test_the_schema_refuses_an_alive_status_and_an_unknown_key(published: dict[str, Any]) -> None:
    validator = Draft202012Validator(_json(RUNS_SCHEMA))
    assert not validator.is_valid({**published, "status": "alive"})
    assert not validator.is_valid({**published, "ranking": []})
    no_hook = {k: v for k, v in published.items() if k != "hook"}
    assert not validator.is_valid(no_hook)


ALIVE_FIXTURE = REPO / "web" / "e2e" / "fixtures" / "runs.alive.json"


def test_the_schema_ties_dead_at_to_the_status(published: dict[str, Any]) -> None:
    validator = Draft202012Validator(_json(RUNS_SCHEMA))
    assert not validator.is_valid({**published, "dead_at": None})  # dead says where
    assert not validator.is_valid({**published, "status": "alive"})  # alive says nowhere
    alive = {**published, "status": "alive", "dead_at": None}
    assert validator.is_valid(alive)


def test_the_alive_fixture_of_the_e2e_validates_and_differs_only_where_it_declares(
    published: dict[str, Any],
) -> None:
    """`/runs` is tested on both branches; the alive document of task 51 does not exist, so the
    fixture is the dead file with the five fields that make it alive, nothing else."""
    fixture = _json(ALIVE_FIXTURE)
    assert list(Draft202012Validator(_json(RUNS_SCHEMA)).iter_errors(fixture)) == []
    assert _differences(fixture, published) == [
        "/dead_at",
        "/never_opened/opened",
        "/stages/M5a/figures/candidates",
        "/stages/M5a/state",
        "/stages/M5b/figures/died_at",
        "/stages/M5b/state",
        "/status",
    ]


def test_both_clips_validate_against_the_replay_schema_of_p1(published: dict[str, Any]) -> None:
    validator = Draft202012Validator(_json(REPLAY_SCHEMA))
    clips = published["hook"]["clips"]
    assert [c["role"] for c in clips] == ["run", "placebo"]
    for entry in clips:
        payload = _json(WEB_DATA / entry["file"])
        assert [e.message for e in list(validator.iter_errors(payload))[:3]] == []


# --- every figure is the reports' ---------------------------------------------------------------


def test_each_section_of_runs_json_equals_its_place_in_the_reports(
    published: dict[str, Any], protocol: dict[str, Any], calibration: dict[str, Any]
) -> None:
    probe, effect = calibration["probe"], calibration["effect"]
    pairs = [
        (published["funnel"]["probe"], probe["funnel"]),
        (_without_modal_rows(published["effect_by_subtype"]), effect["per_subtype"]),
        (published["instrument"], probe["instrument"]),
        (published["power"], probe["power"]),
        (published["null"], probe["null"]),
        (
            published["post_hoc_kinematics"],
            {"label": "post hoc", **effect["kinematics"]},
        ),
        (published["design_checks"]["cadence"], probe["cadence"]),
        (published["design_checks"]["run_length"], probe["run_length"]),
        (published["design_checks"]["placebo_design"], probe["placebo_design"]),
        (published["design_checks"]["units"], probe["units"]),
        (published["design_checks"]["standardisation"], probe["standardisation"]),
        (published["protocol"]["history"], protocol["history"]),
        (published["protocol"]["bar"], protocol["design"]["bar"]),
        (published["protocol"]["quantities"], protocol["design"]["quantities"]),
        (published["protocol"]["windows"], protocol["design"]["windows"]),
        (published["never_opened"]["match_ids"], protocol["design"]["split"]["held_out"]),
    ]
    for got, expected in pairs:
        assert _differences(got, expected) == []


def test_every_aggregate_effect_is_published_with_its_rows_per_match(
    published: dict[str, Any], calibration: dict[str, Any]
) -> None:
    """Review of task 54: the modal-class effect lost its rows and the in/outside split never
    had any. Checked on the file and on what the code writes, so a publisher that drops the
    join fails even while the file on disk is stale."""
    matches = calibration["effect"]["matches"]
    for document in (published, figures(REPORTS)):
        section = {"effect_by_subtype": document["effect_by_subtype"]}
        assert _aggregates_without_rows(section, "") == []
        for subtype in document["effect_by_subtype"]:
            at_tc = subtype["class_at_tc"]
            for part in (
                "modal_class_effect",
                "subtype_pairs_in_modal_class",
                "subtype_pairs_outside_modal_class",
            ):
                rows = at_tc[part]["per_match"]
                assert [r["match_id"] for r in rows] == matches
                assert sum(r["pairs"] for r in rows) == at_tc[part]["pairs"]


def test_the_modal_class_rows_are_the_reports_by_class_rows(
    published: dict[str, Any], calibration: dict[str, Any]
) -> None:
    by_class = {r["class"]: r for r in calibration["effect"]["class_at_tc"]["by_class"]}
    for subtype in published["effect_by_subtype"]:
        at_tc = subtype["class_at_tc"]
        assert (
            at_tc["modal_class_effect"]["per_match"] == by_class[at_tc["modal_class"]]["per_match"]
        )


def test_the_stages_carry_the_reports_figures_and_the_protocols_rules(
    published: dict[str, Any], protocol: dict[str, Any], calibration: dict[str, Any]
) -> None:
    probe, effect = calibration["probe"], calibration["effect"]
    stages = published["stages"]
    rules = protocol["design"]["death_criteria"]
    assert {k: v["rule"] for k, v in stages.items()} == {k: rules[k] for k in stages}
    m1 = probe["verdict"]["M1"]
    for key in ("primary_quantity", "probable_subtypes", "probable_by_line", "needs_at_least"):
        assert stages["M1"]["figures"][key] == m1[key]
    assert stages["M1"]["figures"]["probable"] == probe["power"]["probable"]
    assert stages["M2"]["figures"]["instrument"] == probe["instrument"]["marker"]["pooled"]
    for stage in ("M3", "M4"):
        rows = stages[stage]["figures"]["subtypes"]
        assert [r["subtype"] for r in rows] == [s["subtype"] for s in effect["per_subtype"]]
        for row, subtype in zip(rows, effect["per_subtype"], strict=True):
            assert {k: v for k, v in row.items() if k != "subtype"} == subtype["verdict"][stage]
    for stage in ("M3", "M4"):
        n = sum(s["verdict"][stage]["leaves"] for s in effect["per_subtype"])
        expected = {0: "no_subtype_leaves", len(effect["per_subtype"]): "all_subtypes_leave"}
        assert stages[stage]["state"] == expected.get(n, "some_subtypes_leave")
    assert stages["M5a"]["figures"]["candidates"] == len(effect["candidates"])
    assert (stages["M1"]["state"], stages["M2"]["state"]) == ("passed", "passed")
    assert (stages["M5a"]["state"], stages["M5b"]["state"]) == ("dead", "not_reached")
    assert published["dead_at"] == "M5a"


def test_the_coverage_rows_are_the_csv_cell_by_cell(published: dict[str, Any]) -> None:
    with (REPORTS / "runs_coverage.csv").open(encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    rows = published["funnel"]["coverage"]
    assert len(rows) == len(raw) == 20
    for row, cells in zip(rows, raw, strict=True):
        assert list(row) == list(cells)
        for column, cell in cells.items():
            assert row[column] == (cell if column == "half" else float(cell))


def test_the_protocol_block_is_the_protocols_only_stage(
    published: dict[str, Any], protocol: dict[str, Any], calibration: dict[str, Any]
) -> None:
    block = published["protocol"]
    assert block["stage"] == protocol["stage"] == "design"
    assert block["stages_seen"] == ["design"]
    assert block["frozen"] is False and "frozen" not in protocol
    assert block["fingerprint"] == protocol["fingerprint"]
    assert block["content_sha256"] == protocol["content_sha256"]
    assert block["calibration_sha256"] == calibration["content_sha256"]


def test_no_number_outside_the_hook_is_missing_from_the_reports(
    published: dict[str, Any], protocol: dict[str, Any], calibration: dict[str, Any]
) -> None:
    """A figure typed into the publisher would show here: every number of the document,
    the hook apart, is a number some report holds."""
    with (REPORTS / "runs_coverage.csv").open(encoding="utf-8", newline="") as handle:
        coverage = [
            [float(v) if v != "calibration" and v != "held_out" else 0 for v in r.values()]
            for r in csv.DictReader(handle)
        ]
    known = _numbers(protocol) | _numbers(calibration) | _numbers(coverage)
    body = {k: v for k, v in published.items() if k != "hook"}
    unknown = sorted(n for n in _numbers(body) if n not in known)
    assert unknown == []


# --- dead_at is derived -----------------------------------------------------------------------


def _reports_copy(tmp_path: Path) -> Path:
    target = tmp_path / "reports"
    target.mkdir(parents=True)
    for name in ("runs_protocol.json", "runs_calibration.json", "runs_coverage.csv"):
        shutil.copy(REPORTS / name, target / name)
    return target


def _edit_calibration(reports: Path, edit: Any) -> None:
    path = reports / "runs_calibration.json"
    data = _json(path)
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_dead_at_follows_the_stage_that_died(tmp_path: Path) -> None:
    reports = _reports_copy(tmp_path)
    assert figures(reports)["dead_at"] == "M5a"
    _edit_calibration(reports, lambda d: d["probe"]["verdict"]["M2"].update(dies=True))
    assert figures(reports)["dead_at"] == "M2"
    _edit_calibration(reports, lambda d: d["probe"]["verdict"]["M1"].update(dies=True))
    assert figures(reports)["dead_at"] == "M1"


def test_nothing_is_published_for_an_alive_artefact_or_one_without_the_effect(
    tmp_path: Path,
) -> None:
    reports = _reports_copy(tmp_path)
    _edit_calibration(reports, lambda d: d["effect"]["verdict"]["M5a"].update(dies=False))
    with pytest.raises(RunsPublishError, match="alive branch"):
        figures(reports)
    reports = _reports_copy(tmp_path / "second")
    _edit_calibration(reports, lambda d: d.pop("effect"))
    with pytest.raises(RunsPublishError, match="no effect section"):
        figures(reports)


def test_the_post_hoc_label_needs_the_report_to_say_post_hoc(tmp_path: Path) -> None:
    reports = _reports_copy(tmp_path)
    _edit_calibration(reports, lambda d: d["effect"]["kinematics"].update(post_hoc=False))
    with pytest.raises(RunsPublishError, match="post hoc"):
        figures(reports)


def test_a_calibration_file_of_another_protocol_is_refused(tmp_path: Path) -> None:
    reports = _reports_copy(tmp_path)
    _edit_calibration(reports, lambda d: d["protocol"].update(fingerprint="0" * 64))
    with pytest.raises(RunsPublishError, match="fingerprint"):
        figures(reports)


def test_two_builds_of_the_figures_have_the_same_bytes() -> None:
    assert publish_runs.render(figures(REPORTS)) == publish_runs.render(figures(REPORTS))


# --- the held-out half is counts -----------------------------------------------------------------


def test_the_held_out_half_appears_only_as_counts(
    published: dict[str, Any], protocol: dict[str, Any]
) -> None:
    held = set(protocol["design"]["split"]["held_out"])
    assert published["never_opened"]["opened"] is False
    with (REPORTS / "runs_coverage.csv").open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    for row in published["never_opened"]["counts"]:
        assert row["match_id"] in held and row["half"] == "held_out"
        assert set(row) <= set(header)
    counts_only = {"funnel", "never_opened"}

    def walk(value: Any, path: tuple[str, ...]) -> list[str]:
        found = []
        if isinstance(value, dict):
            if value.get("match_id") in held and path[:1] and path[0] not in counts_only:
                found.append("/".join(path))
            for key, item in value.items():
                found += walk(item, (*path, key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                found += walk(item, (*path, str(i)))
        return found

    assert walk(published, ()) == []
    for row in published["funnel"]["probe"]["per_match"]:
        if row["match_id"] in held:
            assert set(row) == {"match_id", "half", "runs", "pairs", "pairs_by_subtype"}
    assert published["hook"]["pair"]["match_id"] not in held


# --- the hook: a rule, never a maximum ----------------------------------------------------------


def _pair(match_id: int, run_id: str, marker_m: float) -> PairEffect:
    return PairEffect(
        match_id=match_id,
        run_id=run_id,
        possession_id=None,
        subtype="run_ahead_of_the_ball",
        player_id=1,
        t_c=100,
        placebo_period=1,
        placebo_instant=50,
        marker_m=marker_m,
        line_m=0.0,
        placebo_marker_m=0.0,
        placebo_line_m=0.0,
    )


def test_the_hook_pair_is_the_one_closest_to_the_median_and_not_the_largest() -> None:
    pairs = [
        _pair(1, "a", -0.5),
        _pair(1, "b", 1.0),
        _pair(2, "a", 1.5),
        _pair(2, "b", 1.8),
        _pair(3, "a", 5.0),
    ]
    median = float(np.median([p.marker_m for p in pairs]))
    assert median == 1.5
    chosen = choose_pair(pairs, median)
    assert (chosen.match_id, chosen.run_id) == (2, "a")
    assert chosen.marker_m != max(p.marker_m for p in pairs)


def test_equal_distances_go_to_the_lowest_match_and_run_id() -> None:
    pairs = [_pair(2, "a", 1.5), _pair(1, "z", 0.5), _pair(1, "b", 0.5), _pair(3, "a", 1.5)]
    chosen = choose_pair(pairs, 1.0)
    assert (chosen.match_id, chosen.run_id) == (1, "b")
    assert choose_pair(list(reversed(pairs)), 1.0) == chosen


def test_choosing_from_nothing_is_an_error() -> None:
    with pytest.raises(RunsPublishError):
        choose_pair([], 0.0)


def test_the_hook_subtype_is_the_largest_that_passed_the_bar(calibration: dict[str, Any]) -> None:
    effect = copy.deepcopy(calibration["effect"])
    sizes = {s["subtype"]: (s["pairs"], s["verdict"]["passes_bar"]) for s in effect["per_subtype"]}
    assert hook_subtype(effect) == "run_ahead_of_the_ball"
    assert sizes["run_ahead_of_the_ball"][0] == max(n for n, ok in sizes.values() if ok)
    for s in effect["per_subtype"]:
        if s["subtype"] == "run_ahead_of_the_ball":
            s["verdict"]["passes_bar"] = False
    assert hook_subtype(effect) == "support"  # the next largest that passed
    for s in effect["per_subtype"]:
        s["verdict"]["passes_bar"] = False
    with pytest.raises(RunsPublishError):
        hook_subtype(effect)


def test_the_published_hook_is_the_rules_pair_in_the_reports_subtype(
    published: dict[str, Any], calibration: dict[str, Any]
) -> None:
    hook = published["hook"]
    section = next(
        s for s in calibration["effect"]["per_subtype"] if s["subtype"] == hook["subtype"]
    )
    assert hook["rule"] == HOOK_RULE
    assert hook["subtype"] == hook_subtype(calibration["effect"])
    assert hook["subtype_pairs"] == section["pairs"]
    assert hook["subtype_mean_marker_m"] == section["marker"]["pooled"]["mean_m"]
    pair = hook["pair"]
    assert abs(pair["marker_effect_m"] - hook["subtype_median_marker_m"]) == pytest.approx(
        pair["distance_to_median_m"], abs=2e-4
    )
    # not the extreme of the subtype: it sits inside the per-match range of the reported means
    per_match = [m["mean_m"] for m in section["marker"]["per_match"]]
    assert min(per_match) < pair["marker_effect_m"] < max(per_match)
    assert pair["marker_effect_m"] < 2 * section["marker"]["pooled"]["mean_m"]


def test_the_clips_cover_both_windows_around_their_instant(published: dict[str, Any]) -> None:
    for entry in published["hook"]["clips"]:
        payload = _json(WEB_DATA / entry["file"])
        assert (entry["frame_lo"], entry["frame_hi"]) == (
            entry["instant_frame"] - 20,
            entry["instant_frame"] + 20,
        )
        assert entry["window_s"] == [-2.0, 2.0]
        assert len(payload["frames"]) == entry["frames"] == 41
        step = payload["frames"][1]["t"] - payload["frames"][0]["t"]
        index = entry["instant_index"]
        assert payload["frames"][index]["t"] - payload["frames"][0]["t"] == index * step
        assert (payload["frames"][-1]["t"] - payload["frames"][index]["t"]) == 20 * step
        marker = next(d for d in entry["defence"] if d["is_marker"])
        assert marker["entity_id"] == entry["marker_entity_id"]
        assert marker["displacement_m"] == entry["marker_displacement_m"]
        assert sum(d["is_marker"] for d in entry["defence"]) == 1
    run, placebo = published["hook"]["clips"]
    assert run["marker_displacement_m"] - placebo["marker_displacement_m"] == pytest.approx(
        published["hook"]["pair"]["marker_effect_m"], abs=2e-4
    )


def test_the_clips_are_below_p1s_cap_and_match_their_hashes(published: dict[str, Any]) -> None:
    for entry in published["hook"]["clips"]:
        data = (WEB_DATA / entry["file"]).read_bytes()
        assert len(data) == entry["bytes"] < publish_runs.MAX_CLIP_BYTES
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert b"\r" not in data
    assert b"\r" not in (WEB_DATA / "runs.json").read_bytes()
    on_disk = sorted(p.name for p in (WEB_DATA / "runs").glob("*.json"))
    assert on_disk == sorted(Path(e["file"]).name for e in published["hook"]["clips"])


# --- --check ------------------------------------------------------------------------------------


def _web_copy(tmp_path: Path) -> Path:
    out = tmp_path / "web"
    out.mkdir()
    shutil.copy(WEB_DATA / "runs.json", out / "runs.json")
    shutil.copytree(WEB_DATA / "runs", out / "runs")
    return out


def test_check_passes_on_the_versioned_files_without_frames(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    nowhere = tmp_path / "no-data"
    assert run_publish_runs(nowhere, REPORTS, WEB_DATA, check=True) == 0
    assert "PARTIAL" in capsys.readouterr().out


def test_check_fails_when_a_figure_of_runs_json_is_edited(tmp_path: Path) -> None:
    out = _web_copy(tmp_path)
    data = _json(out / "runs.json")
    data["effect_by_subtype"][1]["marker"]["pooled"]["mean_m"] += 0.0001
    (out / "runs.json").write_text(publish_runs.render(data), encoding="utf-8", newline="\n")
    assert run_publish_runs(tmp_path / "no-data", REPORTS, out, check=True) == 1


def test_check_fails_when_a_clip_or_the_directory_changes(tmp_path: Path) -> None:
    out = _web_copy(tmp_path)
    clip = next((out / "runs").glob("*.json"))
    original = clip.read_bytes()
    clip.write_bytes(original.replace(b"fb:", b"fc:", 1))
    assert run_publish_runs(tmp_path / "no-data", REPORTS, out, check=True) == 1
    clip.write_bytes(original)
    assert run_publish_runs(tmp_path / "no-data", REPORTS, out, check=True) == 0
    (out / "runs" / "stray.json").write_text("{}", encoding="utf-8")
    assert run_publish_runs(tmp_path / "no-data", REPORTS, out, check=True) == 1


def test_check_fails_when_runs_json_is_missing(tmp_path: Path) -> None:
    assert run_publish_runs(tmp_path / "no-data", REPORTS, tmp_path, check=True) == 1


def test_the_first_dead_stage_wins_when_a_later_one_died_too(tmp_path: Path) -> None:
    reports = _reports_copy(tmp_path)
    _edit_calibration(reports, lambda d: d["probe"]["verdict"]["M2"].update(dies=True))
    assert dead_at(figures(reports)["stages"]) == "M2"  # M5a also died: the first one wins
