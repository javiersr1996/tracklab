"""The P6 protocol as code (task 60 of tasks/todo.md, phase B2).

`tracklab pose protocol` writes `reports/pose_protocol.json` in stage `design`: the protocol
that stands after the six reviews of phase A ("Protocolo que vale tras las seis pasadas"), every
number from the constants of the code that applies it (`gait`, `sweep`, `criteria` and the
ones below), so a threshold moved by hand shows as a diff to `--check` (D13 of the sister
repo). The sha256 of the versioned sweep (`reports/pose_sweep.json`, committed before the probe)
and of the coverage (`reports/pose_coverage.json`, what is already seen of 1996435) sit inside
`design`, so inside `fingerprint`. Write mode never overwrites a file that is not in design.
`freeze_payload` is what `tracklab pose freeze` (`freeze.py`) writes, and on a frozen file
`--check` verifies with `frozen_problems` what the freeze must keep: the design and its
fingerprint, the evidence, the seal, the history, and a `frozen` block whose (W, cap) is the
cell the sealed `pose_calibration.json` beside it chose.

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
from tracklab.runs.protocol import fingerprint, seal, sealed

PROTOCOL_NAME = "pose_protocol.json"
CALIBRATION_NAME = "pose_calibration.json"
SCHEMA_VERSION = 1
WRITTEN = "2026-10-15"
REVISED = "2026-10-15"  # the review of the first part, before the freeze
TASK = 60
CALIBRATION = (1925299,)
CONFIRMATION = (1996435,)
FPS = 25.0  # the Body Pose files' rate (bronze/football/bodypose.py, the README's 25 fps)
BAND_LOW_M_S = 3.0  # the plan's hypotheses, fixed by the second review; no provider threshold
BAND_HIGH_M_S = 5.5
P_DIES_NOISE_MIN = 0.95
SANE_P_DIES_MAX = 0.05  # the mirror of P_DIES_NOISE_MIN
SANE_DELTA_HZ = 0.05  # high - low band of a sane player: no source, PENDIENTE DE CONFIRMAR
SANE_SIGMA_B_HZ = 0.1  # sd between players: no source, PENDIENTE DE CONFIRMAR
SANE_POOL_WINDOWS = 4000  # resampled with replacement; a player draws at most a few hundred
HALF_IQR = 0.5
HEAD_TAIL_FRAMES = 5  # two native samples of the 10 fps tracking interpolated to 25 (review 6b)
PLATEAU_REL = 0.10  # (f): descriptive, no source, read by no rule
NUMPY_VERSION = importlib.metadata.version("numpy")
FREEZE_NOTE = (
    "frozen with the (W, cap) the rule chose in reports/pose_calibration.json (first time "
    "of the probe, no cadence) and the sha of the committed pose/ tree; the design is "
    "untouched, same fingerprint; next, the second time on 1925299 (pose verdict) in a "
    "commit of its own, and only then 1996435"
)


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
            "is_detected": (
                "a pose whose player the provider did not detect in that frame (is_detected "
                "false) enters the windows as delivered: the pose exists and its mae is the "
                "file's; how many there are per match is in pose_coverage.json"
            ),
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
                "among the cells that pass the bar in the sweep (separation 5.5 / 4.3 m), pass it "
                "again at the separation the probe measures, and in which M1 + M2 kill the "
                "noise and spare a sane instrument, the one of least W and, at equal W, of "
                "greatest cap; if none, P6 dies"
            ),
            "adjusted_bar": (
                "per cell and cadence, on the very windows of the sweep's row at rho 0 (same "
                "generator, seed and 40,000 windows), the separation A whose median sd of s "
                "(ddof 0) equals the median sd of s of the probe's (a') in the high band of that "
                "cell (both periods), by bisection; the bar judged again at A; it reads no "
                "cadence and only hardens the bar: a cell must pass both"
            ),
            "spares_the_sane": (
                "M1 and M2 simulated (criteria.simulate_sane) with the same counts on sane pools "
                "of (W, cap, cadence, rho) drawn by the sweep's generator at the adjusted "
                "separation of each band (the low band's from its own (a') sd), "
                f"{SANE_POOL_WINDOWS} windows each, the high ones with their Monte Carlo copies; "
                f"player i runs at c_i = cadence + {SANE_SIGMA_B_HZ} Hz x N(0, 1) in the high band "
                f"and c_i - {SANE_DELTA_HZ} Hz in the low one, a window scaled by c_i / cadence "
                "(the estimator's relative error, not its error at c_i); P(P6 dies | sane) <= "
                "sane_p_dies_max in every cadence and rho; the separation is matched at rho 0, "
                "which at rho > 0 gives a smaller signal (conservative); delta and sigma_b have "
                "no source: PENDIENTE DE CONFIRMAR"
            ),
            "sane_p_dies_max": SANE_P_DIES_MAX,
            "sane_delta_hz": SANE_DELTA_HZ,
            "sane_sigma_b_hz": SANE_SIGMA_B_HZ,
            "sane_pool_windows": SANE_POOL_WINDOWS,
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
            "reads": (
                "the probe's (a) and (a') and the sweep, never a cadence or a discrepancy of data"
            ),
        },
        "monte_carlo": {
            "noise": (
                "every joint of every frame N(0, its p90_mae_cm) per axis; the x, y of the file "
                "carry no predicted error and get none"
            ),
            "draws": gait.DRAWS,
            "seed_per_window": (
                f"gait.window_seed: numpy default_rng([{gait.SEED}, match_id, player_id, first "
                "frame of the window]), every window its own stream (record of phase B1)"
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
                "instrument does not see even what is forced, or the cadence does not rise "
                f"{SANE_DELTA_HZ} Hz between the bands, or the squad does not spread "
                f"{SANE_SIGMA_B_HZ} Hz (the sane instrument the rule asked to survive)"
            ),
            "M3": (
                "no verdict (decision of Javier, fourth review): per player, the median of "
                "|cad_s - cad_h| and the share of NaN in h in the high band, published with the "
                "sweep's rows of h beside it, without a propagated error"
            ),
            "M4": (
                "M2 in 1996435 with the same numbers; its second clause compares the propagated "
                f"sd of 1996435 with {HALF_IQR} x the IQR of 1925299, written as "
                "m4.half_iqr_hz in pose_verdict.json (second time) before 1996435 is opened, "
                "never with the IQR of its own squad; if its admitted "
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
                "after the freeze, tracklab pose verdict, reports/pose_verdict.json in a commit "
                "of its own: (c) cad_s per player and band, the sign of high - low; (d) the "
                "concordance of M3 with the sweep's rows of h; (e) the propagated error "
                "against the spread between players; the NaN rates; the distribution of cad_s "
                "with the sweep's swap rows; the slope of h on s by heading; the verdict of M1 "
                "and M2 and m4.half_iqr_hz; sealed, with the frozen protocol's content_sha256 "
                "and a code_tree_sha equal to frozen.code_tree_sha"
            ],
        },
        "guard": (
            "1996435 opens only when HEAD's protocol is frozen with a frozen entry after the "
            "design ones; HEAD's pose/ tree is frozen.code_tree_sha; the installed numpy is "
            "dependencies.numpy; HEAD holds pose_verdict.json sealed, answering to the frozen "
            "protocol's content_sha256 and computed by frozen.code_tree_sha, with P6 alive and "
            "a finite m4.half_iqr_hz (if M1 or M2 kill on 1925299, 1996435 never opens); and the "
            "working tree is clean"
        ),
        "order": [
            "sweep (committed)",
            "protocol in design (committed)",
            "probe, first time, and rule_w_cap (committed)",
            "frozen at the chosen (W, cap) (pose freeze, its own commit)",
            "second time on 1925299: M1, M2 and m4.half_iqr_hz (pose verdict, its own commit)",
            "1996435, only if alive: the metric and M4 (pose metric, task 61)",
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
                },
                {
                    "stage": STAGE_DESIGN,
                    "task": TASK,
                    "date": REVISED,
                    "note": (
                        "review of phase B2's first part, before the freeze: the bar judged "
                        "again at the separation the probe's (a') measures (it had been judged "
                        "at 5.5 / 4.3 m only), a sane instrument that must survive M1 and M2 "
                        "in the rule, the second time and its verdict file, M4's half IQR "
                        "written there, the guard's conditions on it and on numpy, and the "
                        "poses with is_detected false declared; the probe is run again"
                    ),
                },
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
    stage = current.get("stage")
    if stage not in (STAGE_DESIGN, STAGE_FROZEN):
        print(f"pose protocol --check: unknown stage {stage!r}")
        return 1
    written = (current.get("evidence") or {}).get("denominators", {}).get("per_match", {})
    evidence = {m: c if c is not None else written.get(m) for m, c in counted.items()}
    expected = build_protocol(sweep_sha, coverage_sha, ids, evidence)
    print(_summary(expected, status))
    if stage == STAGE_DESIGN:
        problems = [] if render(expected) == text else ["differs from what the code writes"]
    else:
        calibration = reports_dir / CALIBRATION_NAME
        problems = frozen_problems(
            current,
            expected,
            json.loads(calibration.read_text(encoding="utf-8")) if calibration.is_file() else None,
        )
    if problems:
        print(f"pose protocol --check: {path} " + "; ".join(problems))
        return 1
    print(
        f"pose protocol --check: {path} matches ({status}: {done} match(es) recounted, "
        f"{len(ids) - done} as written; stage {stage})"
    )
    return 0


FROZEN_KEEPS = ("schema_version", "written", "plan", "fingerprint", "design", "evidence")


def freeze_payload(
    current: dict[str, Any], calibration: dict[str, Any], *, code_tree: str, date: str
) -> dict[str, Any]:
    """The protocol as the freeze commits it: stage frozen, a `frozen` block with the (W, cap)
    the rule chose in `calibration` (the sealed first time of the probe), that file's seal, and
    the sha of the `pose/` tree committed in HEAD; a frozen entry after the design ones in
    `history`; the design untouched; resealed. Refuses a file that is not a sealed design, a
    calibration whose rule chose nothing (P6 died of noise: nothing to freeze) or a tree sha
    that is not one."""
    if current.get("stage") != STAGE_DESIGN:
        raise ValueError(f"only a protocol in stage {STAGE_DESIGN!r} freezes")
    if not sealed(current) or current.get("fingerprint") != fingerprint(current["design"]):
        raise ValueError("the protocol to freeze fails its seal or its fingerprint")
    chosen = (calibration.get("rule_w_cap") or {}).get("chosen")
    if not sealed(calibration) or chosen is None:
        raise ValueError("the calibration is not sealed or its rule chose no (W, cap)")
    if len(code_tree) != 40:
        raise ValueError(f"code_tree must be a git tree sha, got {code_tree!r}")
    entry = {"stage": STAGE_FROZEN, "task": TASK, "date": date, "note": FREEZE_NOTE}
    body = {k: v for k, v in current.items() if k != "content_sha256"}
    return seal(
        {
            **body,
            "stage": STAGE_FROZEN,
            "frozen": {
                "task": TASK,
                "date": date,
                "width": int(chosen["width"]),
                "cap_cm": int(chosen["cap_cm"]),
                "code_tree_sha": code_tree,
                "calibration_from": {
                    "file": f"pipeline/reports/{CALIBRATION_NAME}",
                    "content_sha256": calibration["content_sha256"],
                },
            },
            "history": [*body["history"], entry],
        }
    )


def frozen_problems(
    current: dict[str, Any], expected: dict[str, Any], calibration: dict[str, Any] | None
) -> list[str]:
    """What a frozen file must keep from the design the code writes (`expected`) and what the
    freeze must leave verifiable: the seal, the history, and a `frozen` block whose (W, cap) is
    the one the sealed calibration's rule chose. Whether its tree sha is HEAD's is the guard's
    question (`data`), not a file's."""
    problems: list[str] = []
    if not sealed(current):
        problems.append("content_sha256 does not cover the file")
    for key in FROZEN_KEEPS:
        if current.get(key) != expected[key]:
            problems.append(f"{key} differs from what the code writes")
    history = current.get("history") or []
    opening = expected["history"]
    if history[: len(opening)] != opening:
        problems.append("history does not open with the design entries")
    if not any(h.get("stage") == STAGE_FROZEN for h in history[len(opening) :]):
        problems.append("history has no frozen entry")
    frozen = current.get("frozen")
    if not isinstance(frozen, dict):
        return [*problems, "no frozen block"]
    tree = frozen.get("code_tree_sha")
    if not isinstance(tree, str) or len(tree) != 40:
        problems.append("frozen.code_tree_sha is not a git tree sha")
    if calibration is None or not sealed(calibration):
        problems.append(f"no sealed {CALIBRATION_NAME} beside it")
        return problems
    if (frozen.get("calibration_from") or {}).get("content_sha256") != calibration.get(
        "content_sha256"
    ):
        problems.append(f"frozen.calibration_from is not the {CALIBRATION_NAME} beside it")
    chosen = (calibration.get("rule_w_cap") or {}).get("chosen") or {}
    if (frozen.get("width"), frozen.get("cap_cm")) != (chosen.get("width"), chosen.get("cap_cm")):
        problems.append("frozen (width, cap_cm) is not the cell the calibration's rule chose")
    return problems


def _summary(payload: dict[str, Any], status: str) -> str:
    per_match = payload["evidence"]["denominators"]["per_match"]
    listed = {m: (c or {}).get("players_listed") for m, c in per_match.items()}
    return (
        f"pose protocol: bronze={status} calibration={list(CALIBRATION)} "
        f"confirmation={list(CONFIRMATION)} players_listed={listed} "
        f"sweep={payload['design']['sweep']['sha256'][:12]} "
        f"fingerprint={payload['fingerprint'][:12]}"
    )
