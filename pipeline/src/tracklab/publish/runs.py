"""`tracklab publish runs`: `web/public/data/runs.json` and the hook's two clips under
`web/public/data/runs/` (task 52 of tasks/todo.md, the dead branch of P5, decisions 7 and 8).

P5 died at M5a (task 50): zero candidates, the held-out half never opened. `/runs` is
published dead, in the same route and with the same title, and this file holds what it shows:

* **The figures** are copied from `reports/runs_protocol.json`, `runs_calibration.json` and
  `runs_coverage.csv`, never computed here and never typed: `figures` reads the three files and
  nothing else, so it needs no warehouse. Where this file writes a word that promises a
  criterion (`dead_at`, `post hoc`, `opened`), the word is derived from the artefact that
  holds the criterion; if the artefact does not support it, `figures` raises. The alive branch
  (task 51 run) is not built: the plan has no `runs.json` for it before task 51 exists.
* **The hook** (decision 7): one run and its placebo from the same calibration match, in the
  replay format of P1 (`web/lib/replay/schema.json`), over `[instant - 2 s, instant + 2 s]` for
  each leg, so the page can show the runner already running at `t_c` and the pre-trend window.
  The pair is chosen by rule (decision 8), never by maximum: among the pairs of the largest
  subtype that passed the bar before M3, with both windows inside the tracking, the one whose
  marker effect is closest to the median of that subtype's pairs, ties to the lowest
  (match_id, run_id). The tracking is read through `data.load_half("calibration")` and
  `windows.load_tracking`, which refuse a held-out match; the clip frames are read from silver
  by the calibration match id alone, after `require_readable` has said yes.

The defence's displacement the page paints is published beside each clip: for every opponent,
the residual displacement along the run's direction (the protocol's statistic, the same one
that makes the marker's value) over `[instant, instant + W]`.

`--check` regenerates the figures from the reports and compares bytes. With the calibration
frames in the warehouse it regenerates the hook and the clips too and compares bytes; without
them it verifies the hook as written (the clips' sizes and hashes, and the rule's inputs
against the reports) and says PARTIAL, as `runs effect --check` does.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from tracklab.publish import possessions
from tracklab.runs import effect, windows
from tracklab.runs.coverage import has_frames
from tracklab.runs.data import load_half, match_halves, require_readable
from tracklab.runs.placebo import placebo_instants
from tracklab.runs.protocol import EFFECT_WINDOW_S, VELOCITY_WINDOW_S
from tracklab.runs.windows import EFFECT_FRAMES, VELOCITY_FRAMES, PairEffect, Run

SCHEMA_VERSION = 1
RUNS_JSON = "runs.json"
CLIPS_DIR = "runs"
MAX_CLIP_BYTES = possessions.MAX_BYTES  # P1's cap; the clips are measured against it
ROUND_NDIGITS = 4

PROTOCOL_FILE = "runs_protocol.json"
CALIBRATION_FILE = "runs_calibration.json"
COVERAGE_FILE = "runs_coverage.csv"
HELD_OUT_FILE = "runs_heldout.json"

# The order the plan lists the death criteria in (the protocol's `death_criteria`).
STAGES = ("M1", "M2", "M3", "M4", "M5a", "M5b")
HOOK_RULE = (
    "among the pairs of the largest subtype that passed the bar before M3, with both windows "
    "[instant - 2 s, instant + 2 s] inside the tracking, the one whose marker effect is "
    "closest to the median marker effect of that subtype's pairs in the calibration half; "
    "ties go to the lowest (match_id, run_id); never the maximum"
)


class RunsPublishError(RuntimeError):
    """The artefacts do not support what `runs.json` would say, or the rule has no pair."""


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _number(text: str) -> int | float | str:
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def coverage_rows(path: Path) -> list[dict[str, Any]]:
    """`runs_coverage.csv` as typed rows (counts and detection fractions of both halves)."""
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: _number(v) for k, v in row.items()} for row in csv.DictReader(handle)]


# --- the figures: reports in, JSON out -----------------------------------------------------


def _stage_states(calibration: dict[str, Any], design: dict[str, str]) -> dict[str, dict[str, Any]]:
    probe, effect_section = calibration["probe"], calibration["effect"]
    m1, m2 = probe["verdict"]["M1"], probe["verdict"]["M2"]
    subtypes = effect_section["per_subtype"]
    m3 = [{"subtype": s["subtype"], **s["verdict"]["M3"]} for s in subtypes]
    m4 = [{"subtype": s["subtype"], **s["verdict"]["M4"]} for s in subtypes]
    m5a = effect_section["verdict"]["M5a"]

    def leaving(rows: list[dict[str, Any]]) -> str:
        n = sum(bool(r["leaves"]) for r in rows)
        return (
            "all_subtypes_leave"
            if n == len(rows)
            else ("no_subtype_leaves" if n == 0 else "some_subtypes_leave")
        )

    return {
        "M1": {
            "state": "dead" if m1["dies"] else "passed",
            "rule": design["M1"],
            "figures": {k: v for k, v in m1.items() if k not in ("rule", "dies")}
            | {"probable": probe["power"]["probable"]},
        },
        "M2": {
            "state": "dead" if m2["dies"] else "passed",
            "rule": design["M2"],
            "figures": {"instrument": probe["instrument"]["marker"]["pooled"]},
        },
        "M3": {"state": leaving(m3), "rule": design["M3"], "figures": {"subtypes": m3}},
        "M4": {"state": leaving(m4), "rule": design["M4"], "figures": {"subtypes": m4}},
        "M5a": {
            "state": "dead" if m5a["dies"] else "passed",
            "rule": design["M5a"],
            "figures": {"candidates": m5a["candidates"]},
        },
    }


def dead_at(stages: dict[str, dict[str, Any]]) -> str:
    """The first stage in the plan's order whose state is `dead`."""
    for name in STAGES:
        if stages.get(name, {}).get("state") == "dead":
            return name
    raise RunsPublishError(
        "no stage is dead in the artefacts: the alive branch of runs.json is not built"
    )


def figures(reports_dir: Path) -> dict[str, Any]:
    """Everything `runs.json` holds except the hook, from the three reports alone."""
    protocol = _load(reports_dir / PROTOCOL_FILE)
    calibration = _load(reports_dir / CALIBRATION_FILE)
    coverage = coverage_rows(reports_dir / COVERAGE_FILE)
    probe, effect_section = calibration["probe"], calibration.get("effect")
    if effect_section is None:
        raise RunsPublishError(f"{CALIBRATION_FILE} has no effect section: run task 50 first")
    if calibration["protocol"]["fingerprint"] != protocol["fingerprint"]:
        raise RunsPublishError("the calibration file answers another protocol fingerprint")
    stages = _stage_states(calibration, protocol["design"]["death_criteria"])
    dead = dead_at(stages)
    stages["M5b"] = {
        "state": "not_reached",
        "rule": protocol["design"]["death_criteria"]["M5b"],
        "figures": {"died_at": dead},
    }
    kinematics = effect_section["kinematics"]
    if kinematics.get("post_hoc") is not True:
        raise RunsPublishError("the kinematics section is not labelled post hoc")
    # the other half is named by the coverage file's own `half` column and its ids are
    # checked against the counting door of `data` (ids and counts, never an outcome)
    halves = match_halves()
    unopened = [r for r in coverage if r["half"] != "calibration"]
    names = {r["half"] for r in unopened}
    if len(names) != 1 or {r["match_id"] for r in unopened} != {
        m for m, h in halves.items() if h != "calibration"
    }:
        raise RunsPublishError("the coverage file and the protocol disagree on the other half")
    history = protocol["history"]
    frozen = protocol.get("frozen")
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": {
            "protocol": f"pipeline/reports/{PROTOCOL_FILE}",
            "calibration": f"pipeline/reports/{CALIBRATION_FILE}",
            "coverage": f"pipeline/reports/{COVERAGE_FILE}",
        },
        "status": "dead",
        "dead_at": dead,
        "stages": stages,
        "funnel": {"probe": probe["funnel"], "coverage": coverage},
        "effect_by_subtype": effect_section["per_subtype"],
        "instrument": probe["instrument"],
        "design_checks": {k: probe[k] for k in ("cadence", "run_length", "placebo_design", "units")}
        | {"standardisation": probe["standardisation"]},
        "power": probe["power"],
        "null": probe["null"],
        "post_hoc_kinematics": {"label": "post hoc", **kinematics},
        "protocol": {
            "stage": protocol["stage"],
            "stages_seen": sorted({h["stage"] for h in history}),
            "frozen": frozen is not None,
            "fingerprint": protocol["fingerprint"],
            "content_sha256": protocol["content_sha256"],
            "history": history,
            "calibration_sha256": calibration["content_sha256"],
            "question": protocol["design"]["question"],
            "quantities": protocol["design"]["quantities"],
            "bar": protocol["design"]["bar"],
        },
        "never_opened": {
            "half": names.pop(),
            "opened": (reports_dir / HELD_OUT_FILE).exists() or frozen is not None,
            "match_ids": sorted(r["match_id"] for r in unopened),
            "counts": unopened,
        },
    }


# --- the hook: one pair and its two clips ----------------------------------------------------


def choose_pair(pairs: Sequence[PairEffect], median_m: float) -> PairEffect:
    """The pair whose marker effect is closest to `median_m`; ties to the lowest
    (match_id, run_id). By rule, never by maximum (decision 8)."""
    if not pairs:
        raise RunsPublishError("no pair to choose from")
    return min(pairs, key=lambda p: (abs(p.marker_m - median_m), p.match_id, p.run_id))


def hook_subtype(effect_section: dict[str, Any]) -> str:
    """The largest subtype that passed the bar before M3 (decision 8: 'subtype vivo')."""
    passed = [s for s in effect_section["per_subtype"] if s["verdict"]["passes_bar"]]
    if not passed:
        raise RunsPublishError("no subtype passed the bar: the hook has no subtype to draw")
    return str(max(passed, key=lambda s: (s["pairs"], s["subtype"]))["subtype"])


def _window_inside(t: windows.MatchTracking, period: int, instant: int) -> bool:
    lo, hi = instant - EFFECT_FRAMES, instant + EFFECT_FRAMES
    start, end = t.period_frames[period]
    return start <= lo and hi <= end and all(t.frame_present(f) for f in range(lo, hi + 1))


@dataclass(frozen=True)
class SubtypePairs:
    """Every pair of one subtype in the calibration half, and which ones have both clip
    windows inside the tracking."""

    pairs: tuple[PairEffect, ...]
    eligible: tuple[PairEffect, ...]


def subtype_pairs(data_dir: Path, subtype: str) -> SubtypePairs:
    pairs: list[PairEffect] = []
    eligible: list[PairEffect] = []
    for match_id in load_half("calibration"):
        t = windows.load_tracking(data_dir, match_id)
        runs = [r for r in windows.load_runs(data_dir, match_id) if r.subtype == subtype]
        instants = placebo_instants(data_dir, [match_id], windows.PLACEBO_RULE)
        for pair in windows.pair_effects(t, runs, instants):
            pairs.append(pair)
            run = next(r for r in runs if r.event_id == pair.run_id)
            if _window_inside(t, run.period, pair.t_c) and _window_inside(
                t, pair.placebo_period, pair.placebo_instant
            ):
                eligible.append(pair)
        del t
    return SubtypePairs(tuple(pairs), tuple(eligible))


def _r(value: float) -> float:
    return round(float(value), ROUND_NDIGITS)


def defence_displacement(
    t: windows.MatchTracking, run: Run, period: int, instant: int, direction: Any
) -> list[dict[str, Any]]:
    """For each opponent with a position at t - V, t and t + W: the residual displacement
    along the run's direction (`effect.residual_displacement`, the protocol's statistic), in
    the attack frame of the leg's own period."""
    sign = t.attack_sign[(period, run.team)]
    rows = [
        instant - VELOCITY_FRAMES - t.frame0,
        instant - t.frame0,
        instant + EFFECT_FRAMES - t.frame0,
    ]
    marker = windows.leg_marker(t, run, period, instant)
    out = []
    for i, (entity, team) in enumerate(zip(t.entities, t.team, strict=True)):
        if team == run.team:
            continue
        xy = [np.array([sign * t.x[r, i], sign * t.y[r, i]]) for r in rows]
        residual = effect.residual_displacement(
            *xy, window_s=EFFECT_WINDOW_S, velocity_s=VELOCITY_WINDOW_S
        )
        value = effect.project(residual, direction)
        if np.isfinite(value):
            out.append(
                {
                    "entity_id": entity,
                    "is_goalkeeper": bool(t.is_goalkeeper[i]),
                    "is_marker": i == marker,
                    "displacement_m": _r(value),
                }
            )
    return sorted(out, key=lambda d: str(d["entity_id"]))


def _clip(
    con: duckdb.DuckDBPyConnection,
    t: windows.MatchTracking,
    run: Run,
    period: int,
    instant: int,
    clip_id: str,
) -> dict[str, Any]:
    require_readable(t.match_id)  # the frames below are read by this id alone
    match = f"fb:{t.match_id}"
    lo, hi = instant - EFFECT_FRAMES, instant + EFFECT_FRAMES
    entities = possessions._entities(con, match, lo, hi)
    index = {e["entity_id"]: e["i"] for e in entities}
    return {
        "schema_version": possessions.SCHEMA_VERSION,
        "possession_id": clip_id,
        "sport": "football",
        **possessions._match_block(con, match),
        **possessions._sport_block(con, "football"),
        "team_in_possession": run.team,
        "attack_sign": possessions._attack_sign(con, match, period, run.team),
        "entities": entities,
        "frames": possessions._frames(con, match, lo, hi, index),
    }


def _write_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def hook(data_dir: Path, effect_section: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """The hook block of `runs.json` and the text of each clip, by file name."""
    subtype = hook_subtype(effect_section)
    section = next(s for s in effect_section["per_subtype"] if s["subtype"] == subtype)
    found = subtype_pairs(data_dir, subtype)
    if len(found.pairs) != section["pairs"]:
        raise RunsPublishError(
            f"{len(found.pairs)} pairs of {subtype} recomputed, the report says {section['pairs']}"
        )
    median = float(np.median([p.marker_m for p in found.pairs]))
    mean = _r(np.mean([p.marker_m for p in found.pairs]))
    if mean != section["marker"]["pooled"]["mean_m"]:
        raise RunsPublishError(f"the pairs of {subtype} do not reproduce the reported mean")
    if not found.eligible:
        raise RunsPublishError(f"no pair of {subtype} has both windows inside the tracking")
    pair = choose_pair(found.eligible, median)

    t = windows.load_tracking(data_dir, pair.match_id)
    run = next(r for r in windows.load_runs(data_dir, pair.match_id) if r.event_id == pair.run_id)
    direction = windows.run_direction(t, run)
    assert direction is not None  # the pair exists, so the run has a direction
    legs = (("run", run.period, pair.t_c), ("placebo", pair.placebo_period, pair.placebo_instant))
    con = duckdb.connect()
    possessions.register_candidate_views(con, data_dir)
    possessions.register_payload_views(con, data_dir)
    clips: dict[str, str] = {}
    entries = []
    for role, period, instant in legs:
        clip_id = f"fb:run-hook:{pair.match_id}:{pair.run_id}:{role}"
        payload = _clip(con, t, run, period, instant, clip_id)
        name = f"{CLIPS_DIR}/{possessions.safe_filename(clip_id)}"
        text = _write_text(payload)
        clips[name] = text
        values = windows.quantities(t, run, period, instant, direction)
        marker = windows.leg_marker(t, run, period, instant)
        assert values is not None and marker is not None
        defence = defence_displacement(t, run, period, instant, direction)
        in_defence = [d for d in defence if d["is_marker"]]
        if len(in_defence) != 1 or abs(in_defence[0]["displacement_m"] - values[0]) > 1e-3:
            raise RunsPublishError("the painted marker displacement is not the protocol's")
        entries.append(
            {
                "role": role,
                "file": name,
                "bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "possession_id": clip_id,
                "period": period,
                "instant_frame": instant,
                "frame_lo": instant - EFFECT_FRAMES,
                "frame_hi": instant + EFFECT_FRAMES,
                "frames": len(payload["frames"]),
                "instant_index": EFFECT_FRAMES,
                "window_s": [-EFFECT_WINDOW_S, EFFECT_WINDOW_S],
                "marker_entity_id": t.entities[marker],
                "marker_displacement_m": _r(values[0]),
                "defence": defence,
            }
        )
    return (
        {
            "rule": HOOK_RULE,
            "subtype": subtype,
            "subtype_pairs": len(found.pairs),
            "eligible_pairs": len(found.eligible),
            "subtype_median_marker_m": _r(median),
            "subtype_mean_marker_m": mean,
            "pair": {
                "match_id": pair.match_id,
                "run_id": pair.run_id,
                "possession_id": pair.possession_id,
                "runner_entity_id": run.runner,
                "team_id": run.team,
                "marker_effect_m": _r(pair.marker_m),
                "distance_to_median_m": _r(abs(pair.marker_m - median)),
                "direction": [_r(direction[0]), _r(direction[1])],
            },
            "clips": entries,
        },
        clips,
    )


# --- writing and checking ----------------------------------------------------------------------


def _clip_problems(out_dir: Path, block: dict[str, Any]) -> list[str]:
    problems = []
    for entry in block["clips"]:
        path = out_dir / entry["file"]
        if not path.is_file():
            problems.append(f"{entry['file']} is missing")
            continue
        data = path.read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            problems.append(f"{entry['file']} is not the clip runs.json describes")
    clips_dir = out_dir / CLIPS_DIR
    wanted = {Path(e["file"]).name for e in block["clips"]}
    extra = sorted(p.name for p in clips_dir.glob("*.json") if p.name not in wanted)
    if extra:
        problems.append(f"{CLIPS_DIR}/ holds files runs.json does not name: {extra}")
    return problems


def run_publish_runs(
    data_dir: Path, reports_dir: Path, out_dir: Path, *, check: bool = False
) -> int:
    try:
        base = figures(reports_dir)
    except (OSError, KeyError, RunsPublishError) as error:
        print(f"publish runs: {error!r}")
        return 1
    calibration = _load(reports_dir / CALIBRATION_FILE)
    matches = load_half("calibration")
    whole = all(has_frames(data_dir, m) for m in matches)
    path = out_dir / RUNS_JSON
    if check:
        if not path.is_file():
            print(f"publish runs --check: {RUNS_JSON} is missing")
            return 1
        current = _load(path)
        problems = []
        if render({k: v for k, v in current.items() if k != "hook"}) != render(base):
            problems.append("figures differ from the reports")
        if whole:
            try:
                block, clips = hook(data_dir, calibration["effect"])
            except RunsPublishError as error:
                return _fail(error)
            if render(current) != render({**base, "hook": block}):
                problems.append("hook differs from what the code writes")
            for name, text in clips.items():
                clip = out_dir / name
                if not clip.is_file() or clip.read_bytes() != text.encode("utf-8"):
                    problems.append(f"{name} differs from what the code writes")
            status = f"FULL {len(matches)}/{len(matches)} recomputed and equal"
        else:
            problems += _clip_problems(out_dir, current["hook"])
            subtype = hook_subtype(calibration["effect"])
            if current["hook"]["subtype"] != subtype:
                problems.append("the hook's subtype is not the one the rule picks")
            status = (
                "PARTIAL: frames not at hand, figures recomputed from the reports, "
                "clips verified by size and hash"
            )
        if problems:
            print(f"publish runs --check: {RUNS_JSON} " + "; ".join(problems))
            return 1
        print(f"publish runs --check: {RUNS_JSON} matches ({status})")
        return 0
    if not whole:
        print(f"publish runs: silver frames for the calibration matches are not under {data_dir}")
        return 1
    try:
        block, clips = hook(data_dir, calibration["effect"])
    except RunsPublishError as error:
        return _fail(error)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = out_dir / CLIPS_DIR
    clips_dir.mkdir(parents=True, exist_ok=True)
    for stale in clips_dir.glob("*.json"):  # a previous selection's clips would ship
        stale.unlink()
    for name, text in clips.items():
        (out_dir / name).write_bytes(text.encode("utf-8"))
    path.write_text(render({**base, "hook": block}), encoding="utf-8", newline="\n")
    sizes = ", ".join(f"{e['file']} {e['bytes']} B" for e in block["clips"])
    print(f"publish runs: {path} ({path.stat().st_size} bytes); {sizes}")
    if any(e["bytes"] >= MAX_CLIP_BYTES for e in block["clips"]):
        print(f"publish runs: a clip is over P1's cap of {MAX_CLIP_BYTES} bytes")
        return 1
    return 0


def _fail(error: Exception) -> int:
    print(f"publish runs: {error}")
    return 1
