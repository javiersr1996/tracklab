"""`tracklab pose metric`: the metric in the two matches, 1996435 read once (task 61 of
tasks/todo.md), written and tested with fixtures before the freeze of task 60 (phase B2),
because the freeze records the `pose/` tree.

At the frozen (W, cap), every admitted window of the low and the high band of both matches is
estimated and gets its Monte Carlo with its own seed (`verdict.window_estimates`). Per match,
period (and the whole match, `all`) and player, ordered by team and number
(`CountingHandle.lineup`): the windows per band (the denominator) and how many are finite in s;
the median cadence of s with the propagated sd of that median over all his windows and, in the
high band, over his first five finite ones (M2's); the median step (v / cad_s) and ankle
separation and their ratio; M3's concordance in the high band without a propagated error (the
sd propagated to cad_h is not calibrated, phase B1 of task 60); the mean speed.

Verdicts, beside their frozen thresholds: 1925299's M1 and M2, recomputed with the frozen code,
must equal the committed `pose_verdict.json` or nothing is written. 1996435: if its admitted
windows (before the NaN rule) do not reach any of the minima of M1 and M2, `unreplicated`
(not evaluable by coverage); otherwise M2 with the half IQR of 1925299 frozen as a number:
`replicated` or `replication_failed`. 1996435 is read through `load_players`, past the guard.
The file records `head`, `code_tree_sha`, the protocol's fingerprint and seal and the
verdict's seal. `--check` recomputes where both bronzes are whole and the guard opens
(`FULL 2/2`), and otherwise checks the seal and what the file answered to (`PARTIAL k/2`).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from tracklab.pose import criteria, sweep
from tracklab.pose.data import (
    CountingHandle,
    code_tree_sha,
    committed_protocol,
    committed_split,
    committed_verdict,
    dirty_code_paths,
    head_commit,
    load_players,
)
from tracklab.pose.verdict import Window, criteria_players, window_estimates
from tracklab.runs.data import HeldOutLocked
from tracklab.runs.protocol import seal, sealed

METRIC_NAME = "pose_metric.json"
SCHEMA_VERSION = 1
WRITTEN = "2026-10-15"
COLUMNS = (
    "team_id", "number", "player_id", "period", "band", "windows", "finite_s", "cad_s_p50_hz",
    "cad_s_sd_hz", "cad_s_sd_5_hz", "step_length_p50_m", "ankle_separation_p50_m",
    "separation_over_step", "m3_abs_diff_p50_hz", "m3_nan_h_share", "speed_mean_m_s",
)  # fmt: skip


def _r(value: float) -> float | None:
    return round(float(value), 6) if math.isfinite(value) else None


def _median(values: list[float]) -> float:
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if a.size else math.nan


def player_rows(windows: list[Window], lineup: list[tuple[int, int, int]]) -> list[list[Any]]:
    """One row per player, period (and `all`) and band, ordered by team, number and player."""
    place = {pid: (team, number) for pid, team, number in lineup}
    out = []
    players = sorted(
        {w.player_id for w in windows},
        key=lambda p: (*place.get(p, (math.inf, math.inf)), p),
    )
    for pid in players:
        team, number = place.get(pid, (None, None))
        mine = [w for w in windows if w.player_id == pid]
        for period in [*sorted({str(w.period) for w in mine}), "all"]:
            for band in ("low", "high"):
                ws = [w for w in mine if w.band == band and period in ("all", str(w.period))]
                if not ws:
                    continue
                cad = [w.estimate.cadence_hz for w in ws]
                draws = np.array([w.draws[:, 0] for w in ws if w.draws is not None])
                finite = [i for i, c in enumerate(cad) if math.isfinite(c)]
                sd5 = (
                    criteria.propagated_sd(draws[finite[: criteria.MIN_WINDOWS]])
                    if band == "high" and len(finite) >= criteria.MIN_WINDOWS
                    else math.nan
                )
                step = _median([w.estimate.step_length_m for w in ws])
                separation = _median([w.estimate.ankle_separation_m for w in ws])
                diffs = [
                    abs(w.estimate.cadence_hz - w.estimate.cadence_h_hz)
                    if math.isfinite(w.estimate.cadence_h_hz)
                    else math.inf
                    for w in ws
                    if math.isfinite(w.estimate.cadence_hz)
                ]
                out.append(
                    [
                        team, number, pid, period, band, len(ws), len(finite), _r(_median(cad)),
                        _r(criteria.propagated_sd(draws)) if len(draws) else None, _r(sd5),
                        _r(step), _r(separation), _r(separation / step),
                        _r(float(np.median(diffs))) if band == "high" and diffs else None,
                        _r(sum(not math.isfinite(w.estimate.cadence_h_hz) for w in ws) / len(ws))
                        if band == "high" else None,
                        _r(float(np.mean([w.speed_m_s for w in ws]))),
                    ]
                )  # fmt: skip
    return out


def admitted_minima(windows: list[Window]) -> dict[str, Any]:
    """The minima of M1 and M2 counted on admitted windows, before the NaN rule (M4's
    coverage): players with >= `MIN_WINDOWS` in the high band and in both bands."""
    per: dict[int, dict[str, int]] = {}
    for w in windows:
        per.setdefault(w.player_id, {"low": 0, "high": 0})[w.band] += 1
    high = sum(n["high"] >= criteria.MIN_WINDOWS for n in per.values())
    both = sum(min(n.values()) >= criteria.MIN_WINDOWS for n in per.values())
    return {
        "players_ge_min_high": high,
        "players_ge_min_both": both,
        "reached": high >= criteria.MIN_PLAYERS and both >= criteria.MIN_PLAYERS,
    }


def m_verdict(v: criteria.Verdict) -> dict[str, Any]:
    return {
        "m1_players": v.m1_players,
        "m2_players": v.m2_players,
        "m2_positive": v.m2_positive,
        "median_sd_hz": _r(v.median_sd_hz),
        "half_iqr_hz": _r(v.half_iqr_hz),
        "dies_at": v.dies_at,
    }


def match_verdicts(
    calibration: list[Window], confirmation: list[Window], half_iqr_hz: float
) -> dict[str, Any]:
    """M1 and M2 on 1925299; M4 (M2 with 1925299's half IQR) on 1996435, or unreplicated."""
    cal = criteria.m1_m2(criteria_players(calibration))
    coverage = admitted_minima(confirmation)
    if coverage["reached"]:
        m4 = criteria.m1_m2(criteria_players(confirmation), half_iqr_hz=half_iqr_hz)
        status = "replicated" if m4.dies_at is None else "replication_failed"
        m4_figures: dict[str, Any] | None = m_verdict(m4)
    else:
        status, m4_figures = "unreplicated", None
    return {
        "thresholds": {
            "min_players": criteria.MIN_PLAYERS,
            "min_windows": criteria.MIN_WINDOWS,
            "sign_share": criteria.SIGN_SHARE,
            "m4_half_iqr_hz": half_iqr_hz,
        },
        "calibration": m_verdict(cal),
        "confirmation": {"coverage": coverage, "m4": m4_figures, "status": status},
        "p6": "alive" if status == "replicated" and cal.dies_at is None else status,
    }


def build_metric(
    windows: dict[int, list[Window]],
    lineups: dict[int, list[tuple[int, int, int]]],
    *,
    protocol: dict[str, Any],
    verdict: dict[str, Any],
    head: str,
    code_tree: str,
) -> dict[str, Any]:
    cal, conf = (m for (m,) in committed_split())
    frozen = protocol["frozen"]
    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 61,
            "written": WRITTEN,
            "head": head,
            "code_tree_sha": code_tree,
            "protocol": {k: protocol[k] for k in ("stage", "fingerprint", "content_sha256")},
            "verdict_from": {
                "file": "pipeline/reports/pose_verdict.json",
                "content_sha256": verdict["content_sha256"],
            },
            "width": int(frozen["width"]),
            "cap_cm": int(frozen["cap_cm"]),
            "note": "M3's concordance has no propagated error: the sd propagated to cad_h is not "
            "calibrated (phase B1 of task 60)",
            "columns": list(COLUMNS),
            "matches": {str(m): player_rows(windows[m], lineups[m]) for m in (cal, conf)},
            "verdicts": match_verdicts(
                windows[cal], windows[conf], float(verdict["m4"]["half_iqr_hz"])
            ),
        }
    )


def recompute_problems(payload: dict[str, Any], verdict: dict[str, Any]) -> list[str]:
    """1925299, recomputed with the frozen code, must say what the committed verdict says."""
    mine = payload["verdicts"]["calibration"]
    theirs = verdict["verdict"]
    said = {
        "m1_players": theirs["M1"]["players"],
        "m2_players": theirs["M2"]["players_with_both"],
        "m2_positive": theirs["M2"]["positive"],
        "median_sd_hz": theirs["M2"]["median_sd_hz"],
        "half_iqr_hz": theirs["M2"]["half_iqr_hz"],
        "dies_at": theirs["dies_at"],
    }
    return [] if mine == said else ["1925299 recomputed differs from pose_verdict.json"]


def _summary(payload: dict[str, Any], status: str) -> str:
    v = payload["verdicts"]
    return (
        f"pose metric: bronze={status} W={payload['width']} cap={payload['cap_cm']} "
        f"1925299 dies_at={v['calibration']['dies_at']} 1996435={v['confirmation']['status']} "
        f"p6={v['p6']}"
    )


def _compute(data_dir: Path, head: str, code_tree: str) -> dict[str, Any] | str:
    protocol = committed_protocol()
    calibration, confirmation = (m for (m,) in committed_split())
    try:
        verdict = committed_verdict(protocol)
        rows = {m: load_players(data_dir, m) for m in (calibration, confirmation)}
    except HeldOutLocked as exc:
        return f"1996435 stays closed: {exc}"
    frozen = protocol["frozen"]
    windows = {
        m: window_estimates(
            r, int(frozen["width"]), int(frozen["cap_cm"]), mc_bands=("low", "high")
        )
        for m, r in rows.items()
    }
    lineups = {m: CountingHandle(data_dir, m).lineup() for m in rows}
    payload = build_metric(
        windows, lineups, protocol=protocol, verdict=verdict, head=head, code_tree=code_tree
    )
    problems = recompute_problems(payload, verdict)
    return "; ".join(problems) if problems else payload


def run_pose_metric(data_dir: Path, reports_dir: Path, *, check: bool = False) -> int:
    ids = [m for (m,) in committed_split()]
    whole = [m for m in ids if (h := CountingHandle(data_dir, m)).exists() and h.is_whole()]
    path = reports_dir / METRIC_NAME
    started = time.perf_counter()
    if not check:
        dirty = dirty_code_paths()
        if dirty:
            print(f"pose metric: uncommitted code or protocol (e.g. {dirty[0]!r})")
            return 1
        if len(whole) != len(ids):
            print(f"pose metric: whole bronze for {len(whole)} of {len(ids)}; nothing written")
            return 1
        payload = _compute(data_dir, head_commit(), code_tree_sha())
        if isinstance(payload, str):
            print(f"pose metric: {payload}; nothing written")
            return 1
        path.write_text(sweep.render(payload) + "\n", encoding="utf-8", newline="\n")
        print(_summary(payload, f"FULL 2/2 ({time.perf_counter() - started:.0f} s)"))
        print(f"pose metric: {path} ({path.stat().st_size} bytes)")
        return 0
    if not path.is_file():
        print(f"pose metric --check: {path} is missing")
        return 1
    text = path.read_text(encoding="utf-8")
    current = json.loads(text)
    protocol = committed_protocol()
    problems = [] if sealed(current) else ["content_sha256 does not cover the file"]
    if current.get("protocol", {}).get("fingerprint") != protocol["fingerprint"]:
        problems.append("protocol.fingerprint is not the committed protocol's")
    if problems:
        print(f"pose metric --check: {path} " + "; ".join(problems))
        return 1
    if len(whole) != len(ids):
        status = f"PARTIAL {len(whole)}/{len(ids)}: seal and protocol checked, nothing recomputed"
        print(_summary(current, status))
        print(f"pose metric --check: {path} matches ({status})")
        return 0
    payload = _compute(data_dir, str(current["head"]), str(current["code_tree_sha"]))
    if isinstance(payload, str) or sweep.render(payload) + "\n" != text:
        print(f"pose metric --check: {path} {payload if isinstance(payload, str) else 'differs'}")
        return 1
    status = f"FULL 2/2 recomputed and equal ({time.perf_counter() - started:.0f} s)"
    print(_summary(payload, status))
    print(f"pose metric --check: {path} matches ({status})")
    return 0
