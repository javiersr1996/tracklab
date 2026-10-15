"""`tracklab publish pose`, second version (task 62): `pose.json` and the clips of the two
whole matches.

What these tests hold:

* the rule that picks the hook window (nearest to the median cadence, ties to (player_id,
  frame), never the maximum) and the stretch of most skeletons, on synthetic windows and tables;
* the status read from the reports (`alive`, `unreplicated`, `dead` at noise, M1, M2 or M4);
* `pose.json`: every number it holds is one a report holds (nothing typed), its limits are the
  README's text and line (the fixture of task 57), it is valid, and `serves_query` leaves it and
  the clips to watch;
* `--check`: PARTIAL on fixtures, a failure when a clip, the summary or the cap disagree;
* the real bronze (skipped without it): the hook of 1925299 against an independent median, the
  dead branch end to end, and the bronze path against the sample's clip.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tracklab.build import measure_publish, serves_query
from tracklab.paths import data_root
from tracklab.pose import gait
from tracklab.pose.verdict import Window
from tracklab.publish import pose as publish_pose
from tracklab.publish import pose_hook, pose_summary
from tracklab.publish.pose import CLIP_FILE, LIMITS, SUMMARY_FILE, run_publish_pose

REPO = Path(__file__).resolve().parents[3]
WEB_DATA = REPO / "web" / "public" / "data"
REPORTS = REPO / "pipeline" / "reports"
SCHEMA = REPO / "web" / "lib" / "pose" / "schema.json"
SUMMARY_SCHEMA = REPO / "web" / "lib" / "pose" / "summary.schema.json"
MANIFEST = REPO / "pipeline" / "manifest" / "sources.json"
README_FIXTURE = REPO / "pipeline" / "tests" / "fixtures" / "bodypose" / "README.hf.md"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _reports() -> dict[str, Any]:
    return pose_summary.load_reports(REPORTS)


def _window(player: int, frame: int, cad: float, band: str = "high") -> Window:
    g = gait.Gait(cad, math.nan, 0.7, 1.7, 6.0)
    return Window(player, 1, frame, band, 6.0, 10.0, g, 0.0, None)


# --- the rule of the hook ----------------------------------------------------------------


def test_the_hook_is_the_window_nearest_to_the_median_cadence_and_never_the_maximum() -> None:
    windows = [_window(1, i, c) for i, c in enumerate([3.0, 3.4, 3.5, 3.6, 4.5])]
    assert pose_hook.high_median_hz(windows) == 3.5
    chosen = pose_hook.choose_hook(windows)
    assert chosen.estimate.cadence_hz == 3.5
    assert chosen.estimate.cadence_hz != max(w.estimate.cadence_hz for w in windows)


def test_a_tie_goes_to_the_smaller_player_and_then_the_smaller_frame() -> None:
    cadences = [3.0, 3.25, 3.75, 4.0]  # median 3.5; 3.25 and 3.75 are both 0.25 away
    near = [_window(2, 10, 3.25), _window(1, 99, 3.75)]
    rest = [_window(5, 1, 3.0), _window(5, 2, 4.0)]
    for order in (near + rest, near[::-1] + rest, rest + near):
        assert pose_hook.high_median_hz(order) == 3.5
        chosen = pose_hook.choose_hook(order)
        assert (chosen.player_id, chosen.frame) == (1, 99)
    same = [_window(1, 50, 3.25), _window(1, 40, 3.75)] + [_window(9, 1, c) for c in (3.0, 4.0)]
    assert cadences and pose_hook.choose_hook(same).frame == 40


def test_low_windows_and_windows_without_a_cadence_are_not_candidates() -> None:
    windows = [
        _window(1, 1, 3.5, band="low"),
        _window(1, 2, math.nan),
        _window(2, 3, 3.0),
        _window(2, 4, 4.0),
    ]
    assert pose_hook.high_median_hz(windows) == 3.5
    assert pose_hook.choose_hook(windows).frame == 3  # 3.0 and 4.0 tie; the smaller frame
    with pytest.raises(publish_pose.PosePublishError):
        pose_hook.high_median_hz([_window(1, 1, 3.5, band="low")])


def _table(
    periods: list[int | None], skeletons: list[int], first: int = 1000
) -> pose_hook.FrameTable:
    n = len(periods)
    return pose_hook.FrameTable(
        np.arange(first, first + n, dtype=np.int64),
        periods,
        np.full(n, 22, dtype=np.int64),
        np.array(skeletons, dtype=np.int64),
        [(0.0, 0.0, True)] * n,
    )


def test_the_clip_holds_the_window_and_stays_inside_its_period() -> None:
    table = _table([1] * 300 + [2] * 300, [10] * 600)
    for first in (1000, 1010, 1100, 1240, 1249, 1300, 1549):
        period = 1 if first < 1300 else 2
        lo, hi = pose_hook.clip_range(first, 50, table, period)
        p_lo, p_hi = (1000, 1299) if period == 1 else (1300, 1599)
        assert hi - lo + 1 == pose_hook.CLIP_FRAMES
        assert p_lo <= lo and hi <= p_hi
        assert lo <= first and first + 49 <= hi
    assert pose_hook.clip_range(1100, 50, table, 1) == (1075, 1174)  # PRE frames before
    assert pose_hook.clip_range(1000, 50, table, 1) == (1000, 1099)  # moved into the period


def test_the_stretch_has_most_skeletons_never_crosses_a_period_and_ties_to_the_first_frame() -> (
    None
):
    skeletons = [1] * 120 + [9] * 100 + [1] * 120 + [9] * 100 + [1] * 60
    table = _table([1] * 240 + [2] * 260, skeletons)
    assert pose_hook.choose_stretch(table) == (1120, 1219)  # the first of two equal stretches
    crossing = _table([1] * 150 + [2] * 150, [1] * 100 + [9] * 100 + [1] * 100)
    lo, hi = pose_hook.choose_stretch(crossing)
    periods = {crossing.period[i] for i in range(lo - 1000, hi - 1000 + 1)}
    assert len(periods) == 1
    with pytest.raises(publish_pose.PosePublishError):
        pose_hook.choose_stretch(_table([1] * 99, [5] * 99))


def test_a_frame_table_with_a_hole_is_refused() -> None:
    with pytest.raises(publish_pose.PosePublishError, match="consecutive"):
        pose_hook.FrameTable(
            np.array([1, 2, 4], dtype=np.int64),
            [1, 1, 1],
            np.array([22] * 3, dtype=np.int64),
            np.array([5] * 3, dtype=np.int64),
            [None] * 3,
        )


# --- the status ---------------------------------------------------------------------------


def _dead_noise(r: dict[str, Any]) -> None:
    r["calibration"]["rule_w_cap"]["chosen"] = None


def _dead_m1(r: dict[str, Any]) -> None:
    r["verdict"]["verdict"]["dies_at"] = "m1"


def _dead_m2(r: dict[str, Any]) -> None:
    r["verdict"]["verdict"]["dies_at"] = "m2_precision"


def _dead_m4(r: dict[str, Any]) -> None:
    r["metric"]["verdicts"]["p6"] = "replication_failed"


def _unreplicated(r: dict[str, Any]) -> None:
    r["metric"]["verdicts"]["p6"] = "unreplicated"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda r: None, ("alive", None)),
        (_dead_noise, ("dead", "noise")),
        (_dead_m1, ("dead", "M1")),
        (_dead_m2, ("dead", "M2")),
        (_dead_m4, ("dead", "M4")),
        (_unreplicated, ("unreplicated", None)),
    ],
)
def test_the_status_follows_the_reports(mutate: Any, expected: tuple[str, str | None]) -> None:
    reports = copy.deepcopy(_reports())
    mutate(reports)
    assert pose_summary.status_of(reports) == expected


def test_the_committed_state_is_the_one_the_metric_says() -> None:
    reports = _reports()
    assert pose_summary.status_of(reports) == ("alive", None)
    assert reports["metric"]["verdicts"]["p6"] == "alive"


def test_the_matches_that_may_open_depend_on_the_state() -> None:
    reports = _reports()
    both = pose_hook.matches_to_clip(reports, "alive", None)
    assert len(both) == 2 and both[0] != both[1]
    assert pose_hook.matches_to_clip(reports, "unreplicated", None) == both
    assert pose_hook.matches_to_clip(reports, "dead", "M4") == both
    for dead_at in ("noise", "M1", "M2"):
        assert pose_hook.matches_to_clip(reports, "dead", dead_at) == both[:1]


def test_a_dead_summary_has_no_tables_and_a_live_one_has_them() -> None:
    reports = copy.deepcopy(_reports())
    clips = _json(WEB_DATA / SUMMARY_FILE)["clips"]
    live = pose_summary.build_summary(reports, clips)
    assert live["tables"] is not None and live["status"] == "alive"
    _dead_m4(reports)
    dead = pose_summary.build_summary(reports, clips)
    assert dead["tables"] is None and (dead["status"], dead["dead_at"]) == ("dead", "M4")
    _unreplicated(reports)
    assert pose_summary.build_summary(reports, clips)["tables"] is not None


def test_no_confirmation_metric_means_the_confirmation_match_was_not_opened() -> None:
    reports = copy.deepcopy(_reports())
    assert pose_summary.build_summary(reports, [])["opened"]["not_opened"] == []
    del reports["metric"]
    _dead_m1(reports)
    opened = pose_summary.build_summary(reports, [])["opened"]
    assert opened["confirmation_match_opened"] is False
    assert opened["not_opened"] == [reports["protocol"]["design"]["split"]["confirmation"][0]]


# --- pose.json ------------------------------------------------------------------------------


def _numbers(value: Any) -> set[float]:
    if isinstance(value, bool):
        return set()
    if isinstance(value, int | float):
        return {float(value)}
    if isinstance(value, dict):
        return set().union(*(_numbers(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_numbers(v) for v in value))
    return set()


def _from_no_report(summary: dict[str, Any], reports: dict[str, Any]) -> set[float]:
    held = _numbers(reports)
    return _numbers({k: v for k, v in summary.items() if k != "clips"}) - held


def test_every_number_of_pose_json_is_one_a_report_holds() -> None:
    summary = _json(WEB_DATA / SUMMARY_FILE)
    assert _numbers(summary["tables"])  # the walk reaches the tables
    assert _from_no_report(summary, _reports()) == set()


def test_a_typed_number_is_caught() -> None:
    summary = _json(WEB_DATA / SUMMARY_FILE)
    summary["coverage"]["1925299"]["total"]["frames"] += 1
    assert _from_no_report(summary, _reports()) != set()
    summary = _json(WEB_DATA / SUMMARY_FILE)
    summary["tables"]["matches"]["1925299"][0][5] += 1000
    assert _from_no_report(summary, _reports()) != set()


def test_pose_json_is_what_the_reports_and_its_clips_give() -> None:
    summary = _json(WEB_DATA / SUMMARY_FILE)
    rebuilt = pose_summary.build_summary(_reports(), summary["clips"])
    assert rebuilt == summary
    metric = _reports()["metric"]
    for match, rows in summary["tables"]["matches"].items():
        assert rows == metric["matches"][match]
        assert all(row[5] >= 1 for row in rows), "a row without its denominator"
    assert summary["tables"]["columns"] == metric["columns"]


def test_pose_json_validates_and_the_schema_refuses_damage() -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(_json(SUMMARY_SCHEMA))
    summary = _json(WEB_DATA / SUMMARY_FILE)
    assert list(validator.iter_errors(summary)) == []
    for damage in (
        lambda s: s.update(status="zombie"),
        lambda s: s.update(dead_at="M3"),
        lambda s: s.update(tables=None),  # alive without tables
        lambda s: s["limits"].pop(),
        lambda s: s["clips"][0].update(file="../x.json"),
    ):
        broken = copy.deepcopy(summary)
        damage(broken)
        assert list(validator.iter_errors(broken)), damage


def test_the_clips_are_the_files_pose_json_names() -> None:
    summary = _json(WEB_DATA / SUMMARY_FILE)
    cap = _reports()["clip"]["clip"]["bytes"]
    files = {p.name for p in (WEB_DATA / "pose").glob("*.json")}
    assert files == {Path(CLIP_FILE).name, *(Path(c["file"]).name for c in summary["clips"])}
    for record in summary["clips"]:
        data = (WEB_DATA / record["file"]).read_bytes()
        assert (len(data), hashlib.sha256(data).hexdigest()) == (record["bytes"], record["sha256"])
        assert len(data) <= cap
        clip = json.loads(data)
        assert clip["selection"]["kind"] == record["kind"]
        assert clip["coverage"] == record["coverage"]
        assert (clip["frame_hi"] - clip["frame_lo"] + 1) == pose_hook.CLIP_FRAMES


def test_a_hook_clip_carries_the_window_with_its_signal_and_never_a_null_skeleton() -> None:
    summary = _json(WEB_DATA / SUMMARY_FILE)
    width = summary["protocol"]["width"]
    for record in summary["clips"]:
        clip = json.loads((WEB_DATA / record["file"]).read_bytes())
        assert record["kind"] == "hook"
        sel = clip["selection"]
        window = next(w for w in clip["windows"] if w["frame_lo"] == sel["window_frame"])
        assert window["player"] == sel["player"] and window["band"] == "high"
        assert len(window["s_mm"]) == window["frame_hi"] - window["frame_lo"] + 1 == width
        assert window["cadence_hz"] == sel["cadence_hz"]
        assert window["cadence_sd_hz"] is not None
        for w in clip["windows"]:
            assert clip["frame_lo"] <= w["frame_lo"] and w["frame_hi"] <= clip["frame_hi"]
        for frame in clip["frames"]:
            assert all(entry[4] is not None for entry in frame["p"]), "a player without joints"
            assert len({entry[0] for entry in frame["p"]}) == len(frame["p"])


def test_the_hook_is_not_the_extreme_of_its_match() -> None:
    summary = _json(WEB_DATA / SUMMARY_FILE)
    for record in summary["clips"]:
        sel = record["selection"]
        assert abs(sel["cadence_hz"] - sel["match_median_hz"]) < 0.01
        assert sel["high_windows"] >= 10


def test_the_three_limits_are_the_readmes_text_and_line() -> None:
    lines = README_FIXTURE.read_text(encoding="utf-8").splitlines()
    for limit in LIMITS:
        found = re.fullmatch(r"readme\.md:(\d+)(?:-(\d+))?", limit["readme"])
        assert found, limit["readme"]
        first = int(found.group(1))
        last = int(found.group(2) or first)
        text = " ".join(line.strip().removeprefix("* ") for line in lines[first - 1 : last])
        assert text == limit["text"], limit["id"]
        assert lines[first - 1].startswith("* "), "the line is not the start of a bullet"
        assert not lines[last].startswith("  "), "the limit goes on past its last line"
    summary = _json(WEB_DATA / SUMMARY_FILE)
    assert summary["limits"] == [dict(item) for item in LIMITS]


def test_a_changed_line_is_caught() -> None:
    lines = README_FIXTURE.read_text(encoding="utf-8").splitlines()
    wrong = dict(LIMITS[1], readme="readme.md:141-143")
    first, last = 141, 143
    text = " ".join(line.strip().removeprefix("* ") for line in lines[first - 1 : last])
    assert text != wrong["text"]


def test_pose_json_and_the_clips_are_to_watch_not_to_query() -> None:
    assert not serves_query("pose.json") and not serves_query("hook_1925299.json")
    publish = measure_publish(WEB_DATA)
    watch = {f["path"] for f in publish["watch"]}
    query = {f["path"] for f in publish["query"]}
    named = {SUMMARY_FILE, CLIP_FILE, *(c["file"] for c in _json(WEB_DATA / SUMMARY_FILE)["clips"])}
    assert named <= watch and not named & query


# --- --check -------------------------------------------------------------------------------


def _copy_published(tmp_path: Path) -> tuple[Path, Path]:
    out, reports = tmp_path / "web", tmp_path / "reports"
    shutil.copytree(WEB_DATA / "pose", out / "pose")
    shutil.copy(WEB_DATA / SUMMARY_FILE, out / SUMMARY_FILE)
    reports.mkdir()
    for path in REPORTS.glob("pose_*.json"):
        shutil.copy(path, reports / path.name)
    return out, reports


def _check(tmp_path: Path, out: Path, reports: Path) -> int:
    return run_publish_pose(tmp_path / "nodata", reports, out, MANIFEST, SCHEMA, check=True)


def test_check_says_partial_without_the_bronze_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, reports = _copy_published(tmp_path)
    assert _check(tmp_path, out, reports) == 0
    assert "PARTIAL 0/3" in capsys.readouterr().out


def test_check_fails_when_a_number_of_pose_json_is_typed(tmp_path: Path) -> None:
    out, reports = _copy_published(tmp_path)
    path = out / SUMMARY_FILE
    summary = _json(path)
    summary["coverage"]["1925299"]["total"]["frames"] += 1
    path.write_text(json.dumps(summary, separators=(",", ":"), ensure_ascii=False) + "\n")
    assert _check(tmp_path, out, reports) == 1


def test_check_fails_when_a_clip_changes_goes_missing_or_is_over_the_cap(tmp_path: Path) -> None:
    out, reports = _copy_published(tmp_path)
    summary = _json(out / SUMMARY_FILE)
    victim = out / summary["clips"][0]["file"]
    original = victim.read_bytes()
    victim.write_bytes(original.replace(b'"fps":25', b'"fps":25 ', 1))
    assert _check(tmp_path, out, reports) == 1
    victim.write_bytes(original)
    assert _check(tmp_path, out, reports) == 0
    victim.unlink()
    assert _check(tmp_path, out, reports) == 1
    victim.write_bytes(original)
    record = _json(reports / publish_pose.RECORD_FILE)
    record["clip"]["bytes"] = len(original) - 1  # the cap is the sample clip's measured bytes
    (reports / publish_pose.RECORD_FILE).write_text(json.dumps(record), encoding="utf-8")
    assert _check(tmp_path, out, reports) == 1


def test_check_fails_on_a_stray_clip_and_on_a_missing_summary(tmp_path: Path) -> None:
    out, reports = _copy_published(tmp_path)
    (out / "pose" / "hook_1.json").write_text("{}", encoding="utf-8")
    assert _check(tmp_path, out, reports) == 1
    (out / "pose" / "hook_1.json").unlink()
    (out / SUMMARY_FILE).unlink()
    assert _check(tmp_path, out, reports) == 1


def test_check_fails_when_a_report_moves_under_the_summary(tmp_path: Path) -> None:
    out, reports = _copy_published(tmp_path)
    metric = _json(reports / "pose_metric.json")
    metric["matches"]["1925299"][0][5] += 1
    (reports / "pose_metric.json").write_text(json.dumps(metric), encoding="utf-8")
    assert _check(tmp_path, out, reports) == 1


# --- the real bronze (skipped without it) -------------------------------------------------


@pytest.fixture(scope="module")
def real_data() -> Path:
    root = data_root()
    if not publish_pose._whole(root, 1925299):
        pytest.skip(f"no whole bronze of 1925299 under TRACKLAB_DATA_ROOT={root}: CI says PARTIAL")
    return root


def test_the_hook_of_the_real_match_is_the_rule_on_an_independent_median(real_data: Path) -> None:
    from tracklab.pose.data import load_players
    from tracklab.pose.verdict import window_estimates

    reports = _reports()
    frozen = reports["protocol"]["frozen"]
    windows = window_estimates(
        load_players(real_data, 1925299), int(frozen["width"]), float(frozen["cap_cm"]), mc_bands=()
    )
    high = [w for w in windows if w.band == "high" and math.isfinite(w.estimate.cadence_hz)]
    cad = sorted(w.estimate.cadence_hz for w in high)
    median = float(np.median(cad))
    record = next(c for c in _json(WEB_DATA / SUMMARY_FILE)["clips"] if c["match_id"] == 1925299)
    sel = record["selection"]
    assert len(high) == sel["high_windows"]
    assert sel["match_median_hz"] == pytest.approx(median, abs=5e-7)
    best = min(abs(c - median) for c in cad)
    assert abs(sel["cadence_hz"] - median) == pytest.approx(best, abs=1e-5)
    assert sel["cadence_hz"] != cad[-1]
    chosen = min(high, key=lambda w: (abs(w.estimate.cadence_hz - median), w.player_id, w.frame))
    assert (sel["player_id"], sel["window_frame"]) == (chosen.player_id, chosen.frame)


def test_the_windows_counted_here_are_the_metrics(real_data: Path) -> None:
    from tracklab.pose.data import load_players
    from tracklab.pose.verdict import window_estimates

    frozen = _reports()["protocol"]["frozen"]
    windows = window_estimates(
        load_players(real_data, 1925299), int(frozen["width"]), float(frozen["cap_cm"]), mc_bands=()
    )
    rows = [r for r in _reports()["metric"]["matches"]["1925299"] if r[3] == "all"]
    for band in ("low", "high"):
        counted = sum(w.band == band for w in windows)
        assert counted == sum(r[5] for r in rows if r[4] == band)


def test_the_bronze_path_gives_the_samples_skeletons_within_a_centimetre(real_data: Path) -> None:
    """The bronze keeps float32 and no row for a player without a pose, so the clip it gives
    cannot have the sample's bytes: the skeletons it does hold must be the sample's, to within
    the half-centimetre ties that float32 can flip."""
    sample = json.loads((WEB_DATA / CLIP_FILE).read_bytes())
    lo, hi = sample["frame_lo"], sample["frame_hi"]
    table = pose_hook.read_frame_table(real_data, 1925299)
    from tracklab.pose.data import load_players

    rows = load_players(real_data, 1925299)
    flags = pose_hook.detected_flags(real_data, 1925299, lo, hi)
    frames = pose_hook.pose_frames(rows, table, flags, lo, hi)
    ids = [p["player_id"] for p in sample["players"]]
    worst = 0
    compared = flipped = 0
    for mine, theirs in zip(frames, sample["frames"], strict=True):
        assert mine.frame == theirs["f"]
        posed = {ids[e[0]]: e for e in theirs["p"] if e[4] is not None}
        assert {p.player_id for p in mine.players} == set(posed)
        for p in mine.players:
            e = posed[p.player_id]
            assert p.xyz is not None and p.mae_cm is not None
            rel = publish_pose.cm(p.xyz - np.array([p.x, p.y, 0.0]))
            diff = np.abs(rel - np.array(e[4][0]))
            worst = max(worst, int(diff.max()))
            compared += diff.size
            flipped += int((diff > 0).sum())
            assert int(publish_pose.cm(p.x)) == e[1] and int(publish_pose.cm(p.y)) == e[2]
            assert bool(e[3]) == p.is_detected
    print(f"bronze vs sample: {compared} coordinates, {flipped} differ, worst {worst} cm")
    # Some offsets sit on a half-centimetre tie, which is all float32 can flip (measured: 4.5 %,
    # none by more than 1 cm); a bound of a tenth is the loosest that still means a tie.
    assert worst <= 1 and flipped / compared < 0.1


def test_a_dead_state_publishes_a_stretch_without_a_metric(real_data: Path, tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    for path in REPORTS.glob("pose_*.json"):
        shutil.copy(path, reports / path.name)
    calibration = _json(reports / "pose_calibration.json")
    calibration["rule_w_cap"]["chosen"] = None
    (reports / "pose_calibration.json").write_text(json.dumps(calibration), encoding="utf-8")
    (reports / "pose_metric.json").unlink()
    (reports / "pose_verdict.json").unlink()
    texts, summary_text = publish_pose._site(real_data, MANIFEST, reports)
    summary = json.loads(summary_text)
    assert (summary["status"], summary["dead_at"], summary["tables"]) == ("dead", "noise", None)
    assert list(texts) == ["pose/stretch_1925299.json"]  # 1996435 stays closed
    clip = json.loads(texts["pose/stretch_1925299.json"])
    assert clip["selection"]["kind"] == "stretch" and clip["windows"] == []
    assert publish_pose.validate_clip(clip, SCHEMA) == []
    table = pose_hook.read_frame_table(real_data, 1925299)
    lo, hi = clip["frame_lo"], clip["frame_hi"]
    best = max(
        int(table.n_with_pose[i : i + 100].sum())
        for i in range(len(table.frame) - 99)
        if len({p for p in table.period[i : i + 100]}) == 1 and table.period[i] is not None
    )
    assert clip["selection"]["skeletons"] == best
    assert int(table.n_with_pose[(table.frame >= lo) & (table.frame <= hi)].sum()) == best
    assert pose_summary.status_of(pose_summary.load_reports(reports)) == ("dead", "noise")


# --- the documents the web's e2e is given ---------------------------------------------------

FIXTURES = REPO / "web" / "e2e" / "fixtures"


def site_documents() -> dict[str, dict[str, Any]]:
    """`pose.json` as the publisher writes it in each state the page has a branch for: alive (the
    published one), unreplicated (1996435 below the minima of M1 and M2) and dead at M4 (its
    clips are stretches, chosen without a metric). Built by `build_summary` from the reports
    changed the way each state changes them, so the page is tested on the publisher's own shape.
    Regenerate with `python -c "import test_publish_pose_site as t; t.write_documents()"` from
    `pipeline/tests/unit`."""
    published = _json(WEB_DATA / SUMMARY_FILE)
    clips = published["clips"]
    alive = pose_summary.build_summary(_reports(), clips)

    unreplicated_reports = copy.deepcopy(_reports())
    confirmation = unreplicated_reports["metric"]["verdicts"]
    confirmation["p6"] = "unreplicated"
    confirmation["confirmation"] = {
        "coverage": {"players_ge_min_high": 4, "players_ge_min_both": 3, "reached": False},
        "m4": None,
        "status": "unreplicated",
    }
    unreplicated = pose_summary.build_summary(unreplicated_reports, clips)

    dead_reports = copy.deepcopy(_reports())
    verdicts = dead_reports["metric"]["verdicts"]
    verdicts["p6"] = "replication_failed"
    verdicts["confirmation"]["status"] = "replication_failed"
    verdicts["confirmation"]["m4"].update(median_sd_hz=0.2, dies_at="m2_precision")
    stretches = []
    for record in clips:
        stretch = copy.deepcopy(record)
        stretch.update(
            kind="stretch",
            file=f"pose/stretch_{record['match_id']}.json",
            selection={"kind": "stretch", "rule": pose_hook.STRETCH_RULE, "skeletons": 1},
            windows=[],
        )
        stretches.append(stretch)
    dead = pose_summary.build_summary(dead_reports, stretches)
    return {"alive": alive, "unreplicated": unreplicated, "dead": dead}


def write_documents() -> None:
    for name, document in site_documents().items():
        text = json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
        (FIXTURES / f"pose.{name}.json").write_text(text, encoding="utf-8", newline="\n")


def test_the_e2e_documents_are_what_the_publisher_writes_in_each_state() -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(_json(SUMMARY_SCHEMA))
    documents = site_documents()
    assert {n: d["status"] for n, d in documents.items()} == {
        "alive": "alive",
        "unreplicated": "unreplicated",
        "dead": "dead",
    }
    for name, document in documents.items():
        assert list(validator.iter_errors(document)) == [], name
        assert _json(FIXTURES / f"pose.{name}.json") == document, f"regenerate pose.{name}.json"
    assert documents["alive"] == _json(WEB_DATA / SUMMARY_FILE)
    assert documents["dead"]["tables"] is None and documents["dead"]["dead_at"] == "M4"
