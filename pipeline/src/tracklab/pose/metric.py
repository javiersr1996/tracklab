"""`tracklab pose metric`: the metric in the two matches, 1996435 read once (task 61 of
tasks/todo.md), written and tested with fixtures before the freeze of task 60 (phase B2),
because the freeze records the `pose/` tree.

At the frozen (W, cap), every admitted window of the low and the high band of both matches is
estimated and gets its Monte Carlo with its own seed (`verdict.window_estimates`). Per match,
period (and the whole match, `all`) and player, ordered by team and number
(`CountingHandle.lineup`): the windows per band (the denominator) and how many are finite in s;
the median cadence of s with the propagated sd of that median over his finite windows and, in
the high band, over his first five finite ones (M2's); the median step (v / cad_s) and ankle
separation and their ratio, each with its propagated sd; M3's concordance in the high band
without a propagated error (the sd propagated to cad_h is not calibrated, phase B1 of task 60);
the mean speed, without one either (the file's x, y carry no predicted error).

Verdicts, beside their frozen thresholds: 1925299's M1 and M2, recomputed with the frozen code,
must equal the committed `pose_verdict.json` or nothing is written. 1996435: if its admitted
windows (before the NaN rule) do not reach any of the minima of M1 and M2, `unreplicated`
(not evaluable by coverage); otherwise M2 with the half IQR of 1925299 frozen as a number:
`replicated` or `replication_failed`. 1996435 is read through `load_players`, past the guard.
1925299 is recomputed first, and 1996435 is loaded only if it gives the committed verdict.
The file records `head`, `code_tree_sha`, the protocol's fingerprint and seal and the
verdict's seal. `--check` recomputes where both bronzes are whole and the guard opens
(`FULL 2/2`), and otherwise checks the seal, the protocol, the code tree and the verdict
against what HEAD holds (`PARTIAL k/2`).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

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
    "cad_s_sd_hz", "cad_s_sd_5_hz", "step_length_p50_m", "step_length_sd_m",
    "ankle_separation_p50_m", "ankle_separation_sd_m", "separation_over_step",
    "separation_over_step_sd", "m3_abs_diff_p50_hz", "m3_nan_h_share", "speed_mean_m_s",
)  # fmt: skip
CAD, SEPARATION, STEP = 0, 1, 2  # columns of `gait.monte_carlo`'s draws

Array = NDArray[np.float64]


def _r(value: float) -> float | None:
    return round(float(value), 6) if math.isfinite(value) else None


def _median(values: list[float]) -> float:
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if a.size else math.nan


def _finite(values: list[float]) -> list[int]:
    return [i for i, v in enumerate(values) if math.isfinite(v)]


def ratio_sd(separation: Array, step: Array) -> float:
    """The sd over the draws of the ratio of the two medians over the windows (rows), each draw
    with the windows finite in it (`nanmedian`); a draw with either median NaN is not valid."""
    with np.errstate(all="ignore"):
        ratio = np.nanmedian(separation, axis=0) / np.nanmedian(step, axis=0)
    valid = ratio[np.isfinite(ratio)]
    return float(np.std(valid, ddof=1)) if len(valid) >= 2 else math.inf


def player_rows(windows: list[Window], lineup: list[tuple[int, int, int]]) -> list[list[Any]]:
    """One row per player, period (and `all`) and band, ordered by team, number and player.
    Each median is over the windows whose value is finite, and its propagated sd
    (`criteria.propagated_sd`, the draws of the same windows) beside it."""
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
                draws = np.array([w.draws for w in ws])  # (windows, draws, 4)
                cad = [w.estimate.cadence_hz for w in ws]
                step = [w.estimate.step_length_m for w in ws]
                sep = [w.estimate.ankle_separation_m for w in ws]
                f_cad, f_step, f_sep = _finite(cad), _finite(step), _finite(sep)
                sd5 = (
                    criteria.propagated_sd(draws[f_cad[: criteria.MIN_WINDOWS], :, CAD])
                    if band == "high" and len(f_cad) >= criteria.MIN_WINDOWS
                    else math.nan
                )
                diffs = [
                    abs(w.estimate.cadence_hz - w.estimate.cadence_h_hz)
                    if math.isfinite(w.estimate.cadence_h_hz)
                    else math.inf
                    for w in ws
                    if math.isfinite(w.estimate.cadence_hz)
                ]
                out.append(
                    [
                        team, number, pid, period, band, len(ws), len(f_cad), _r(_median(cad)),
                        _sd(draws, f_cad, CAD), _r(sd5),
                        _r(_median(step)), _sd(draws, f_step, STEP),
                        _r(_median(sep)), _sd(draws, f_sep, SEPARATION),
                        _r(_median(sep) / _median(step)),
                        _r(ratio_sd(draws[f_sep, :, SEPARATION], draws[f_step, :, STEP]))
                        if f_sep and f_step else None,
                        _r(float(np.median(diffs))) if band == "high" and diffs else None,
                        _r(sum(not math.isfinite(w.estimate.cadence_h_hz) for w in ws) / len(ws))
                        if band == "high" else None,
                        _r(float(np.mean([w.speed_m_s for w in ws]))),
                    ]
                )  # fmt: skip
    return out


def _sd(draws: Array, rows: list[int], column: int) -> float | None:
    """The propagated sd of the median of `column` over the windows `rows`."""
    return _r(criteria.propagated_sd(draws[rows, :, column])) if rows else None


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
            "note": "each median is over the windows with that value finite, its sd propagated "
            "over the draws of the same windows (criteria.propagated_sd; the ratio's, draw by "
            "draw); M3's concordance has no propagated error: the sd propagated to cad_h is not "
            "calibrated (phase B1 of task 60); speed_mean_m_s has no propagated error: the "
            "file's x, y carry no predicted error",
            "columns": list(COLUMNS),
            "matches": {str(m): player_rows(windows[m], lineups[m]) for m in (cal, conf)},
            "verdicts": match_verdicts(
                windows[cal], windows[conf], float(verdict["m4"]["half_iqr_hz"])
            ),
        }
    )


def recompute_problems(figures: dict[str, Any], verdict: dict[str, Any]) -> list[str]:
    """1925299's M1 and M2 (`m_verdict`), recomputed with the frozen code, must say what the
    committed verdict says."""
    theirs = verdict["verdict"]
    said = {
        "m1_players": theirs["M1"]["players"],
        "m2_players": theirs["M2"]["players_with_both"],
        "m2_positive": theirs["M2"]["positive"],
        "median_sd_hz": theirs["M2"]["median_sd_hz"],
        "half_iqr_hz": theirs["M2"]["half_iqr_hz"],
        "dies_at": theirs["dies_at"],
    }
    return [] if figures == said else ["1925299 recomputed differs from pose_verdict.json"]


def _summary(payload: dict[str, Any], status: str) -> str:
    v = payload["verdicts"]
    return (
        f"pose metric: bronze={status} W={payload['width']} cap={payload['cap_cm']} "
        f"1925299 dies_at={v['calibration']['dies_at']} 1996435={v['confirmation']['status']} "
        f"p6={v['p6']}"
    )


def _compute(data_dir: Path, head: str, code_tree: str) -> dict[str, Any] | str:
    """1925299 first: if the frozen code does not give the committed verdict, 1996435 is never
    loaded."""
    protocol = committed_protocol()
    calibration, confirmation = (m for (m,) in committed_split())
    try:
        verdict = committed_verdict(protocol)
    except HeldOutLocked as exc:
        return f"1996435 stays closed: {exc}"
    frozen = protocol["frozen"]
    width, cap = int(frozen["width"]), int(frozen["cap_cm"])

    def estimated(match: int) -> list[Window]:
        rows = load_players(data_dir, match)
        return window_estimates(rows, width, cap, mc_bands=("low", "high"))

    windows = {calibration: estimated(calibration)}
    problems = recompute_problems(
        m_verdict(criteria.m1_m2(criteria_players(windows[calibration]))), verdict
    )
    if problems:
        return "; ".join(problems)
    try:
        windows[confirmation] = estimated(confirmation)
    except HeldOutLocked as exc:
        return f"1996435 stays closed: {exc}"
    lineups = {m: CountingHandle(data_dir, m).lineup() for m in windows}
    return build_metric(
        windows, lineups, protocol=protocol, verdict=verdict, head=head, code_tree=code_tree
    )


def partial_problems(current: dict[str, Any]) -> list[str]:
    """What the file must say whatever bronze is at hand: sealed, answering to the protocol,
    the frozen code tree and the verdict committed in HEAD."""
    problems = [] if sealed(current) else ["content_sha256 does not cover the file"]
    protocol = committed_protocol()
    recorded = current.get("protocol") or {}
    if any(recorded.get(k) != protocol.get(k) for k in ("stage", "fingerprint", "content_sha256")):
        problems.append("protocol is not the one committed in HEAD")
    if current.get("code_tree_sha") != (protocol.get("frozen") or {}).get("code_tree_sha"):
        problems.append("code_tree_sha is not the tree the freeze recorded")
    try:
        seal_ = committed_verdict(protocol)["content_sha256"]
    except HeldOutLocked as exc:
        problems.append(f"no verdict to answer to: {exc}")
    else:
        if (current.get("verdict_from") or {}).get("content_sha256") != seal_:
            problems.append("verdict_from is not the pose_verdict.json committed in HEAD")
    return problems


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
    problems = partial_problems(current)
    if problems:
        print(f"pose metric --check: {path} " + "; ".join(problems))
        return 1
    if len(whole) != len(ids):
        status = (
            f"PARTIAL {len(whole)}/{len(ids)}: seal, protocol, code tree and verdict checked, "
            "nothing recomputed"
        )
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
