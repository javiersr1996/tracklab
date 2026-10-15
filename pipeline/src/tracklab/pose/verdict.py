"""`tracklab pose verdict`: the probe's second time on 1925299, after the freeze (task 60 of
tasks/todo.md, phase B2), and the verdict of M1 and M2 that opens 1996435 or keeps it closed.

At the (W, cap) the frozen protocol names, every admitted window of the low and the high band
(cap on the ankles, inside one period, band by `gait.mean_speed_m_s`) is estimated with
`gait.estimate`, and every high window gets its Monte Carlo (`gait.monte_carlo`, 200 draws)
with its own seed, `gait.window_seed(match, player, first frame)`. `reports/pose_verdict.json`
holds, sealed:

* (c) the cadence of s per player and band (median of the finite windows, n beside), the sign
  of high - low and the share of players with it positive;
* (d) M3's concordance, no verdict: per player of M1, the median of |cad_s - cad_h| in the high
  band (a NaN in h counts as discrepant, an infinite difference) and the share of NaN in h,
  with the sweep's rows of h at that (W, cap), rho 0 and kz 1.0 beside;
* (e) the propagated error per high window (median and p90 of the sd of cad_s and of the step)
  against the IQR between players of their cadence;
* the NaN rates of cad_s and cad_h per band, the distribution of cad_s per band with the
  sweep's rows of the left/right swap beside, and the slope of h on s at lag 0 per window by
  the heading's angle to the pitch's x axis (descriptive, read by no rule);
* `verdict`: M1 and M2 (`criteria.m1_m2`) with their figures, `alive`; `m4.half_iqr_hz`, half
  the IQR of 1925299 that M4 compares 1996435's precision with.

The file records the frozen protocol it answered to (stage, fingerprint, `content_sha256`),
`head` and `code_tree_sha`, which must be the tree the freeze recorded: write mode refuses
otherwise, and the guard (`data.assert_confirmation_open`) reads this blob in HEAD. `--check`
recomputes where 1925299's bronze is whole (`FULL 1/1`) and compares the bytes; elsewhere it
checks the seal, the protocol, the tree and a verdict that follows from its figures.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from tracklab.pose import criteria, gait, sweep
from tracklab.pose.data import (
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
from tracklab.pose.protocol import FPS, band
from tracklab.runs.protocol import seal, sealed

VERDICT_NAME = "pose_verdict.json"
SCHEMA_VERSION = 1
WRITTEN = "2026-10-15"
QS = (5, 25, 50, 75, 95)
HEADINGS = ((0.0, 30.0), (30.0, 60.0), (60.0, 90.0))  # degrees from the pitch's x axis

Array = NDArray[np.float64]


@dataclass(frozen=True)
class Window:
    """One admitted window of the low or the high band and what `gait` says of it. `draws` is
    `gait.monte_carlo`'s (draws, 4) for the bands that asked for it, else None."""

    player_id: int
    period: int
    frame: int
    band: str
    speed_m_s: float
    heading_deg: float
    estimate: gait.Gait
    slope_h_on_s: float
    draws: Array | None


def window_estimates(
    rows: PoseRows,
    width: int,
    cap_cm: float,
    *,
    mc_bands: tuple[str, ...] = ("high",),
    draws: int = gait.DRAWS,
) -> list[Window]:
    """Every admitted window of the low and the high band of `rows`, by player and frame."""
    out = []
    for pid, sl in rows.players():
        frame, period = rows.frame[sl], rows.period[sl]
        mae = rows.mae_cm[sl].astype(np.float64)
        for start, stop in gait.windows(frame, period, mae, width=width, mae_cap_cm=cap_cm):
            xy = np.c_[rows.x[sl][start:stop], rows.y[sl][start:stop]]
            b = band(gait.mean_speed_m_s(xy, fps=FPS))
            if b == "below":
                continue
            joints = rows.joints[sl][start:stop].astype(np.float64)
            centred = gait.centre_on_midhip(joints)
            s = gait.signal(centred, gait.direction(xy))
            h = gait.signal_h(centred)
            s0, h0 = s - s.mean(), h - h.mean()
            dx, dy = xy[-1] - xy[0]
            heading = abs(math.degrees(math.atan2(float(dy), float(dx))))
            values = None
            if b in mc_bands:
                seed = gait.window_seed(rows.match_id, pid, int(frame[start]))
                values = gait.monte_carlo(
                    joints, xy, mae[start:stop], fps=FPS, draws=draws, seed=seed
                )
            out.append(
                Window(
                    pid,
                    int(period[start]),
                    int(frame[start]),
                    b,
                    gait.mean_speed_m_s(xy, fps=FPS),
                    180.0 - heading if heading > 90.0 else heading,
                    gait.estimate(joints, xy, fps=FPS),
                    float(np.sum(s0 * h0) / np.sum(s0 * s0)),
                    values,
                )
            )
    return out


def criteria_players(windows: list[Window]) -> list[criteria.Player]:
    """Per player (by id), M1 and M2's view of his windows, in frame order: the cadence of s of
    each high and low window and the Monte Carlo cadences of each high one."""
    out = []
    for pid in sorted({w.player_id for w in windows}):
        high = [w for w in windows if w.player_id == pid and w.band == "high"]
        low = [w for w in windows if w.player_id == pid and w.band == "low"]
        mc = [w.draws[:, 0] for w in high if w.draws is not None]
        out.append(
            criteria.Player(
                np.array([w.estimate.cadence_hz for w in high]),
                np.array([w.estimate.cadence_hz for w in low]),
                np.array(mc) if mc else np.empty((0, gait.DRAWS)),
            )
        )
    return out


def _r(value: float) -> float | None:
    return round(float(value), 6) if math.isfinite(value) else None


def _qs(values: list[float], qs: tuple[int, ...] = QS) -> list[float | None]:
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    return [_r(float(np.percentile(a, q))) for q in qs] if a.size else [None] * len(qs)


def _iqr(values: list[float]) -> float:
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size < 2:
        return math.nan
    q25, q75 = np.percentile(a, [25, 75])
    return float(q75 - q25)


def second_time(
    windows: list[Window], sweep_report: dict[str, Any], width: int, cap_cm: int
) -> dict[str, Any]:
    """(c), (d), (e), the NaN rates, the distribution of cad_s, the slope of h on s, and the
    verdict of M1 and M2 with `m4.half_iqr_hz`."""
    by_player: dict[int, dict[str, list[Window]]] = {}
    for w in windows:
        by_player.setdefault(w.player_id, {"low": [], "high": []})[w.band].append(w)
    verdict = criteria.m1_m2(criteria_players(windows))
    cadence_rows, signs = [], []
    concordance = []
    for pid, bands in sorted(by_player.items()):
        cad = {b: [w.estimate.cadence_hz for w in ws] for b, ws in bands.items()}
        finite = {b: [c for c in cs if math.isfinite(c)] for b, cs in cad.items()}
        med = {b: float(np.median(f)) if f else math.nan for b, f in finite.items()}
        both = all(len(finite[b]) >= criteria.MIN_WINDOWS for b in ("low", "high"))
        sign = (med["high"] > med["low"]) if both else None
        if sign is not None:
            signs.append(sign)
        cadence_rows.append([pid, len(cad["low"]), len(finite["low"]), _r(med["low"]),
                             len(cad["high"]), len(finite["high"]), _r(med["high"]),
                             sign])  # fmt: skip
        if len(finite["high"]) >= criteria.MIN_WINDOWS:
            diffs = [
                abs(w.estimate.cadence_hz - w.estimate.cadence_h_hz)
                if math.isfinite(w.estimate.cadence_h_hz)
                else math.inf
                for w in bands["high"]
                if math.isfinite(w.estimate.cadence_hz)
            ]
            nan_h = sum(not math.isfinite(w.estimate.cadence_h_hz) for w in bands["high"])
            concordance.append([pid, len(diffs), _r(float(np.median(diffs))),
                                _r(nan_h / len(bands["high"]))])  # fmt: skip
    high = [w for w in windows if w.band == "high"]
    errors = [gait.summarise(w.draws) for w in high if w.draws is not None]
    medians_high = [r[6] for r in cadence_rows if r[6] is not None]
    rates = []
    for b in ("low", "high"):
        ws = [w for w in windows if w.band == b]
        n = len(ws)
        rates.append([b, n, sum(not math.isfinite(w.estimate.cadence_hz) for w in ws),
                      sum(not math.isfinite(w.estimate.cadence_h_hz) for w in ws)])  # fmt: skip
    distribution = [
        [b, *_qs([w.estimate.cadence_hz for w in windows if w.band == b])] for b in ("low", "high")
    ]
    h_columns = sweep_report["h_rows"]["columns"]
    at_cell = [
        r
        for r in sweep_report["h_rows"]["rows"]
        if (r[1], r[2], r[4], r[5]) == (width, cap_cm, 0.0, 1.0)
    ]
    slopes = []
    for lo, hi in HEADINGS:
        s = [
            w.slope_h_on_s
            for w in high
            if lo <= w.heading_deg < hi or (hi == 90.0 and w.heading_deg == 90.0)
        ]
        slopes.append([lo, hi, len(s), *_qs(s, (25, 50, 75))])
    dies = verdict.dies_at
    return {
        "cadence": {
            "note": "(c) cadence of s, Hz: per player, the median of his finite windows per band; "
            f"sign of high - low for the players with >= {criteria.MIN_WINDOWS} finite in both",
            "columns": [
                "player_id",
                "low_windows",
                "low_finite",
                "low_cad_s_hz",
                "high_windows",
                "high_finite",
                "high_cad_s_hz",
                "high_above_low",
            ],  # fmt: skip
            "rows": cadence_rows,
            "players_with_both": len(signs),
            "positive": sum(signs),
        },
        "m3": {
            "note": "(d) M3, no verdict and no propagated error: per player of M1, the median of "
            "|cad_s - cad_h| over his high windows finite in s (NaN in h: infinite) and the share "
            "of NaN in h; the sweep's rows of h at this (W, cap), rho 0, kz 1.0 beside",
            "columns": ["player_id", "windows", "abs_diff_p50_hz", "nan_h_share"],
            "rows": concordance,
            "sweep_h_columns": h_columns,
            "sweep_h_rows": at_cell,
        },
        "error": {
            "note": "(e) per high window, the Monte Carlo sd of cad_s and of the step (draws "
            "with a finite cad_s, separation and step), against the IQR between players of "
            "their high-band cadence",
            "windows": len(errors),
            "cad_s_sd_p50_hz": _qs([e.cadence_hz_sd for e in errors], (50,))[0],
            "cad_s_sd_p90_hz": _qs([e.cadence_hz_sd for e in errors], (90,))[0],
            "step_sd_p50_m": _qs([e.step_length_m_sd for e in errors], (50,))[0],
            "step_sd_p90_m": _qs([e.step_length_m_sd for e in errors], (90,))[0],
            "iqr_between_players_hz": _r(_iqr(medians_high)),
        },
        "nan_rates": {
            "columns": ["band", "windows", "nan_cad_s", "nan_cad_h"],
            "rows": rates,
        },
        "cad_s_distribution": {
            "columns": ["band", *(f"p{q}_hz" for q in QS)],
            "rows": distribution,
            "swap_note": "the sweep's swap rows (the forward foot called left in every frame) "
            "at this (W, cap), rho 0, kz 1.0: cad_s_p50_hz per planted cadence, a blind spot",
            "swap": [
                [r[h_columns.index("cadence_hz")], r[h_columns.index("cad_s_p50_hz")]]
                for r in at_cell
                if r[0] == "swap"
            ],
        },
        "slope_h_on_s": {
            "note": "per high window, cov(s, h) / var(s) at lag 0, by the heading's angle to the "
            "pitch's x axis folded into [0, 90] degrees; descriptive",
            "columns": ["from_deg", "to_deg", "windows", "p25", "p50", "p75"],
            "rows": slopes,
        },
        "verdict": {
            "M1": {
                "players": verdict.m1_players,
                "min_players": criteria.MIN_PLAYERS,
                "dies": dies == "m1",
            },
            "M2": {
                "players_with_both": verdict.m2_players,
                "positive": verdict.m2_positive,
                "sign_share": criteria.SIGN_SHARE,
                "median_sd_hz": _r(verdict.median_sd_hz),
                "half_iqr_hz": _r(verdict.half_iqr_hz),
                "dies_at": dies if dies is not None and dies.startswith("m2") else None,
            },
            "dies_at": dies,
            "alive": dies is None,
        },
        "m4": {
            "half_iqr_hz": _r(verdict.half_iqr_hz),
            "note": "half the IQR between the players of M1 of 1925299 of the median of their "
            "first five finite high windows: M4's threshold for 1996435's propagated sd",
        },
    }


def build_verdict(
    rows: PoseRows,
    sweep_report: dict[str, Any],
    *,
    protocol: dict[str, Any],
    head: str,
    code_tree: str,
    draws: int = gait.DRAWS,
) -> dict[str, Any]:
    frozen = protocol["frozen"]
    width, cap = int(frozen["width"]), int(frozen["cap_cm"])
    windows = window_estimates(rows, width, cap, draws=draws)
    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 60,
            "phase": "B2",
            "time": "second: cadences, after the freeze",
            "written": WRITTEN,
            "match_id": rows.match_id,
            "head": head,
            "code_tree_sha": code_tree,
            "protocol": {k: protocol[k] for k in ("stage", "fingerprint", "content_sha256")},
            "width": width,
            "cap_cm": cap,
            "draws": draws,
            "inputs": {"rows": len(rows.frame), "players_with_pose": len(rows.players())},
            **second_time(windows, sweep_report, width, cap),
        }
    )


def frozen_here() -> dict[str, Any]:
    """The committed protocol, frozen, whose recorded tree is HEAD's, with the numpy its design
    names installed: what the second time answers to. Anything else raises ValueError."""
    protocol = committed_protocol()
    if protocol.get("stage") != STAGE_FROZEN:
        raise ValueError(f"the committed protocol is in stage {protocol.get('stage')!r}")
    if (protocol.get("frozen") or {}).get("code_tree_sha") != code_tree_sha():
        raise ValueError("HEAD's pose/ tree is not the one the freeze recorded")
    numpy = importlib.metadata.version("numpy")
    if numpy != protocol["design"].get("dependencies", {}).get("numpy"):
        raise ValueError(f"numpy {numpy} is installed, not the one the protocol names")
    return protocol


def consistency_problems(current: dict[str, Any], calibration: int) -> list[str]:
    problems: list[str] = []
    if not sealed(current):
        problems.append("content_sha256 does not cover the file")
    protocol = committed_protocol()
    recorded = current.get("protocol") or {}
    if any(recorded.get(k) != protocol.get(k) for k in ("stage", "fingerprint", "content_sha256")):
        problems.append("protocol is not the committed one")
    if current.get("code_tree_sha") != (protocol.get("frozen") or {}).get("code_tree_sha"):
        problems.append("code_tree_sha is not the tree the freeze recorded")
    if current.get("match_id") != calibration:
        problems.append("match_id is not the committed calibration match")
    try:
        section = current["verdict"]
        dies = criteria.verdict_dies_at(section)
        if section["dies_at"] != dies or section["alive"] != (dies is None):
            problems.append("verdict does not follow its figures")
        if not isinstance(current["inputs"]["rows"], int):
            problems.append("inputs.rows is not a count")
        if current["m4"]["half_iqr_hz"] != section["M2"]["half_iqr_hz"]:
            problems.append("m4.half_iqr_hz is not M2's")
    except (KeyError, TypeError) as exc:
        problems.append(f"the verdict is incomplete: {exc!r}")
    return problems


def _render(payload: dict[str, Any]) -> str:
    return sweep.render(payload) + "\n"


def _summary(payload: dict[str, Any], status: str) -> str:
    v = payload["verdict"]
    return (
        f"pose verdict: bronze={status} match={payload['match_id']} W={payload['width']} "
        f"cap={payload['cap_cm']} M1={v['M1']['players']} M2={v['M2']['positive']}/"
        f"{v['M2']['players_with_both']} sd={v['M2']['median_sd_hz']} "
        f"half_iqr={v['M2']['half_iqr_hz']} dies_at={v['dies_at']}"
    )


def run_pose_verdict(data_dir: Path, reports_dir: Path, *, check: bool = False) -> int:
    (calibration,) = committed_split()[0]
    handle = CountingHandle(data_dir, calibration)
    whole = handle.exists() and handle.is_whole()
    path = reports_dir / VERDICT_NAME
    sweep_report = json.loads((reports_dir / sweep.SWEEP_NAME).read_text(encoding="utf-8"))
    started = time.perf_counter()
    if not check:
        try:
            protocol = frozen_here()
        except ValueError as exc:
            print(f"pose verdict: {exc}; the second time runs only on the frozen code")
            return 1
        dirty = dirty_code_paths()
        if dirty:
            print(f"pose verdict: uncommitted code or protocol (e.g. {dirty[0]!r})")
            return 1
        if not whole:
            print(f"pose verdict: no whole bronze of {calibration} under {data_dir}")
            return 1
        payload = build_verdict(
            load_players(data_dir, calibration),
            sweep_report,
            protocol=protocol,
            head=head_commit(),
            code_tree=code_tree_sha(),
        )
        path.write_text(_render(payload), encoding="utf-8", newline="\n")
        print(_summary(payload, f"FULL 1/1 ({time.perf_counter() - started:.0f} s)"))
        print(f"pose verdict: {path} ({path.stat().st_size} bytes)")
        return 0
    if not path.is_file():
        print(f"pose verdict --check: {path} is missing")
        return 1
    text = path.read_text(encoding="utf-8")
    current = json.loads(text)
    problems = consistency_problems(current, calibration)
    if problems:
        print(f"pose verdict --check: {path} " + "; ".join(problems))
        return 1
    if not whole:
        status = "PARTIAL 0/1: seal, protocol, tree and verdict checked against the figures"
        print(_summary(current, status))
        print(f"pose verdict --check: {path} matches ({status} as written)")
        return 0
    try:
        protocol = frozen_here()
    except ValueError as exc:
        print(f"pose verdict --check: {exc}")
        return 1
    payload = build_verdict(
        load_players(data_dir, calibration),
        sweep_report,
        protocol=protocol,
        head=str(current["head"]),
        code_tree=str(current["code_tree_sha"]),
        draws=int(current["draws"]),
    )
    if _render(payload) != text:
        print(f"pose verdict --check: {path} differs from what the code writes")
        return 1
    status = f"FULL 1/1 recomputed and equal ({time.perf_counter() - started:.0f} s)"
    print(_summary(payload, status))
    print(f"pose verdict --check: {path} matches ({status})")
    return 0
