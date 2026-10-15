"""`tracklab pose probe`, first time: what the rule of (W, cap) reads on 1925299, and no cadence
(task 60 of tasks/todo.md, phase B2).

`reports/pose_calibration.json` holds, per period, with the protocol it answered to, `head`,
`code_tree_sha` and the date:

* (a) admitted windows (`gait.windows`, before the NaN rule) per player, period and band for W x
  cap, with the cap on the ankles (the protocol's) and on ankles and heels (what the heels cost):
  a window lies inside one period, and its band is that of its `gait.mean_speed_m_s`;
* (a') per period, W, cap and band: the sd of s(t) and of h(t) over each window's W frames
  (ddof 0) and the mean `mae` of the two ankles in it, as quantiles over the windows;
* (b) the distribution of `mae` per joint and period, over every row;
* (f) per period, W, cap and band: the speed over the first and the last `HEAD_TAIL_FRAMES`
  frames, the window counted as accelerating, plateau or braking by tail - head against
  +-`PLATEAU_REL` of the window's speed (descriptive: no rule reads it), and path / chord;
* (g) per player and period: the median of z(nose) - z(midHip) and of the ankles' mean z -
  z(midHip), with the share of frames above 0;
* `rule_w_cap`: the rule of the protocol applied blind, from (a) and the sweep alone: for each
  cell that passes the bar of `pose_sweep.json`, M1 and M2 simulated on the noise twin of every
  rho with (a)'s counts (cap on the ankles, both periods), and the cell chosen or P6's death.

What reads cadences (c, d, e, the NaN rates, M1 and M2 on data) is the second time, after the
freeze, and is not here. The rows come from `data.load_players`, past the guard; the match is
the calibration one the committed protocol names. Write mode refuses while the code under
`pose/` or the protocol has uncommitted changes, or while the bronze of 1925299 is not whole.
`--check` regenerates the file where that bronze is whole (`FULL 1/1`) and compares the bytes;
elsewhere it verifies the seal, the protocol it answered to and the rule against its own figures
(`PARTIAL 0/1`).
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from tracklab.pose import criteria, gait, sweep
from tracklab.pose.data import (
    STAGE_DESIGN,
    STAGE_FROZEN,
    CountingHandle,
    PoseRows,
    code_tree_sha,
    committed_protocol,
    committed_split,
    dirty_code_paths,
    head_commit,
    load_players,
)
from tracklab.pose.jsonl import JOINTS
from tracklab.pose.protocol import (
    FPS,
    HEAD_TAIL_FRAMES,
    P_DIES_NOISE_MIN,
    PLATEAU_REL,
    band,
    file_sha256,
)
from tracklab.runs.protocol import seal, sealed

CALIBRATION_NAME = "pose_calibration.json"
SCHEMA_VERSION = 1
WRITTEN = "2026-10-15"
TIME = "first: no cadence computed"
JOINT_SETS = ("ankles", "ankles_heels")
HEELS = (JOINTS.index("lHeel"), JOINTS.index("rHeel"))
NOSE = JOINTS.index("nose")
BANDS = ("below", "low", "high")
QS = (10, 50, 90)
CLASSES = ("accelerating", "plateau", "braking")

Array = NDArray[np.float64]

WINDOW_COLUMNS = ("player_id", "period", "joints", "width", "cap_cm", *BANDS)
SD_COLUMNS = (
    "period", "width", "cap_cm", "band", "windows", *(f"s_sd_p{q}_m" for q in QS),
    *(f"h_sd_p{q}_m" for q in QS), "ankle_mae_p50_cm", "ankle_mae_p90_cm",
)  # fmt: skip
MAE_COLUMNS = ("period", "joint", "p10", "p50", "p90", "max")
KIN_COLUMNS = (
    "period", "width", "cap_cm", "band", "windows", "head_p50_m_s", "tail_p50_m_s",
    *(f"tail_minus_head_p{q}_m_s" for q in QS), *CLASSES, "path_chord_p50", "path_chord_p90",
    "path_chord_max",
)  # fmt: skip
Z_COLUMNS = (
    "player_id", "period", "frames", "nose_minus_midhip_p50_m", "nose_share_above",
    "ankles_minus_midhip_p50_m", "ankles_share_above",
)  # fmt: skip
CELL_COLUMNS = ("rho", "p_dies", *criteria.DEATHS)


def _r(value: float, digits: int = 6) -> float | None:
    """Rounded; `mae` to 4 digits, the bronze's float32 holding no more (as coverage does)."""
    return round(float(value), digits) if np.isfinite(value) else None


def _qs(
    values: list[float] | Array, qs: tuple[int, ...] = QS, digits: int = 6
) -> list[float | None]:
    a = np.asarray(values, dtype=np.float64)
    return [_r(float(np.percentile(a, q)), digits) for q in qs] if a.size else [None] * len(qs)


def cap_mae(mae_cm: Array, joints: str) -> Array:
    """The `mae` `gait.windows` reads for a set of capped joints: with the heels, each ankle's
    column carries the larger of it and its own heel, so the cap holds on all four (a NaN stays
    NaN). The instrument's own cap is on the ankles alone."""
    if joints == "ankles":
        return mae_cm
    out = mae_cm.copy()
    for ankle, heel in zip(gait.ANKLES, HEELS, strict=True):
        out[:, ankle] = np.maximum(mae_cm[:, ankle], mae_cm[:, heel])
    return out


def window_speeds(x: Array, y: Array, starts: Array, width: int) -> Array:
    """`gait.mean_speed_m_s` of every window starting at `starts`, at once."""
    stops = starts + width - 1
    return np.asarray(np.hypot(x[stops] - x[starts], y[stops] - y[starts]) * FPS / (width - 1))


def _features(rows: PoseRows, sl: slice, start: int, stop: int, speed: float) -> tuple[float, ...]:
    """(a') and (f) of one window: sd of s and of h, the ankles' mean mae, head and tail
    speed, path / chord, and the window's speed. No cadence."""
    xy = np.c_[rows.x[sl][start:stop], rows.y[sl][start:stop]]
    centred = gait.centre_on_midhip(rows.joints[sl][start:stop].astype(np.float64))
    s = gait.signal(centred, gait.direction(xy))
    h = gait.signal_h(centred)
    mae = rows.mae_cm[sl][start:stop][:, gait.ANKLES].astype(np.float64)
    head = gait.mean_speed_m_s(xy[:HEAD_TAIL_FRAMES], fps=FPS)
    tail = gait.mean_speed_m_s(xy[-HEAD_TAIL_FRAMES:], fps=FPS)
    path = float(np.sum(np.hypot(*np.diff(xy, axis=0).T)))
    chord = float(np.hypot(*(xy[-1] - xy[0])))
    return float(np.std(s)), float(np.std(h)), float(mae.mean()), head, tail, path / chord, speed


def admitted(rows: PoseRows) -> dict[str, Any]:
    """(a), (a') and (f): every admitted window of every player, counted per band, and the
    features of those in the low and high bands with the cap on the ankles."""
    grid = sweep.PROTOCOL
    counts: Counter[tuple[int, int, str, int, int, str]] = Counter()
    features: dict[tuple[str, int, int, str], list[tuple[float, ...]]] = defaultdict(list)
    for pid, sl in rows.players():
        frame, period = rows.frame[sl], rows.period[sl]
        x, y = rows.x[sl], rows.y[sl]
        mae = rows.mae_cm[sl].astype(np.float64)
        for joints in JOINT_SETS:
            capped = cap_mae(mae, joints)
            for width in grid.widths:
                for cap in grid.caps_cm:
                    wins = gait.windows(frame, period, capped, width=width, mae_cap_cm=cap)
                    if not wins:
                        continue
                    starts = np.array([a for a, _ in wins])
                    speeds = window_speeds(x, y, starts, width)
                    for (start, stop), v in zip(wins, speeds, strict=True):
                        b = band(float(v))
                        p = int(period[start])
                        counts[(pid, p, joints, width, cap, b)] += 1
                        if joints == "ankles" and b != "below":
                            f = _features(rows, sl, start, stop, float(v))
                            features[(str(p), width, cap, b)].append(f)
                            features[("all", width, cap, b)].append(f)
    return {"counts": counts, "features": features}


def window_rows(rows: PoseRows, counts: Counter[Any]) -> list[list[Any]]:
    """(a): one row per player, period, joint set, W and cap, with the windows per band."""
    grid = sweep.PROTOCOL
    periods = sorted({int(p) for p in np.unique(rows.period)})
    out = []
    for pid, _ in rows.players():
        for p in periods:
            for joints in JOINT_SETS:
                for width in grid.widths:
                    for cap in grid.caps_cm:
                        n = [counts[(pid, p, joints, width, cap, b)] for b in BANDS]
                        out.append([pid, p, joints, width, cap, *n])
    return out


def window_summary(table: list[list[Any]]) -> list[dict[str, Any]]:
    """Per joint set, W and cap: windows per band, and the players with >= `MIN_WINDOWS`
    admitted in the high band and in both bands (both periods summed)."""
    per: dict[tuple[str, int, int], dict[int, Array]] = defaultdict(dict)
    for pid, _, joints, width, cap, *n in table:
        key = (joints, width, cap)
        per[key][pid] = per[key].get(pid, np.zeros(3, dtype=np.int64)) + np.array(n)
    out = []
    for (joints, width, cap), players in per.items():
        totals = np.sum(list(players.values()), axis=0)
        high = sum(int(n[2] >= criteria.MIN_WINDOWS) for n in players.values())
        both = sum(int(min(n[1], n[2]) >= criteria.MIN_WINDOWS) for n in players.values())
        out.append(
            {
                "joints": joints,
                "width": width,
                "cap_cm": cap,
                "windows": dict(zip(BANDS, (int(t) for t in totals), strict=True)),
                "players_ge_min_high": high,
                "players_ge_min_both": both,
            }
        )
    return out


def counts_for_rule(table: list[list[Any]], width: int, cap: int) -> tuple[list[int], list[int]]:
    """Per player (by id), the admitted windows in the high and the low band, cap on the
    ankles, both periods summed: the counts the simulator draws."""
    high: dict[int, int] = defaultdict(int)
    low: dict[int, int] = defaultdict(int)
    for pid, _, joints, w, c, _below, n_low, n_high in table:
        if (joints, w, c) == ("ankles", width, cap):
            high[pid] += n_high
            low[pid] += n_low
    ids = sorted(high)
    return [high[i] for i in ids], [low[i] for i in ids]


def sd_rows(features: dict[tuple[str, int, int, str], list[tuple[float, ...]]]) -> list[Any]:
    out = []
    for (p, width, cap, b), fs in sorted(features.items(), key=_feature_order):
        a = np.array(fs)
        out.append([p, width, cap, b, len(a), *_qs(a[:, 0]), *_qs(a[:, 1]),
                    *_qs(a[:, 2], (50, 90), 4)])  # fmt: skip
    return out


def kinematics_rows(
    features: dict[tuple[str, int, int, str], list[tuple[float, ...]]],
) -> list[Any]:
    out = []
    for (p, width, cap, b), fs in sorted(features.items(), key=_feature_order):
        a = np.array(fs)
        cls = classify(a[:, 3], a[:, 4], a[:, 6])
        out.append([p, width, cap, b, len(a), *_qs(a[:, 3], (50,)), *_qs(a[:, 4], (50,)),
                    *_qs(a[:, 4] - a[:, 3]), *(int(np.sum(cls == c)) for c in CLASSES),
                    *_qs(a[:, 5], (50, 90)), _r(float(a[:, 5].max()))])  # fmt: skip
    return out


def classify(head: Array, tail: Array, speed: Array) -> NDArray[np.str_]:
    """Accelerating when tail - head > `PLATEAU_REL` x the window's speed, braking below minus
    that, plateau in between."""
    diff = tail - head
    return np.where(
        diff > PLATEAU_REL * speed,
        "accelerating",
        np.where(diff < -PLATEAU_REL * speed, "braking", "plateau"),
    )


def _feature_order(item: tuple[tuple[str, int, int, str], Any]) -> tuple[int, int, int, int]:
    p, width, cap, b = item[0]
    return (99 if p == "all" else int(p), width, cap, BANDS.index(b))


def mae_rows(rows: PoseRows) -> list[list[Any]]:
    """(b): per period and over the match, the quantiles of each joint's `mae`."""
    out = []
    periods = [str(int(p)) for p in np.unique(rows.period)]
    for p in [*periods, "all"]:
        mask = np.ones(len(rows.period), dtype=bool) if p == "all" else rows.period == int(p)
        mae = rows.mae_cm[mask].astype(np.float64)
        for j, name in enumerate(JOINTS):
            out.append([p, name, *_qs(mae[:, j], QS, 4), _r(float(mae[:, j].max()), 4)])
    return out


def z_rows(rows: PoseRows) -> list[list[Any]]:
    """(g): per player and period, the nose and the ankles against midHip in z."""
    out = []
    for pid, sl in rows.players():
        z = rows.joints[sl][:, :, 2].astype(np.float64)
        nose = z[:, NOSE] - z[:, gait.MIDHIP]
        ankles = z[:, list(gait.ANKLES)].mean(axis=1) - z[:, gait.MIDHIP]
        period = rows.period[sl]
        for p in np.unique(period):
            m = period == p
            out.append([pid, int(p), int(m.sum()), _r(float(np.median(nose[m]))),
                        _r(float(np.mean(nose[m] > 0))), _r(float(np.median(ankles[m]))),
                        _r(float(np.mean(ankles[m] > 0)))])  # fmt: skip
    return out


def kills_the_noise(noise_rows: list[list[Any]], p_dies_min: float = P_DIES_NOISE_MIN) -> bool:
    """P(P6 dies | noise) at or above `p_dies_min` in every rho (column 1 of each row)."""
    return all(r[1] >= p_dies_min for r in noise_rows)


def choose(cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The cell of least W and, at equal W, of greatest cap among those that kill the noise."""
    alive = [c for c in cells if c["kills_the_noise"]]
    if not alive:
        return None
    best = min(alive, key=lambda c: (c["width"], -c["cap_cm"]))
    return {"width": best["width"], "cap_cm": best["cap_cm"]}


def rule_w_cap(
    table: list[list[Any]],
    bar_cells: list[dict[str, Any]],
    clip_mae_cm: Array,
    clip_fps: float,
    *,
    grid: sweep.Grid = sweep.PROTOCOL,
    draws: int = gait.DRAWS,
    reps: int = criteria.REPS,
    seed: int = criteria.SEED,
) -> dict[str, Any]:
    """The rule of (W, cap) of the protocol, from (a)'s counts and the sweep: per cell that
    passes the bar, P(P6 dies | noise) in every rho, and the cell it chooses (None: P6 dies)."""
    cells = []
    for cell in bar_cells:
        if not cell["passes"]:
            continue
        width, cap = int(cell["width"]), int(cell["cap_cm"])
        high, low = counts_for_rule(table, width, cap)
        sims = []
        for rho in grid.rhos:
            pool = sweep.noise_pool(
                clip_mae_cm, clip_fps, width=width, cap=cap, rho=rho, grid=grid, draws=draws
            )
            sim = criteria.simulate_m1_m2(high, low, pool, pool, reps=reps, seed=seed)
            sims.append([rho, sim["p_dies"], *(sim["by"][d] for d in criteria.DEATHS)])
        cells.append(
            {
                "width": width,
                "cap_cm": cap,
                "players": len(high),
                "players_ge_min_high": sum(n >= criteria.MIN_WINDOWS for n in high),
                "players_ge_min_both": sum(
                    min(a, b) >= criteria.MIN_WINDOWS for a, b in zip(high, low, strict=True)
                ),
                "windows_high": sum(high),
                "windows_low": sum(low),
                "noise": {"columns": list(CELL_COLUMNS), "rows": sims},
                "kills_the_noise": kills_the_noise(sims),
            }
        )
    chosen = choose(cells)
    return {
        "p_dies_min": P_DIES_NOISE_MIN,
        "reps": reps,
        "draws": draws,
        "seed": seed,
        "pool_windows": grid.windows_s,
        "cells": cells,
        "chosen": chosen,
        "verdict": (
            "P6 dies: the instrument cannot be told from the noise"
            if chosen is None
            else f"W {chosen['width']}, cap {chosen['cap_cm']} cm"
        ),
    }


def protocol_record() -> dict[str, Any]:
    protocol = committed_protocol()
    return {k: protocol[k] for k in ("stage", "fingerprint", "content_sha256")}


def protocol_problems(recorded: dict[str, Any]) -> list[str]:
    """As P5's probe: the same design always; the same stage and seal while HEAD is in design;
    once HEAD is frozen (the freeze does not regenerate this file), the record's shape."""
    problems: list[str] = []
    protocol = committed_protocol()
    if recorded.get("fingerprint") != protocol["fingerprint"]:
        problems.append("protocol.fingerprint is not the committed protocol's")
    if protocol["stage"] == STAGE_DESIGN:
        for key in ("stage", "content_sha256"):
            if recorded.get(key) != protocol[key]:
                problems.append(f"protocol.{key} is not the committed protocol's")
    elif recorded.get("stage") not in (STAGE_DESIGN, STAGE_FROZEN) or not (
        isinstance(recorded.get("content_sha256"), str) and len(recorded["content_sha256"]) == 64
    ):
        problems.append("protocol.stage or protocol.content_sha256 is not a protocol's")
    return problems


def build_calibration(
    rows: PoseRows,
    sweep_report: dict[str, Any],
    clip: tuple[float, Array, str],
    *,
    head: str,
    code_tree: str,
    protocol: dict[str, Any],
    sweep_sha256: str,
) -> dict[str, Any]:
    """The first time of the probe on `rows` (1925299), sealed."""
    fps, clip_mae, clip_sha = clip
    if clip_sha != sweep_report["source"]["sha256"]:
        raise ValueError("the clip is not the one the sweep was drawn from")
    found = admitted(rows)
    table = window_rows(rows, found["counts"])
    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 60,
            "phase": "B2",
            "time": TIME,
            "written": WRITTEN,
            "match_id": rows.match_id,
            "head": head,
            "code_tree_sha": code_tree,
            "protocol": protocol,
            "inputs": {
                "sweep": {"file": f"pipeline/reports/{sweep.SWEEP_NAME}", "sha256": sweep_sha256},
                "clip": {"file": sweep.CLIP_NAME, "sha256": clip_sha},
                "fps": FPS,
                "rows": len(rows.frame),
                "players_with_pose": len(rows.players()),
            },
            "windows": {
                "note": "(a) admitted windows, before the NaN rule; joints: the capped set",
                "summary": window_summary(table),
                "columns": list(WINDOW_COLUMNS),
                "rows": table,
            },
            "signal_sd": {
                "note": "(a') cap on the ankles; sd over each window's frames, ddof 0; period "
                "'all' pools both",
                "columns": list(SD_COLUMNS),
                "rows": sd_rows(found["features"]),
            },
            "mae_by_joint": {
                "note": "(b) over every row with a pose",
                "columns": list(MAE_COLUMNS),
                "rows": mae_rows(rows),
            },
            "kinematics": {
                "note": f"(f) cap on the ankles; head and tail over {HEAD_TAIL_FRAMES} frames; "
                f"class by tail - head against +-{PLATEAU_REL} x the window's mean_speed_m_s, "
                "descriptive, read by no rule; path / chord over the window's frames",
                "columns": list(KIN_COLUMNS),
                "rows": kinematics_rows(found["features"]),
            },
            "z_up": {
                "note": "(g) every frame with a pose; ankles: the mean z of lAnkle and rAnkle",
                "columns": list(Z_COLUMNS),
                "rows": z_rows(rows),
            },
            "rule_w_cap": rule_w_cap(table, sweep_report["bar"]["cells"], clip_mae, fps),
        }
    )


def consistency_problems(current: dict[str, Any], calibration: int) -> list[str]:
    """What the file must satisfy whatever bronze is at hand: the seal, the protocol, the match,
    the shas, and a rule that follows from its own figures."""
    problems: list[str] = []
    if not sealed(current):
        problems.append("content_sha256 does not cover the file")
    problems += protocol_problems(current.get("protocol") or {})
    if current.get("match_id") != calibration:
        problems.append("match_id is not the committed calibration match")
    for key in ("head", "code_tree_sha"):
        if not (isinstance(current.get(key), str) and len(current[key]) == 40):
            problems.append(f"{key} is not a git sha")
    design = committed_protocol()["design"]
    if current.get("inputs", {}).get("sweep", {}).get("sha256") != design["sweep"]["sha256"]:
        problems.append("inputs.sweep.sha256 is not the protocol's")
    try:
        rule = current["rule_w_cap"]
        for cell in rule["cells"]:
            if cell["kills_the_noise"] != kills_the_noise(
                cell["noise"]["rows"], rule["p_dies_min"]
            ):
                problems.append(f"rule_w_cap: W {cell['width']} / {cell['cap_cm']} does not "
                                "follow its figures")  # fmt: skip
        if rule["chosen"] != choose(rule["cells"]):
            problems.append("rule_w_cap.chosen does not follow the cells")
    except (KeyError, TypeError) as exc:
        problems.append(f"rule_w_cap is incomplete: {exc!r}")
    return problems


def _summary(payload: dict[str, Any], status: str) -> str:
    rule = payload["rule_w_cap"]
    cells = ", ".join(
        f"W{c['width']}/{c['cap_cm']}:{'kills' if c['kills_the_noise'] else 'spares'}"
        for c in rule["cells"]
    )
    return (
        f"pose probe: bronze={status} match={payload['match_id']} rule: {cells}; {rule['verdict']}"
    )


def _render(payload: dict[str, Any]) -> str:
    return sweep.render(payload) + "\n"


def _compute(
    data_dir: Path,
    reports_dir: Path,
    clip_path: Path,
    calibration: int,
    *,
    head: str,
    code_tree: str,
    protocol: dict[str, Any],
) -> dict[str, Any] | str:
    """The payload, or why it cannot be computed."""
    sweep_path = reports_dir / sweep.SWEEP_NAME
    sweep_sha = file_sha256(sweep_path)
    if sweep_sha != committed_protocol()["design"]["sweep"]["sha256"]:
        return f"{sweep_path} is not the sweep the committed protocol names"
    raw = clip_path.read_bytes()
    fps, clip_mae = sweep.clip_mae(json.loads(raw))
    return build_calibration(
        load_players(data_dir, calibration),
        json.loads(sweep_path.read_text(encoding="utf-8")),
        (fps, clip_mae, file_sha256(clip_path)),
        head=head,
        code_tree=code_tree,
        protocol=protocol,
        sweep_sha256=sweep_sha,
    )


def run_pose_probe(
    data_dir: Path, reports_dir: Path, clip_path: Path = sweep.CLIP, *, check: bool = False
) -> int:
    (calibration,) = committed_split()[0]
    handle = CountingHandle(data_dir, calibration)
    whole = handle.exists() and handle.is_whole()
    path = reports_dir / CALIBRATION_NAME
    started = time.perf_counter()
    if not check:
        dirty = dirty_code_paths()
        if dirty:
            print(
                f"pose probe: {len(dirty)} path(s) of the code that computes the figures are not "
                f"committed (e.g. {dirty[0]!r}): commit them first, so head and code_tree_sha "
                "name the code that ran"
            )
            return 1
        if not whole:
            print(f"pose probe: no whole bronze of {calibration} under {data_dir}; nothing written")
            return 1
        payload = _compute(
            data_dir,
            reports_dir,
            clip_path,
            calibration,
            head=head_commit(),
            code_tree=code_tree_sha(),
            protocol=protocol_record(),
        )
        if isinstance(payload, str):
            print(f"pose probe: {payload}")
            return 1
        reports_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(_render(payload), encoding="utf-8", newline="\n")
        print(_summary(payload, f"FULL 1/1 ({time.perf_counter() - started:.0f} s)"))
        print(f"pose probe: {path} ({path.stat().st_size} bytes)")
        return 0

    if not path.is_file():
        print(f"pose probe --check: {path} is missing")
        return 1
    text = path.read_text(encoding="utf-8")
    current = json.loads(text)
    problems = consistency_problems(current, calibration)
    if problems:
        print(f"pose probe --check: {path} " + "; ".join(problems))
        return 1
    if not whole:
        status = "PARTIAL 0/1: seal, protocol, match and rule checked against the figures"
        print(_summary(current, status))
        print(f"pose probe --check: {path} matches ({status} as written)")
        return 0
    payload = _compute(
        data_dir,
        reports_dir,
        clip_path,
        calibration,
        head=str(current["head"]),
        code_tree=str(current["code_tree_sha"]),
        protocol=current["protocol"],
    )
    if isinstance(payload, str):
        print(f"pose probe --check: {payload}")
        return 1
    if _render(payload) != text:
        print(f"pose probe --check: {path} differs from what the code writes")
        return 1
    status = f"FULL 1/1 recomputed and equal ({time.perf_counter() - started:.0f} s)"
    print(_summary(payload, status))
    print(f"pose probe --check: {path} matches ({status})")
    return 0
