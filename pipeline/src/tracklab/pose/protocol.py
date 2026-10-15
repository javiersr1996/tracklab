"""The P6 protocol as code (task 60 of tasks/todo.md, phase B2).

`tracklab pose protocol` writes `reports/pose_protocol.json` in stage `design`: the protocol
that stands after the six reviews of phase A ("Protocolo que vale tras las seis pasadas"), every
number from the constants of the code that applies it (`gait`, `sweep`, `criteria` and the
ones below), so a threshold moved by hand shows as a diff to `--check` (D13 of the sister
repo). The sha256 of the versioned sweep (`reports/pose_sweep.json`, committed before the probe)
and of the coverage (`reports/pose_coverage.json`, what is already seen of 1996435) sit inside
`design`, so inside `fingerprint`. Write mode never overwrites a frozen file; the freeze, and the
check of a frozen file, are the second part of phase B2.

`evidence` holds the denominators of M1 per match (players the file lists, players with a
pose), counted through `data.CountingHandle`, which returns integers and reads no position. The
status line says how much backed them: `FULL 2/2` when both matches' bronze is whole and they
were recounted, `PARTIAL k/2` when the rest travelled in the file as written (the CI fixtures
hold a slice of 1925299, so `PARTIAL 0/2`). A PARTIAL pass is a pass on the file's consistency,
never on the data.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any

from tracklab.pose import criteria, gait, sweep
from tracklab.pose.coverage import COVERAGE_NAME, MANIFEST, match_ids
from tracklab.pose.data import STAGE_DESIGN, STAGE_FROZEN, CountingHandle
from tracklab.pose.jsonl import JOINTS
from tracklab.runs.protocol import fingerprint, seal

PROTOCOL_NAME = "pose_protocol.json"
SCHEMA_VERSION = 1
WRITTEN = "2026-10-15"
TASK = 60
CALIBRATION = (1925299,)
CONFIRMATION = (1996435,)
FPS = 25.0  # the Body Pose files' rate (bronze/football/bodypose.py, the README's 25 fps)
BAND_LOW_M_S = 3.0  # the plan's hypotheses, fixed by the second review; no provider threshold
BAND_HIGH_M_S = 5.5
P_DIES_NOISE_MIN = 0.95
HALF_IQR = 0.5
HEAD_TAIL_FRAMES = 5  # two native samples of the 10 fps tracking interpolated to 25 (review 6b)
PLATEAU_REL = 0.10  # (f): descriptive, no source, read by no rule
NUMPY_VERSION = importlib.metadata.version("numpy")


def band(speed_m_s: float) -> str:
    """The band of a window by its `gait.mean_speed_m_s`: below, low or high."""
    if speed_m_s >= BAND_HIGH_M_S:
        return "high"
    return "low" if speed_m_s >= BAND_LOW_M_S else "below"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def design(sweep_sha256: str, coverage_sha256: str, ids: list[int]) -> dict[str, Any]:
    if sorted(ids) != sorted(CALIBRATION + CONFIRMATION):
        raise ValueError(f"the manifest's Body Pose matches are {ids}, not the split's")
    grid = sweep.PROTOCOL
    ankles = [JOINTS[j] for j in gait.ANKLES]
    return {
        "question": (
            "Cadence and step length in the high-speed stretches, per match and per player, "
            "with their propagated error, from the Body Pose of two full matches."
        ),
        "unit": (
            "the player: the windows of one player are not independent, so they are reported "
            "per player; there is no null, P6 measures and tests no effect"
        ),
        "split": {
            "calibration": list(CALIBRATION),
            "confirmation": list(CONFIRMATION),
            "rule": "the plan's (task 60): 1925299 calibrates, 1996435 confirms",
            "matches": sorted(ids),
            "source": str(MANIFEST.as_posix()),
        },
        "seen_of_confirmation": {
            "seen": [
                "from P5 (runs_protocol.json, design.split.calibration): its whole tracking at "
                "10 fps, its runs, its speeds and P5's metric per match",
                "from task 57: the bytes and sha of the zip",
                "from task 58: pose_coverage.json whole (frames, coverage per period and player, "
                "players, stretches >= 25, 37 and 50 frames per player, mae per joint, the "
                "range of z)",
            ],
            "not_seen": (
                "no coordinate of any joint of 1996435, and none of its x, y at 25 fps of the "
                "pose file"
            ),
            "consequence": (
                "the speed bands are not blind to 1996435 (P5 saw its speeds); what M4 confirms "
                "blind is the kinematics of the pose"
            ),
            "coverage": {"file": f"pipeline/reports/{COVERAGE_NAME}", "sha256": coverage_sha256},
        },
        "signals": {
            "s": "(lAnkle - rAnkle) . d, d the unit (x, y) displacement of the window",
            "h": "z(lAnkle) - z(rAnkle)",
            "centred_on": "midHip, frame by frame (only differences inside one body survive)",
            "cadence": "gait.cadence_hz of each signal: 2 x fps / the lag of the first peak",
            "nan_rule": (
                "the first local maximum with r[k] > 0 after the first r[k] < 0; NaN if there "
                "is none or if r[k] / r[0] <= band_z / sqrt(n - k) (reading A)"
            ),
            "band_z": gait.BAND_Z,
            "ankle_separation_m": "the amplitude of s, the mean of its maxima, with its sd",
            "step_length_m": "mean_speed_m_s / cad_s, the only step length",
            "fps": FPS,
        },
        "windows": {
            "widths": list(grid.widths),
            "caps_cm": list(grid.caps_cm),
            "cap_joints": ankles,
            "tiling": "from the start of each stretch, without overlap (gait.windows)",
            "inside_one_period": True,
            "w_and_cap": "chosen by rule_w_cap, blind, after the probe; written at the freeze",
        },
        "bands": {
            "low_m_s": [BAND_LOW_M_S, BAND_HIGH_M_S],
            "high_m_s_from": BAND_HIGH_M_S,
            "low_rule": f"{BAND_LOW_M_S} <= v < {BAND_HIGH_M_S}",
            "assigned_by": (
                "mean_speed_m_s: the net displacement of the pose file's x, y over "
                "(W - 1) / fps, the denominator of v / cadence"
            ),
            "source": (
                "the plan's hypotheses, fixed by the second review; no provider threshold is in "
                "the repository; the probe's (f) reports their kinematics and moves nothing"
            ),
        },
        "sweep": {
            "file": f"pipeline/reports/{sweep.SWEEP_NAME}",
            "sha256": sweep_sha256,
            "bar": {
                "p95_rel_err_max": sweep.BAR_P95,
                "nan_s_max": sweep.BAR_NAN,
                "rho": sweep.BAR_RHO,
                "cadences_hz": list(grid.cadences_hz),
                "rule": "a (W, cap) cell passes when every cadence meets the bar at rho 0",
            },
            "noise_twin": "one per (W, cap, rho), the same body travelling with no gait",
            "rhos": list(grid.rhos),
            "windows_per_row": grid.windows_s,
            "separation_m": round(grid.separation_m, 6),
            "seed": grid.seed,
        },
        "rule_w_cap": {
            "rule": (
                "among the cells that pass the bar in the sweep and in which M1 + M2 kill the "
                "noise, the one of least W and, at equal W, of greatest cap; if none, P6 dies"
            ),
            "kills_the_noise": (
                "M1 and M2 simulated as they are applied (criteria.simulate_m1_m2) with the "
                "counts of admitted windows per player and band of the probe's (a), cap on the "
                "ankles, both periods summed, resampling windows of the noise twin of (W, cap, "
                "rho) in both bands, NaN included, each window with its Monte Carlo copies "
                "(sweep.noise_pool): P(P6 dies | noise) >= p_dies_min in each rho"
            ),
            "p_dies_min": P_DIES_NOISE_MIN,
            "reps": criteria.REPS,
            "draws": gait.DRAWS,
            "seed": criteria.SEED,
            "if_none": "P6 dies: the instrument cannot be told from the noise",
            "reads": "the probe's (a) and the sweep, never a cadence or a discrepancy of data",
        },
        "monte_carlo": {
            "noise": (
                "every joint of every frame N(0, its p90_mae_cm) per axis; the x, y of the file "
                "carry no predicted error and get none"
            ),
            "draws": gait.DRAWS,
            "seed_per_window": (
                f"numpy default_rng([{gait.SEED}, match_id, player_id, first frame of the "
                "window]): every window its own stream (record of phase B1)"
            ),
            "invalid_draw": (
                "in a player's draw, the median ignores his NaN windows (nanmedian); a draw "
                "with all of them NaN is not valid; the sd (ddof 1) is over the valid draws, "
                "and fewer than 2 valid draws count as an infinite sd"
            ),
        },
        "numbers": {
            "min_players": criteria.MIN_PLAYERS,
            "min_windows": criteria.MIN_WINDOWS,
            "sign_share": criteria.SIGN_SHARE,
            "half_iqr": HALF_IQR,
            "precision_windows": (
                f"the first {criteria.MIN_WINDOWS} high windows finite in s, by frame"
            ),
            "iqr": "numpy linear-interpolation percentiles 75 minus 25",
        },
        "death_criteria": {
            "noise": "rule_w_cap finds no cell -> P6 dies: the instrument is not told from noise",
            "M1": (
                f"in 1925299, fewer than {criteria.MIN_PLAYERS} players with >= "
                f"{criteria.MIN_WINDOWS} windows finite in s in the high band -> P6 dies: the "
                "coverage does not pay for the question"
            ),
            "M2": (
                f"among the players with >= {criteria.MIN_WINDOWS} windows finite in s in both "
                f"bands (n printed; n < {criteria.MIN_PLAYERS} dies by coverage), fewer than "
                f"{criteria.SIGN_SHARE} with cad_s high > cad_s low (medians of their finite "
                "windows) -> dies; or, among the players of M1, the median of the propagated sd "
                f"of the median of their first {criteria.MIN_WINDOWS} finite high windows above "
                f"{HALF_IQR} x the IQR between players of that same median -> dies: the "
                "instrument does not see even what is forced"
            ),
            "M3": (
                "no verdict (decision of Javier, fourth review): per player, the median of "
                "|cad_s - cad_h| and the share of NaN in h in the high band, published with the "
                "sweep's rows of h beside it, without a propagated error"
            ),
            "M4": (
                "M2 in 1996435 with the same numbers; its second clause compares the propagated "
                f"sd of 1996435 with {HALF_IQR} x the IQR of 1925299, written as a number "
                "before 1996435 is opened, never with the IQR of its own squad; if its admitted "
                "windows (before the NaN rule) do not reach any of the minima of M1 and M2, "
                "'not evaluable by coverage' and P6 is unreplicated, not dead; 'replication "
                "failed' only if they reach them and M2 fails"
            ),
            "blind_spots": [
                "the forward foot called left in every frame doubles cad_s and cad_h together "
                "(sweep row swap)",
                "s leaning towards z (sweep rows lean, 10 and 20 degrees)",
            ],
        },
        "probe": {
            "match": list(CALIBRATION),
            "first_time": [
                "(a) admitted windows (before the NaN rule) per player, period and band for "
                "every W and cap, cap on the ankles and on ankles and heels",
                "(a') sd of h(t) and of s(t) per band, W and cap, with the ankles' mae",
                "(b) the distribution of mae per joint",
                f"(f) per band: the speed of the first and last {HEAD_TAIL_FRAMES} frames, "
                f"accelerating / plateau / braking (tail against head within +-{PLATEAU_REL} "
                "of the window's speed: descriptive, read by no rule), path / chord",
                "(g) z(nose) - z(midHip) and z(ankles) - z(midHip) per player: sign and median",
                "rule_w_cap, with its figures",
            ],
            "second_time": [
                "after the freeze: (c) cad_s per player and band, the sign of high - low; (d) "
                "the concordance of M3; (e) the propagated error against the spread between "
                "players; the NaN rates; the distribution of cad_s; the slope of h on s by "
                "heading; M1 and M2"
            ],
        },
        "order": [
            "sweep (committed)",
            "protocol in design (committed)",
            "probe, first time (committed)",
            "rule_w_cap",
            "frozen",
            "M1 and M2 on 1925299",
            "1996435: M2 (M4)",
        ],
        "dependencies": {"numpy": NUMPY_VERSION},
    }


def build_protocol(
    sweep_sha256: str, coverage_sha256: str, ids: list[int], evidence: dict[str, Any]
) -> dict[str, Any]:
    design_payload = design(sweep_sha256, coverage_sha256, ids)
    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "stage": STAGE_DESIGN,
            "written": WRITTEN,
            "plan": "tasks/todo.md, P6, task 60, 'Protocolo que vale tras las seis pasadas'",
            "fingerprint": fingerprint(design_payload),
            "design": design_payload,
            "evidence": {
                "denominators": {
                    "what": (
                        "per match, the players the file lists and the players with a pose: "
                        "the denominator printed beside M1; counted, never a position"
                    ),
                    "per_match": evidence,
                }
            },
            "history": [
                {
                    "stage": STAGE_DESIGN,
                    "task": TASK,
                    "date": WRITTEN,
                    "note": (
                        "phase B2, first part: the protocol after the six reviews, as code, "
                        "after the sweep and before the probe"
                    ),
                }
            ],
        }
    )


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def denominators(data_dir: Path, match_id: int) -> dict[str, int] | None:
    """Players listed and players with a pose, or None when the bronze is absent or a slice."""
    handle = CountingHandle(data_dir, match_id)
    if not handle.exists() or not handle.is_whole():
        return None
    return {
        "players_listed": len(handle.frames_present()),
        "players_with_pose": len(handle.frames_posed()),
    }


def run_pose_protocol(
    data_dir: Path, reports_dir: Path, *, check: bool = False, manifest_path: Path = MANIFEST
) -> int:
    path = reports_dir / PROTOCOL_NAME
    ids = match_ids(manifest_path)
    inputs = [reports_dir / sweep.SWEEP_NAME, reports_dir / COVERAGE_NAME]
    missing = [p for p in inputs if not p.is_file()]
    if missing:
        print(f"pose protocol: {missing[0]} is missing")
        return 1
    sweep_sha, coverage_sha = (file_sha256(p) for p in inputs)
    counted = {str(m): denominators(data_dir, m) for m in ids}
    done = sum(c is not None for c in counted.values())
    status = f"FULL {done}/{len(ids)}" if done == len(ids) else f"PARTIAL {done}/{len(ids)}"

    if not check:
        if path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("stage") != (
            STAGE_DESIGN
        ):
            print(f"pose protocol: {path} is not in stage design and is not rewritten (D13)")
            return 1
        if done != len(ids):
            print(f"pose protocol: whole bronze for {done} of {len(ids)} matches; nothing written")
            return 1
        payload = build_protocol(sweep_sha, coverage_sha, ids, counted)
        reports_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(render(payload), encoding="utf-8", newline="\n")
        print(_summary(payload, status))
        print(f"pose protocol: {path} ({path.stat().st_size} bytes)")
        return 0

    if not path.is_file():
        print(f"pose protocol --check: {path} is missing")
        return 1
    text = path.read_text(encoding="utf-8")
    current = json.loads(text)
    if current.get("stage") != STAGE_DESIGN:
        stage = current.get("stage")
        what = (
            "the check of a frozen file is written with the freeze" if stage == STAGE_FROZEN else ""
        )
        print(f"pose protocol --check: stage {stage!r} is not checked here; {what or 'unknown'}")
        return 1
    written = (current.get("evidence") or {}).get("denominators", {}).get("per_match", {})
    evidence = {m: c if c is not None else written.get(m) for m, c in counted.items()}
    expected = build_protocol(sweep_sha, coverage_sha, ids, evidence)
    print(_summary(expected, status))
    if render(expected) != text:
        print(f"pose protocol --check: {path} differs from what the code writes")
        return 1
    print(
        f"pose protocol --check: {path} matches ({status}: {done} match(es) recounted, "
        f"{len(ids) - done} as written; stage {STAGE_DESIGN})"
    )
    return 0


def _summary(payload: dict[str, Any], status: str) -> str:
    split = payload["design"]["split"]
    per_match = payload["evidence"]["denominators"]["per_match"]
    listed = {m: (c or {}).get("players_listed") for m, c in per_match.items()}
    return (
        f"pose protocol: bronze={status} calibration={split['calibration']} "
        f"confirmation={split['confirmation']} players_listed={listed} "
        f"sweep={payload['design']['sweep']['sha256'][:12]} "
        f"fingerprint={payload['fingerprint'][:12]}"
    )
