"""`tracklab runs effect` and `tracklab runs freeze`, death probe 2 of P5 (task 50).

The class at t_c, the detection of a leg's marker, the overlap keys and the verdict are
tested on hand-built inputs where the answer is known; the whole command on a synthetic
warehouse of 20 matches with a planted effect, a planted pre-trend on three subtypes (they
must leave by M3), planted extrapolation on two (M4) and nothing else on five (the
candidates); then the freeze on a throwaway repository, after which the held-out half opens
and both `--check`s stay green. Real data enters only through the versioned
`runs_calibration.json`, at the end.

Mutations recorded in tasks/todo.md: the pre-trend measured at t_c + 1 s (the cause moved
after the effect's window starts) lets the planted pre-trend pass M3 and fails the synthetic
test; the sha comparison removed from the guard and a guard looking at `stage` alone fail
the two tests of test_runs_protocol; a class read one second after t_c fails the hand-built
class test; the probe rewriting the file without the foreign sections fails the keep test.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest
from test_runs_protocol import HELD_OUT
from test_runs_windows import (  # the synthetic match and the throwaway design repo of task 48
    CI_FIXTURE_MATCH,
    OTHER,
    PLANTED_LINE_M,
    PLANTED_MARKER_M,
    TEAM,
    _git,
    _synthetic_raw,
    _write_warehouse,
    design_repo,  # noqa: F401  (a fixture)
)

from tracklab.cli import build_parser
from tracklab.paths import data_root
from tracklab.runs import candidates, data, probe
from tracklab.runs.candidates import (
    M3_PRE_TREND_SHARE,
    M4_DETECTED_SHARE,
    NOT_TESTABLE_ON_LINE,
    TESTABLE_ON_LINE,
    EffectInputError,
    consistency_problems,
    line_testability,
    run_leg_overlap_keys,
    run_runs_effect,
    run_runs_freeze,
    section_sha256,
    subtype_verdict,
)
from tracklab.runs.data import HeldOutLocked, load_half
from tracklab.runs.probe import PROBE_NAME, run_runs_probe
from tracklab.runs.protocol import (
    BAR_P,
    N_PERMUTATIONS,
    STAGE_DESIGN,
    STAGE_FROZEN,
    SUBTYPES,
    read_protocol,
    seal,
    sealed,
)
from tracklab.runs.windows import (
    EFFECT_FRAMES,
    RUN_CLASSES,
    VELOCITY_FRAMES,
    MatchTracking,
    PairEffect,
    Run,
    components,
    leg_marker_detected,
    run_class,
)

PIPELINE = Path(__file__).resolve().parents[2]
REPORTS = PIPELINE / "reports"
CALIBRATION_FILE = REPORTS / PROBE_NAME
SRC = PIPELINE / "src" / "tracklab" / "runs"
PROBABLE = ["coming_short", "run_ahead_of_the_ball", "support"]  # task 49's, by the marker


# --- the class at t_c ---------------------------------------------------------------------


def _walker(
    *, ball: tuple[float, float], start_y: float, velocity: tuple[float, float]
) -> tuple[MatchTracking, Run]:
    """A runner at (−10, start_y) at t_c = 40, moving with `velocity` (m per frame) before
    and after it; two outfield opponents at x = 30 and 28 make the line; the ball sits at
    `ball`. One second after t_c the runner has moved on, so a class read there differs."""
    n, t_c = 100, 40
    k = np.arange(n)
    x = np.full((n, 4), np.nan)
    y = np.full((n, 4), np.nan)
    x[:, 0] = -10.0 + velocity[0] * (k - t_c)
    y[:, 0] = start_y + velocity[1] * (k - t_c)
    x[:, 1], y[:, 1] = 30.0, 8.0
    x[:, 2], y[:, 2] = 28.0, -8.0
    x[:, 3], y[:, 3] = 50.0, 0.0
    tracking = MatchTracking(
        match_id=CI_FIXTURE_MATCH,
        frame0=0,
        x=x,
        y=y,
        detected=np.ones((n, 4), dtype=np.bool_),
        entities=("fb:7", "fb:301", "fb:302", "fb:303"),
        team=(TEAM, OTHER, OTHER, OTHER),
        is_goalkeeper=np.array([False, False, False, True]),
        period_frames={1: (0, n - 1)},
        attack_sign={(1, TEAM): 1, (1, OTHER): -1},
        ball_x=np.full(n, ball[0]),
        ball_y=np.full(n, ball[1]),
    )
    return tracking, Run(CI_FIXTURE_MATCH, "r", 7, 100, 1, t_c, t_c + 20, "support", "p")


@pytest.mark.usefixtures("design_repo")
def test_run_class_reads_the_runner_against_the_ball_the_line_and_the_flank() -> None:
    """Each bit from the velocity over [t_c - V, t_c]: towards the ball, towards the line
    (its x ahead of the runner), towards the nearer touchline; and None without a direction,
    a ball or a line."""
    assert len(RUN_CLASSES) == 8 and len(set(RUN_CLASSES)) == 8
    # forward and outward (y grows, the runner at y = 5 > 0), the ball behind: from the
    # ball, to the line, wide
    t, run = _walker(ball=(-20.0, 0.0), start_y=5.0, velocity=(0.5, 0.2))
    assert run_class(t, run) == "from_ball/to_line/wide"
    # the same velocity with the ball ahead: to the ball
    t, run = _walker(ball=(20.0, 5.0), start_y=5.0, velocity=(0.5, 0.2))
    assert run_class(t, run) == "to_ball/to_line/wide"
    # backward and inward (y shrinks towards 0), the ball ahead: from the ball, from the
    # line, inside
    t, run = _walker(ball=(20.0, 0.0), start_y=5.0, velocity=(-0.5, -0.2))
    assert run_class(t, run) == "from_ball/from_line/inside"
    # the mirror flank: at y = -5 moving towards -y is wide
    t, run = _walker(ball=(-20.0, 0.0), start_y=-5.0, velocity=(0.5, -0.2))
    assert run_class(t, run) == "from_ball/to_line/wide"
    # the class is read at t_c, not one second on: a runner turning there keeps the class
    # of his approach
    t, run = _walker(ball=(-20.0, 0.0), start_y=5.0, velocity=(0.5, 0.2))
    turned = t.x.copy()
    turned[run.frame_start + 1 :, 0] = turned[run.frame_start, 0] - 0.5 * np.arange(
        1, t.n_frames - run.frame_start
    )
    later = MatchTracking(**{**{f: getattr(t, f) for f in t.__dataclass_fields__}, "x": turned})
    assert run_class(later, run) == "from_ball/to_line/wide"
    # no direction, no ball, no line: no class
    t, run = _walker(ball=(-20.0, 0.0), start_y=5.0, velocity=(0.0, 0.0))
    assert run_class(t, run) is None
    t, run = _walker(ball=(np.nan, np.nan), start_y=5.0, velocity=(0.5, 0.2))
    assert run_class(t, run) is None
    t, run = _walker(ball=(-20.0, 0.0), start_y=5.0, velocity=(0.5, 0.2))
    no_ball = MatchTracking(
        **{**{f: getattr(t, f) for f in t.__dataclass_fields__}, "ball_x": None, "ball_y": None}
    )
    assert run_class(no_ball, run) is None
    one_x = t.x.copy()
    one_x[run.frame_start, 2] = np.nan
    lone = MatchTracking(**{**{f: getattr(t, f) for f in t.__dataclass_fields__}, "x": one_x})
    assert run_class(lone, run) is None


@pytest.mark.usefixtures("design_repo")
def test_leg_marker_detected_needs_every_frame_of_the_window() -> None:
    t, run = _walker(ball=(-20.0, 0.0), start_y=5.0, velocity=(0.5, 0.0))
    # the marker is the nearest opponent at t_c: from (-10, 5) the one at (30, 8) is 40.1 m
    # away, the one at (28, -8) 40.2 m: fb:301, column 1
    assert leg_marker_detected(t, run, 1, run.frame_start) is True

    def blind_at(frame: int, column: int) -> MatchTracking:
        detected = t.detected.copy()
        detected[frame, column] = False
        fields = {f: getattr(t, f) for f in t.__dataclass_fields__}
        return MatchTracking(**{**fields, "detected": detected})

    assert leg_marker_detected(blind_at(run.frame_start + EFFECT_FRAMES, 1), run, 1, 40) is False
    assert leg_marker_detected(blind_at(run.frame_start - VELOCITY_FRAMES, 1), run, 1, 40) is False
    assert leg_marker_detected(blind_at(run.frame_start + 7, 1), run, 1, 40) is False
    assert leg_marker_detected(blind_at(run.frame_start, 2), run, 1, 40) is True  # not the marker
    assert leg_marker_detected(blind_at(run.frame_start + EFFECT_FRAMES + 1, 1), run, 1, 40) is True
    assert leg_marker_detected(t, run, 1, 2) is None  # no leg: t - V before the period


# --- the keys of the run-leg overlap control -------------------------------------------------


def _pair(i: int, possession: str | None, t_c: int, instant: int = 900) -> PairEffect:
    return PairEffect(
        CI_FIXTURE_MATCH, f"r{i}", possession, "support", 7, t_c, 1, instant, 0, 0, 0, 0
    )


def test_run_leg_overlap_keys_link_overlapping_legs_of_a_team_and_keep_the_protocols() -> None:
    v, w = VELOCITY_FRAMES, EFFECT_FRAMES
    a = run_leg_overlap_keys(_pair(0, "p0", 100), 1, v, w)
    b = run_leg_overlap_keys(_pair(1, "p1", 100 + w, 901), 1, v, w)  # legs touch at 120
    c = run_leg_overlap_keys(_pair(2, "p2", 100 + 2 * w + v + 1, 902), 1, v, w)  # apart from b
    d = run_leg_overlap_keys(_pair(3, "p3", 100, 903), 2, v, w)  # the other team, same time
    e = run_leg_overlap_keys(_pair(4, "p0", 500, 904), 1, v, w)  # the protocol's possession key
    f = run_leg_overlap_keys(_pair(5, None, 700, 900), 1, v, w)  # the protocol's instant key
    assert components([a, b, c, d, e, f]) == [0, 0, 1, 2, 0, 0]
    assert ("p", "p0") in a and ("i", (7, 900)) in a
    assert sum(1 for k in a if k[0] == "f") == v + w + 1


# --- the verdict ----------------------------------------------------------------------------


def test_subtype_verdict_follows_the_written_criteria() -> None:
    alive = subtype_verdict(
        passes_bar=True, pre_trend_ratio=0.1, class_opposite_sign=False, detected_ratio=0.9
    )
    assert alive["candidate"] and not alive["M3"]["leaves"] and not alive["M4"]["leaves"]
    # M3 by the pre-trend, at the threshold itself
    m3 = subtype_verdict(
        passes_bar=True,
        pre_trend_ratio=M3_PRE_TREND_SHARE,
        class_opposite_sign=False,
        detected_ratio=0.9,
    )
    assert m3["M3"]["pre_trend_reaches_share"] and m3["M3"]["leaves"] and not m3["candidate"]
    assert not subtype_verdict(
        passes_bar=True, pre_trend_ratio=0.4999, class_opposite_sign=False, detected_ratio=0.9
    )["M3"]["leaves"]
    # M3 by the class
    m3c = subtype_verdict(
        passes_bar=True, pre_trend_ratio=0.0, class_opposite_sign=True, detected_ratio=1.0
    )
    assert m3c["M3"]["leaves"] and not m3c["M3"]["pre_trend_reaches_share"] and not m3c["candidate"]
    # M4: below half, or a sign change (a negative ratio)
    for ratio in (M4_DETECTED_SHARE - 0.0001, -0.3, -1.2):  # a sign change of any size
        m4 = subtype_verdict(
            passes_bar=True, pre_trend_ratio=0.0, class_opposite_sign=False, detected_ratio=ratio
        )
        assert m4["M4"]["leaves"] and not m4["candidate"]
    assert not subtype_verdict(
        passes_bar=True,
        pre_trend_ratio=0.0,
        class_opposite_sign=False,
        detected_ratio=M4_DETECTED_SHARE,
    )["M4"]["leaves"]
    # a pre-trend of the opposite sign is no reaction; a subtype that fails the bar is no
    # candidate whatever the controls; a ratio that cannot be computed stays silent
    assert not subtype_verdict(
        passes_bar=True, pre_trend_ratio=-2.0, class_opposite_sign=False, detected_ratio=1.0
    )["M3"]["leaves"]
    assert not subtype_verdict(
        passes_bar=False, pre_trend_ratio=0.0, class_opposite_sign=False, detected_ratio=1.0
    )["candidate"]
    silent = subtype_verdict(
        passes_bar=True, pre_trend_ratio=None, class_opposite_sign=False, detected_ratio=None
    )
    assert silent["candidate"] and silent["M3"]["pre_trend_ratio"] is None


def test_line_testability_follows_the_probes_rows() -> None:
    rows = [
        {"subtype": "a", "half": "calibration", "mde80_line_sd": 0.3},
        {"subtype": "a", "half": "other", "mde80_line_sd": 0.3},
        {"subtype": "b", "half": "calibration", "mde80_line_sd": 0.3},
        {"subtype": "b", "half": "other", "mde80_line_sd": 0.35},
        {"subtype": "c", "half": "calibration", "mde80_line_sd": None},
        {"subtype": "c", "half": "other", "mde80_line_sd": 0.2},
    ]
    assert line_testability(rows, "a") == TESTABLE_ON_LINE
    assert line_testability(rows, "b") == NOT_TESTABLE_ON_LINE
    assert line_testability(rows, "c") == NOT_TESTABLE_ON_LINE
    assert line_testability(rows, "d") == NOT_TESTABLE_ON_LINE


# --- the command on a synthetic warehouse ---------------------------------------------------

PRE_TREND_ON = ("behind", "coming_short", "cross_receiver")  # leave by M3
EXTRAPOLATED_ON = ("dropping_off", "overlap")  # leave by M4
EXTRAPOLATED_PUSH_M = 14.0  # on the second run of each triple: every pair 6 m, detected 2 m


def _synthetic_warehouse(
    root: Path,
    *,
    pre_push: float | Mapping[str, float],
    extrapolated: Mapping[str, float] | None,
) -> list[int]:
    """Twenty synthetic matches under the committed split's ids, 30 runs each, a baseline
    per run shared by its two scenes (so 30 pairs per subtype and half make a probable
    subtype), with task 50's plantings; returns the calibration ids."""
    calibration = load_half("calibration")
    for i, match_id in enumerate(data.counting_match_ids()):
        raw, runs, instants = _synthetic_raw(
            30,
            PLANTED_MARKER_M,
            PLANTED_LINE_M,
            seed=500 + i,
            match_id=match_id,
            pre_push=pre_push,
            baseline_sd=20.0,
            extrapolated=extrapolated,
        )
        _write_warehouse(root, raw, runs, instants, pitch_length=100.0 + 2.0 * (i % 4))
    return calibration


def _written(
    tmp_path: Path,
    *,
    pre_push: float | Mapping[str, float] = dict.fromkeys(PRE_TREND_ON, 1.0),
    extrapolated: Mapping[str, float] | None = dict.fromkeys(EXTRAPOLATED_ON, EXTRAPOLATED_PUSH_M),
) -> tuple[Path, Path, dict[str, object]]:
    root, reports = tmp_path / "data", tmp_path / "reports"
    _synthetic_warehouse(root, pre_push=pre_push, extrapolated=extrapolated)
    assert run_runs_probe(root, reports) == 0
    before = json.loads((reports / PROBE_NAME).read_text(encoding="utf-8"))
    assert before["probe"]["power"]["probable"]["marker"] == list(SUBTYPES)  # all ten probable
    code = run_runs_effect(root, reports)
    payload = json.loads((reports / PROBE_NAME).read_text(encoding="utf-8"))
    assert code == (2 if payload["effect"]["verdict"]["M5a"]["dies"] else 0)
    return root, reports, payload


def _commit_freeze(repo: Path, reports: Path) -> None:
    """What Javier does after `runs freeze` writes the file: commit it, and nothing else."""
    shutil.copy(reports / "runs_protocol.json", repo / data.PROTOCOL_IN_REPO)
    _git(repo, "add", data.PROTOCOL_IN_REPO)
    _git(repo, "commit", "-q", "-m", "freeze")


@pytest.mark.usefixtures("design_repo")
def test_the_effect_on_planted_subtypes_applies_m3_and_m4_and_check_reproduces_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, reports, payload = _written(tmp_path)
    assert sealed(payload) and consistency_problems(payload) == []
    assert list(payload)[-3:] == ["probe", "effect", "content_sha256"]
    e = payload["effect"]
    assert e["matches"] == load_half("calibration") and e["half"] == "calibration"
    assert len(e["head"]) == 40 and len(e["code_tree_sha"]) == 40
    assert e["code_tree_sha"] == data.code_tree_sha() and e["head"] == data.head_commit()
    assert e["probe_section_sha256"] == section_sha256(payload["probe"])
    assert e["protocol"] == payload["protocol"]
    assert e["inputs"]["subtypes"] == list(SUBTYPES)
    assert (
        e["inputs"]["placebo_sd_marker_m"]
        == payload["probe"]["standardisation"]["placebo_sd_marker_m"]
    )
    rows = {r["subtype"]: r for r in e["per_subtype"]}
    assert list(rows) == list(SUBTYPES)
    for s, r in rows.items():
        pooled = r["marker"]["pooled"]
        assert r["pairs"] == pooled["pairs"] == pooled["units"] == 30
        assert len(r["marker"]["per_match"]) == 10
        assert all(row["pairs"] == 3 for row in r["marker"]["per_match"])
        # every subtype passes the bar (three pairs per match: a 1 m effect may lose a match)
        assert pooled["same_sign_matches"] >= 8 and pooled["p"] == round(
            1 / (1 + N_PERMUTATIONS), 5
        )
        assert pooled["passes_bar"] and r["verdict"]["passes_bar"]
        if s not in PRE_TREND_ON:
            assert pooled["same_sign_matches"] == 10
        assert r["line"]["testability"] in (TESTABLE_ON_LINE, NOT_TESTABLE_ON_LINE)
        assert abs(r["line"]["pooled"]["mean_m"] - PLANTED_LINE_M) < 0.3
        # the class at t_c: the runner walks along d before t_c, the ball behind him, the
        # line ahead: from the ball, to the line, wide or inside by the flank
        cls = r["class_at_tc"]
        assert cls["unclassified"] == 0 and cls["classified"] == 30
        assert set(k for k, n in cls["distribution"].items() if n) <= {
            "from_ball/to_line/wide",
            "from_ball/to_line/inside",
        }
        assert cls["modal_class"] in ("from_ball/to_line/wide", "from_ball/to_line/inside")
        assert cls["modal_class_effect"]["mean_m"] > 0 and not cls["opposite_sign"]
        assert not r["verdict"]["M3"]["class_at_tc_opposite_sign"]
        # the run-leg overlap control: legs 10 s apart never overlap, the units stay
        assert r["run_leg_overlap"]["units"] == 30 and r["run_leg_overlap"]["largest_unit"] == 1
        assert r["run_leg_overlap"]["passes_bar"]
        pre, det = r["pre_trend"]["pooled"], r["fully_detected"]["pooled"]
        if s in PRE_TREND_ON:
            # the marker moved 1 m before the runner: the effect is the planted 2 m minus
            # what the velocity at t_c then predicted, and the pre-trend is the metre
            assert abs(pooled["mean_m"] - (PLANTED_MARKER_M - 1.0)) < 0.5, s
            assert abs(pre["pre_trend_mean_m"] - 1.0) < 0.2, s
            assert pre["ratio"] >= M3_PRE_TREND_SHARE and r["verdict"]["M3"]["leaves"], s
            assert not r["verdict"]["candidate"]
        elif s in EXTRAPOLATED_ON:
            # one run in three carries 14 m with its marker undetected: 6 m with every
            # pair, the planted 2 m with the detected ones
            assert abs(pooled["mean_m"] - (2 * PLANTED_MARKER_M + EXTRAPOLATED_PUSH_M) / 3) < 0.5
            assert (
                r["fully_detected"]["pairs"] == 20 and abs(det["mean_m"] - PLANTED_MARKER_M) < 0.5
            )
            assert det["ratio"] < M4_DETECTED_SHARE and r["verdict"]["M4"]["leaves"], s
            assert not r["verdict"]["M3"]["leaves"] and not r["verdict"]["candidate"]
        else:
            assert abs(pooled["mean_m"] - PLANTED_MARKER_M) < 0.5, s
            assert abs(pre["pre_trend_mean_m"]) < 0.2 and pre["ratio"] < M3_PRE_TREND_SHARE, s
            assert r["fully_detected"]["pairs"] == 30 and det["ratio"] == 1.0
            assert r["verdict"]["candidate"], s
        # the pre-trend leg is missing for the first run of each period (its t - W - V
        # frames fall before the period), and nowhere else
        assert 28 <= r["pre_trend"]["pairs"] <= 30
    expected = [s for s in SUBTYPES if s not in PRE_TREND_ON and s not in EXTRAPOLATED_ON]
    assert e["candidates"] == expected and len(expected) == 5
    assert e["verdict"] == {
        "M5a": {
            "rule": "zero candidates -> P5 dies, the held-out half is never opened",
            "candidates": 5,
            "dies": False,
        },
        "alive": True,
    }
    # --check: the whole warehouse recomputes and agrees; a resealed hand edit differs
    text = (reports / PROBE_NAME).read_text(encoding="utf-8")
    capsys.readouterr()
    assert run_runs_effect(root, reports, check=True) == 0
    assert "warehouse=FULL 10/10 recomputed and equal" in capsys.readouterr().out
    doctored = json.loads(text)
    doctored["effect"]["per_subtype"][0]["pre_trend"]["pairs"] += 1
    (reports / PROBE_NAME).write_text(
        json.dumps(seal(doctored), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    assert run_runs_effect(root, reports, check=True) == 1
    assert "differs from what the code writes" in capsys.readouterr().out
    (reports / PROBE_NAME).write_text(text, encoding="utf-8")
    # inherited (a): the probe rewritten keeps the effect section, byte for byte, and both
    # checks stay green
    assert run_runs_probe(root, reports) == 0
    assert (reports / PROBE_NAME).read_text(encoding="utf-8") == text
    assert run_runs_probe(root, reports, check=True) == 0
    assert run_runs_effect(root, reports, check=True) == 0
    # two writes, the same bytes
    again = tmp_path / "again"
    shutil.copytree(reports, again)
    assert run_runs_effect(root, again) == 0
    assert (again / PROBE_NAME).read_bytes() == text.encode("utf-8")
    # the freeze, prepared: writes the frozen protocol from the candidates and HEAD's tree
    shutil.copy(data.repo_root() / data.PROTOCOL_IN_REPO, reports / "runs_protocol.json")
    assert run_runs_freeze(reports, date="2026-10-12") == 0
    frozen = read_protocol(reports / "runs_protocol.json")
    assert frozen["stage"] == STAGE_FROZEN and sealed(frozen)
    assert frozen["frozen"]["candidates"] == expected
    assert frozen["frozen"]["code_tree_sha"] == data.code_tree_sha()
    assert frozen["frozen"]["candidates_from"]["content_sha256"] == payload["content_sha256"]
    assert frozen["fingerprint"] == payload["protocol"]["fingerprint"]
    assert data.head_stage() == STAGE_DESIGN  # written, not committed: nothing opened
    with pytest.raises(HeldOutLocked):
        load_half("held_out")
    # the commit is the freeze: the held-out half opens, and the calibration file written
    # under design still answers to the committed protocol (same design, stage recorded)
    _commit_freeze(data.repo_root(), reports)
    assert data.head_stage() == STAGE_FROZEN
    assert load_half("held_out") == HELD_OUT
    assert consistency_problems(payload) == [] and probe.consistency_problems(payload) == []
    capsys.readouterr()
    assert run_runs_effect(root, reports, check=True) == 0
    assert run_runs_probe(root, reports, check=True) == 0
    out = capsys.readouterr().out
    assert "runs effect: warehouse=FULL 10/10 recomputed and equal" in out
    assert "runs probe: warehouse=FULL 10/10 recomputed and equal" in out
    # a code commit after the freeze: the freeze refuses to run again (the file is frozen)
    # and the held-out half closes (test_runs_protocol has the guard's mutation)
    assert run_runs_freeze(reports, date="2026-10-12") == 1
    assert "only a protocol in stage" in capsys.readouterr().out
    # --check on a partial warehouse (one calibration match's frames gone) recomputes
    # nothing and says so
    frames = root / "silver" / "frames" / "sport=football"
    gone = frames / f"native_match_id={load_half('calibration')[-1]}"
    shutil.rmtree(gone)
    capsys.readouterr()
    assert run_runs_effect(root, again, check=True) == 0
    out = capsys.readouterr().out
    assert "warehouse=PARTIAL 9/10 at hand, 0/10 recomputed" in out
    assert "figures as written" in out and "FULL" not in out
    assert run_runs_effect(root, again) == 1  # and writes nothing from a partial warehouse


@pytest.mark.usefixtures("design_repo")
def test_the_effect_with_no_candidate_dies_at_m5a_and_the_freeze_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every subtype with the pre-trend planted: all leave by M3, zero candidates, M5a; the
    command says so with rc 2, `--check` still reproduces it, and the freeze writes nothing."""
    root, reports, payload = _written(tmp_path, pre_push=1.0, extrapolated=None)
    e = payload["effect"]
    assert all(r["verdict"]["M3"]["leaves"] for r in e["per_subtype"])
    assert e["candidates"] == [] and e["verdict"]["M5a"]["dies"] and not e["verdict"]["alive"]
    assert consistency_problems(payload) == []
    capsys.readouterr()
    assert run_runs_effect(root, reports, check=True) == 0
    assert "M5a_dies=True" in capsys.readouterr().out
    shutil.copy(data.repo_root() / data.PROTOCOL_IN_REPO, reports / "runs_protocol.json")
    before = (reports / "runs_protocol.json").read_bytes()
    assert run_runs_freeze(reports, date="2026-10-12") == 2
    assert "zero candidates (M5a)" in capsys.readouterr().out
    assert (reports / "runs_protocol.json").read_bytes() == before
    with pytest.raises(HeldOutLocked):
        load_half("held_out")


@pytest.mark.usefixtures("design_repo")
def test_consistency_problems_see_a_doctored_verdict_or_input(tmp_path: Path) -> None:
    _, _, payload = _written(tmp_path)

    def doctored(**changes: object) -> dict[str, object]:
        p = json.loads(json.dumps(payload))
        for path, value in changes.items():
            node = p
            keys = path.split("__")
            for key in keys[:-1]:
                node = node[int(key) if key.isdigit() else key]
            node[keys[-1]] = value
        return seal(p)

    def says(fragment: str, **changes: object) -> bool:
        return any(fragment in s for s in consistency_problems(doctored(**changes)))

    assert consistency_problems(payload) == []
    assert "content_sha256" in " ".join(consistency_problems({**payload, "plan": "x"}))
    assert "no effect section" in consistency_problems(
        seal({k: v for k, v in payload.items() if k != "effect"})
    )
    assert says("probe_section_sha256", effect__probe_section_sha256="0" * 64)
    assert says("probe:", probe__verdict__M2__dies=True)  # the probe section itself
    assert says("effect.protocol.fingerprint", effect__protocol__fingerprint="0" * 64)
    assert says("calibration half", effect__matches=[1])
    assert says("probable list", effect__inputs__subtypes=["support"])
    assert says("per_subtype does not follow", effect__per_subtype=[])
    assert says("placebo_sd_marker_m", effect__inputs__placebo_sd_marker_m=1.0)
    assert says("line_testability", effect__inputs__line_testability__support="x")
    assert says("line.testability", effect__per_subtype__0__line__testability="x")
    assert says("passes_bar", effect__per_subtype__0__marker__pooled__passes_bar=False)
    assert says("verdict of", effect__per_subtype__0__verdict__candidate=True)
    assert says("verdict of", effect__per_subtype__0__verdict__M3__leaves=False)
    assert says("verdict of", effect__per_subtype__3__verdict__M4__leaves=False)
    # a ratio edited so the written flag no longer follows it
    assert says("verdict of", effect__per_subtype__5__pre_trend__pooled__pre_trend_mean_m=5.0)
    assert says("verdict of", effect__per_subtype__5__class_at_tc__modal_class_effect__mean_m=-1.0)
    assert says("candidates do not follow", effect__candidates=list(SUBTYPES))
    assert says("M5a", effect__verdict__M5a__dies=True)
    assert says("alive", effect__verdict__alive=False)
    assert says("git sha", effect__head="abc")


@pytest.mark.usefixtures("design_repo")
def test_the_effect_refuses_uncommitted_code_and_a_tree_other_than_the_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Write mode names the code that ran, like the probe's; the freeze refuses when HEAD's
    `runs/` tree is not the one that computed the effect section."""
    root, reports, payload = _written(tmp_path)
    before = (reports / PROBE_NAME).read_bytes()
    code = data.repo_root() / data.CODE_IN_REPO / "probe.py"
    code.write_text("# edited and not committed\n", encoding="utf-8")
    capsys.readouterr()
    assert run_runs_effect(root, reports) == 1
    assert "not committed" in capsys.readouterr().out
    assert (reports / PROBE_NAME).read_bytes() == before
    shutil.copy(data.repo_root() / data.PROTOCOL_IN_REPO, reports / "runs_protocol.json")
    assert run_runs_freeze(reports, date="2026-10-12") == 1
    assert "not committed" in capsys.readouterr().out
    _git(data.repo_root(), "add", ".")
    _git(data.repo_root(), "commit", "-q", "-m", "code after the effect")
    assert run_runs_freeze(reports, date="2026-10-12") == 1
    assert "regenerate it on this tree first" in capsys.readouterr().out
    assert read_protocol(reports / "runs_protocol.json")["stage"] == STAGE_DESIGN
    assert run_runs_effect(root, reports) == 0  # regenerated on the new tree
    assert (
        json.loads((reports / PROBE_NAME).read_text(encoding="utf-8"))["effect"]["code_tree_sha"]
        == data.code_tree_sha()
    )
    assert run_runs_freeze(reports, date="2026-10-12") == 0


@pytest.mark.usefixtures("design_repo")
def test_the_effect_refuses_a_file_without_a_consistent_probe_section(tmp_path: Path) -> None:
    root, reports = tmp_path / "data", tmp_path / "reports"
    reports.mkdir()
    assert run_runs_effect(root, reports) == 1  # no file
    (reports / PROBE_NAME).write_text(json.dumps(seal({"probe": {}})) + "\n", encoding="utf-8")
    assert run_runs_effect(root, reports, check=True) == 1
    with pytest.raises(EffectInputError, match="not one to answer to"):
        candidates.probe_inputs(seal({"probe": {}}))


def test_the_effect_names_the_calibration_half_and_no_other_door() -> None:
    text = (SRC / "candidates.py").read_text(encoding="utf-8")
    assert 'HALF: Half = "calibration"' in text
    assert "load_half(HALF)" in text
    assert text.count("load_tracking(") == 1  # the one call, on load_half's ids
    assert "_read_tracking" not in text and '"sport=football"' not in text
    assert "frames_attacking" not in text


def test_cli_wires_runs_effect_and_freeze() -> None:
    args = build_parser().parse_args(["runs", "effect", "--check"])
    assert args.check and args.runs_command == "effect"
    assert args.data_dir == data_root() and args.reports_dir == Path("reports")
    args = build_parser().parse_args(["runs", "freeze", "--date", "2026-10-12"])
    assert args.runs_command == "freeze" and args.date == "2026-10-12"
    assert args.reports_dir == Path("reports")


# --- the versioned file -----------------------------------------------------------------------


def _versioned() -> dict[str, object]:
    return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))


def test_the_versioned_effect_is_sealed_and_answers_to_the_probe_and_the_protocol() -> None:
    payload = _versioned()
    assert sealed(payload)
    assert consistency_problems(payload) == []
    e = payload["effect"]
    assert e["task"] == 50 and e["written"] == candidates.WRITTEN
    assert e["matches"] == load_half("calibration")
    assert e["inputs"]["subtypes"] == PROBABLE
    assert e["probe_section_sha256"] == section_sha256(payload["probe"])
    assert e["code_tree_sha"] != payload["probe"]["code_tree_sha"]  # task 50's tree, not 49's
    head = subprocess.run(
        ["git", "-C", str(PIPELINE), "rev-parse", f"HEAD:{data.CODE_IN_REPO}"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    assert len(head) == 40


def test_the_versioned_verdict_is_pinned() -> None:
    """The figures of task 50 as the plan records them: a change is a change of what the
    freeze records and must show here, never only in the JSON."""
    e = _versioned()["effect"]
    rows = {r["subtype"]: r for r in e["per_subtype"]}
    assert list(rows) == PROBABLE
    for r in rows.values():
        assert r["marker"]["pooled"]["p"] <= BAR_P
        assert r["marker"]["pooled"]["same_sign_matches"] >= 8
        assert r["verdict"]["passes_bar"]
    assert e["candidates"] == PROBABLE
    assert e["verdict"]["M5a"] == {
        "rule": "zero candidates -> P5 dies, the held-out half is never opened",
        "candidates": 3,
        "dies": False,
    }
    assert e["verdict"]["alive"] is True
