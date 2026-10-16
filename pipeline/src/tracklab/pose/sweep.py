"""`tracklab pose sweep`: the synthetic sweep of task 60, versioned before the probe (phase B1).

What `gait.cadence_hz` does on runners whose cadence is planted, over the grid the protocol fixes
(tasks/todo.md, task 60, "Protocolo que vale tras las seis pasadas"), written to
`reports/pose_sweep.json` in a commit before `pose_calibration.json`:

* **Rows of s**: W {25, 37, 50} x cap {15, 20, 25} cm x cadence {2.5, 3.0, 3.5, 4.3} Hz x rho
  {0, 0.5, 0.8, 0.9}, 40,000 windows each, ankle separation 5.5 / 4.3 m in every cadence (both
  figures are the plan's hypotheses, without a source): the share of NaN in s and the p50 and
  p95 of the relative error of the finite cadences.
* **The bar of task 59** per (W, cap): p95 <= 5 % and NaN <= 10 % in the four cadences at rho 0
  (the white error task 59 assumes); at rho 0.5 to 0.9 the rows are printed and judged by no
  rule. A cell is judged on the rounded figures the file holds.
* **A noise twin** per (W, cap, rho), 40,000 windows: the same body travelling with no gait, so
  s is error only; its NaN share and cadence quantiles. `noise_pool` regenerates its windows
  bit for bit, with a Monte Carlo per window, for the simulator of M1 and M2
  (`tracklab.pose.criteria`) that phase B2 runs with the probe's counts.
* **Informative rows of h**, 400 windows each, read by no rule: `sane` (lift of the foot in the
  air 0.10 to 0.60 m by 0.05, kz {1.0, 1.5}), the broken rows `no_gait` (i: no swing, no lift)
  and `flat_h` (ii: swing, no lift), and the blind spots `swap` (the forward foot called left in
  every frame, lift 0.30 m, the value of the protocol's NaN test) and `lean` (s tilted towards z
  by 10 or 20 degrees, no lift), each over W x cap x cadence x rho x kz.

The model of a window, drawn as the two signals the estimator reads (a test rebuilds the 29
joints of a body from the same draws and gets the same s and h through `gait`): the stride's
phase is uniform per window and ψ(t) = π · cadence · t + phase; the left ankle sits
separation / 2 · sin ψ ahead of midHip and the right one as far behind, so s = separation · sin ψ;
each foot rises lift · max(0, ±cos ψ) while it swings forward, half of the stride, so h = lift ·
cos ψ (the feet take turns: no instant with both up, a supposition of the fourth review). The
error of each ankle in each frame has the sd of that ankle's `p90_mae_cm` in a skeleton of the
versioned clip drawn per frame among those whose two ankles are at or under the cap, as in
task 59: along d it is the projection of an isotropic error in x, y (so N(0, mae) along it), in
z it is kz times as large, and along the frames it is an AR(1) with coefficient rho and the same
sd. midHip's error cancels in both signals, and d is the heading, since the file's x, y carry no
error in this model (task 59, deviation 8).

Every random stream is seeded by the seed of the file and the row's own key, so a row does not
depend on the order of the grid, and `--check` regenerates the whole file and compares bytes.
No data is read: the only input is the clip `web/public/data/pose/1925299_phase406.json`
(the `mae` of its 4,953 skeletons, its fps and its sha256), so the check is FULL on any
data root.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from tracklab.pose import gait
from tracklab.pose.criteria import Pool
from tracklab.pose.jsonl import JOINTS

SWEEP_NAME = "pose_sweep.json"
CLIP = Path("../web/public/data/pose/1925299_phase406.json")
CLIP_NAME = "web/public/data/pose/1925299_phase406.json"
SCHEMA_VERSION = 1
WRITTEN = "2026-10-14"
SEED = 60
SEPARATION_M = 5.5 / 4.3
BAR_P95 = 0.05
BAR_NAN = 0.10
BAR_RHO = 0.0
KINDS = ("s", "twin", "sane", "no_gait", "flat_h", "swap", "lean", "pool_mc", "sane_high",
         "sane_low")  # fmt: skip

Array = NDArray[np.float64]

S_COLUMNS = (
    "width", "cap_cm", "cadence_hz", "rho", "windows", "nan_s", "cad_s_p50_hz",
    "rel_err_p50", "rel_err_p95", "meets_bar",
)  # fmt: skip
TWIN_COLUMNS = (
    "width", "cap_cm", "rho", "windows", "nan_s", "cad_s_p05_hz", "cad_s_p50_hz", "cad_s_p95_hz",
)  # fmt: skip
H_COLUMNS = (
    "kind", "width", "cap_cm", "cadence_hz", "rho", "kz", "lift_m", "lean_deg", "windows",
    "nan_s", "nan_h", "h_sd_p50_m", "cad_s_p50_hz", "cad_h_p50_hz", "rel_err_h_p50",
    "rel_err_h_p95", "abs_diff_p50_hz", "abs_diff_p90_hz",
)  # fmt: skip


@dataclass(frozen=True)
class Grid:
    widths: tuple[int, ...] = (25, 37, 50)
    caps_cm: tuple[int, ...] = (15, 20, 25)
    cadences_hz: tuple[float, ...] = (2.5, 3.0, 3.5, 4.3)
    rhos: tuple[float, ...] = (0.0, 0.5, 0.8, 0.9)
    windows_s: int = 40_000
    windows_h: int = 400
    lifts_m: tuple[float, ...] = tuple(round(0.10 + 0.05 * i, 2) for i in range(11))
    kzs: tuple[float, ...] = (1.0, 1.5)
    swap_lift_m: float = 0.30
    lean_deg: tuple[int, ...] = (10, 20)
    separation_m: float = SEPARATION_M
    seed: int = SEED


PROTOCOL = Grid()


@dataclass(frozen=True)
class Windows:
    """The random part of n windows of `width` frames: the stride's phase at the first frame
    (n,), the `mae` of the left and right ankle in each frame, in metres (n, width, 2), and the
    standard error of each ankle along d (`along`) and in z (`up`, None when no h is wanted),
    an AR(1) along the frames (n, width, 2)."""

    phase: Array
    mae: Array
    along: Array
    up: Array | None


def clip_mae(clip: dict[str, Any]) -> tuple[float, Array]:
    """The clip's fps and the 29 `mae` (cm) of every skeleton in it (the clip has whole mm)."""
    if clip["joints"] != list(JOINTS):
        raise ValueError("the clip's joints are not in the order of JOINTS")
    rows = [p[4][1] for f in clip["frames"] for p in f["p"] if p[4] is not None]
    return float(clip["fps"]), np.array(rows, dtype=np.float64) / 10.0


def under_cap(mae_cm: Array, cap_cm: float) -> Array:
    """The skeletons whose two ankles are at or under the cap (the cap of `gait.windows`)."""
    return mae_cm[np.all(mae_cm[:, gait.ANKLES] <= cap_cm, axis=1)]


def _key(value: float) -> int:
    return int(round(value * 100))


def _rng(seed: int, kind: str, *key: float) -> np.random.Generator:
    return np.random.default_rng([seed, KINDS.index(kind), *(_key(k) for k in key)])


def _ar1(rng: np.random.Generator, shape: tuple[int, int, int], rho: float) -> Array:
    e = rng.standard_normal(shape)
    if rho:
        c = math.sqrt(1.0 - rho * rho)
        for t in range(1, shape[1]):
            e[:, t] = rho * e[:, t - 1] + c * e[:, t]
    return e


def draw_windows(
    rng: np.random.Generator,
    n: int,
    *,
    width: int,
    mae_rows_cm: Array,
    rho: float,
    vertical: bool,
) -> Windows:
    phase = rng.uniform(0.0, 2.0 * math.pi, size=n)
    pick = rng.integers(len(mae_rows_cm), size=(n, width))
    mae = mae_rows_cm[:, gait.ANKLES][pick] / 100.0
    along = _ar1(rng, (n, width, 2), rho)
    up = _ar1(rng, (n, width, 2), rho) if vertical else None
    return Windows(phase, mae, along, up)


def signals(
    w: Windows,
    *,
    fps: float,
    cadence_hz: float,
    separation_m: float,
    lift_m: float = 0.0,
    kz: float = 1.0,
    swap: bool = False,
    lean_deg: float = 0.0,
) -> tuple[Array, Array | None]:
    """(s, h) of every window (n, width); h is None when `w` has no vertical error."""
    width = w.mae.shape[1]
    psi = math.pi * cadence_hz * (np.arange(width) / fps)[None, :] + w.phase[:, None]
    forward = separation_m * np.sin(psi)  # left ankle minus right ankle, along d
    up = lift_m * np.maximum(np.cos(psi), 0.0) - lift_m * np.maximum(-np.cos(psi), 0.0)
    lean = math.radians(lean_deg)  # the body's (forward, up) plane turned by `lean`
    s_clean = math.cos(lean) * forward - math.sin(lean) * up
    h_clean = math.sin(lean) * forward + math.cos(lean) * up
    if swap:  # the ankle ahead is called left in every frame, by the geometry of the body
        sign = np.where(s_clean < 0, -1.0, 1.0)
        s_clean, h_clean = sign * s_clean, sign * h_clean
    s = s_clean + (w.mae[..., 0] * w.along[..., 0] - w.mae[..., 1] * w.along[..., 1])
    if w.up is None:
        return s, None
    return s, h_clean + kz * (w.mae[..., 0] * w.up[..., 0] - w.mae[..., 1] * w.up[..., 1])


def _r(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 6)


def _q(values: Array, q: float) -> float | None:
    return _r(float(np.percentile(values, q))) if values.size else None


def s_windows(mae_cm: Array, grid: Grid, width: int, cap: int, cadence: float,
              rho: float) -> Windows:  # fmt: skip
    """The windows of the row of s of (W, cap, cadence, rho): the stream `s_row` draws, which
    does not depend on the separation (phase B2 re-judges the bar on it at another one)."""
    return draw_windows(
        _rng(grid.seed, "s", width, cap, cadence, rho),
        grid.windows_s,
        width=width,
        mae_rows_cm=under_cap(mae_cm, cap),
        rho=rho,
        vertical=False,
    )


def s_row(mae_cm: Array, fps: float, grid: Grid, width: int, cap: int, cadence: float,
          rho: float) -> list[Any]:  # fmt: skip
    w = s_windows(mae_cm, grid, width, cap, cadence, rho)
    s, _ = signals(w, fps=fps, cadence_hz=cadence, separation_m=grid.separation_m)
    cad = gait.cadence_hz_batch(s, fps=fps)
    finite = cad[np.isfinite(cad)]
    rel = np.abs(finite - cadence) / cadence
    nan = int(len(cad) - len(finite))
    row = [width, cap, cadence, rho, len(cad), nan, _q(finite, 50), _q(rel, 50), _q(rel, 95)]
    return [*row, meets_bar(row)]


def meets_bar(row: list[Any]) -> bool:
    """The bar on a row of s, from the rounded figures it holds and the constants as they are:
    p95 of the relative error <= `BAR_P95` and NaN in s <= `BAR_NAN` of the windows."""
    windows, nan, p95 = row[4], row[5], row[8]
    return bool(p95 is not None and p95 <= BAR_P95 and nan <= BAR_NAN * windows)


def twin_windows(mae_cm: Array, grid: Grid, width: int, cap: int, rho: float) -> Windows:
    """The noise twin's windows of (W, cap, rho): the same stream `noise_pool` regenerates."""
    return draw_windows(
        _rng(grid.seed, "twin", width, cap, rho),
        grid.windows_s,
        width=width,
        mae_rows_cm=under_cap(mae_cm, cap),
        rho=rho,
        vertical=False,
    )


def twin_row(mae_cm: Array, fps: float, grid: Grid, width: int, cap: int,
             rho: float) -> list[Any]:  # fmt: skip
    w = twin_windows(mae_cm, grid, width, cap, rho)
    s, _ = signals(w, fps=fps, cadence_hz=0.0, separation_m=0.0)
    cad = gait.cadence_hz_batch(s, fps=fps)
    finite = cad[np.isfinite(cad)]
    nan = int(len(cad) - len(finite))
    return [width, cap, rho, len(cad), nan, _q(finite, 5), _q(finite, 50), _q(finite, 95)]


def noise_pool(
    mae_cm: Array,
    fps: float,
    *,
    width: int,
    cap: int,
    rho: float,
    grid: Grid = PROTOCOL,
    draws: int = gait.DRAWS,
    chunk: int = 500,
) -> Pool:
    """The noise twin of (W, cap, rho), the very windows of its row, and for each `draws`
    copies with white N(0, mae) added to each ankle along d, as `gait.propagated_error` adds it
    (midHip's share cancels in s). For phase B2's simulator of M1 and M2."""
    w = twin_windows(mae_cm, grid, width, cap, rho)
    s, _ = signals(w, fps=fps, cadence_hz=0.0, separation_m=0.0)
    cadence = gait.cadence_hz_batch(s, fps=fps)
    rng = _rng(grid.seed, "pool_mc", width, cap, rho, draws)
    return Pool(cadence, _copies(rng, s, w.mae, fps=fps, draws=draws, chunk=chunk))


def _copies(
    rng: np.random.Generator, s: Array, mae: Array, *, fps: float, draws: int, chunk: int
) -> Array:
    """The cadence of `draws` copies of each window of `s`, white N(0, mae) on each ankle."""
    width = s.shape[1]
    out = np.empty((len(s), draws))
    for lo in range(0, len(s) if draws else 0, chunk):
        hi = min(lo + chunk, len(s))
        e = rng.standard_normal((hi - lo, draws, width, 2)) * mae[lo:hi, None]
        copies = s[lo:hi, None, :] + (e[..., 0] - e[..., 1])
        out[lo:hi] = gait.cadence_hz_batch(copies.reshape(-1, width), fps=fps).reshape(-1, draws)
    return out


def sane_pool(
    mae_cm: Array,
    fps: float,
    *,
    width: int,
    cap: int,
    cadence: float,
    rho: float,
    separation_m: float,
    band: str,
    windows: int,
    grid: Grid = PROTOCOL,
    draws: int = gait.DRAWS,
    chunk: int = 500,
) -> Pool:
    """`windows` sane windows of (W, cap, cadence, rho) whose ankles part by `separation_m`, on
    the stream of their `band` ("high" or "low"), with `draws` copies each as `noise_pool` adds
    them (none for the low band, whose draws M2 never reads): the condition that a sane
    instrument survives M1 and M2 (phase B2)."""
    rng = _rng(grid.seed, f"sane_{band}", width, cap, cadence, rho)
    w = draw_windows(
        rng, windows, width=width, mae_rows_cm=under_cap(mae_cm, cap), rho=rho, vertical=False
    )
    s, _ = signals(w, fps=fps, cadence_hz=cadence, separation_m=separation_m)
    cad = gait.cadence_hz_batch(s, fps=fps)
    return Pool(cad, _copies(rng, s, w.mae, fps=fps, draws=draws, chunk=chunk))


def _h_specs(grid: Grid) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every informative row of h, in the file's order: (kind, its parameters)."""
    for width in grid.widths:
        for cap in grid.caps_cm:
            for rho in grid.rhos:
                for kz in grid.kzs:
                    base = {"width": width, "cap": cap, "rho": rho, "kz": kz}
                    yield "no_gait", {**base, "cadence": None, "lift": 0.0, "lean": 0}
                    for cadence in grid.cadences_hz:
                        at = {**base, "cadence": cadence}
                        for lift in grid.lifts_m:
                            yield "sane", {**at, "lift": lift, "lean": 0}
                        yield "flat_h", {**at, "lift": 0.0, "lean": 0}
                        yield "swap", {**at, "lift": grid.swap_lift_m, "lean": 0}
                        for lean in grid.lean_deg:
                            yield "lean", {**at, "lift": 0.0, "lean": lean}


def h_row(mae_cm: Array, fps: float, grid: Grid, kind: str, p: dict[str, Any]) -> list[Any]:
    cadence = p["cadence"]
    w = draw_windows(
        _rng(
            grid.seed,
            kind,
            *(p[k] or 0.0 for k in ("width", "cap", "cadence", "rho", "kz", "lift", "lean")),
        ),
        grid.windows_h,
        width=p["width"],
        mae_rows_cm=under_cap(mae_cm, p["cap"]),
        rho=p["rho"],
        vertical=True,
    )
    s, h = signals(
        w,
        fps=fps,
        cadence_hz=cadence or 0.0,
        separation_m=0.0 if cadence is None else grid.separation_m,
        lift_m=p["lift"],
        kz=p["kz"],
        swap=kind == "swap",
        lean_deg=p["lean"],
    )
    assert h is not None
    cad_s, cad_h = gait.cadence_hz_batch(s, fps=fps), gait.cadence_hz_batch(h, fps=fps)
    fs, fh = np.isfinite(cad_s), np.isfinite(cad_h)
    rel_h = np.abs(cad_h[fh] - cadence) / cadence if cadence else np.empty(0)
    diff = np.abs(cad_s[fs & fh] - cad_h[fs & fh])
    return [
        kind, p["width"], p["cap"], cadence, p["rho"], p["kz"], p["lift"], p["lean"], len(s),
        int(np.sum(~fs)), int(np.sum(~fh)), _q(np.std(h, axis=1), 50), _q(cad_s[fs], 50),
        _q(cad_h[fh], 50), _q(rel_h, 50), _q(rel_h, 95), _q(diff, 50), _q(diff, 90),
    ]  # fmt: skip


def bar_cells(s_rows: list[list[Any]], grid: Grid) -> list[dict[str, Any]]:
    """Per (W, cap): does every cadence meet the bar at rho 0? Judged again from each row's
    figures with `meets_bar`, never from the row's own flag."""
    at = {(r[0], r[1], r[2]): r for r in s_rows if r[3] == BAR_RHO}
    cells = []
    for width in grid.widths:
        for cap in grid.caps_cm:
            failing = [c for c in grid.cadences_hz if not meets_bar(at[(width, cap, c)])]
            cells.append(
                {
                    "width": width,
                    "cap_cm": cap,
                    "passes": not failing,
                    "failing_cadences_hz": failing,
                }
            )
    return cells


def build_sweep(
    mae_cm: Array, fps: float, clip_sha256: str, grid: Grid = PROTOCOL
) -> dict[str, Any]:
    s_rows = [
        s_row(mae_cm, fps, grid, width, cap, cadence, rho)
        for width in grid.widths
        for cap in grid.caps_cm
        for cadence in grid.cadences_hz
        for rho in grid.rhos
    ]
    twins = [
        twin_row(mae_cm, fps, grid, width, cap, rho)
        for width in grid.widths
        for cap in grid.caps_cm
        for rho in grid.rhos
    ]
    h_rows = [h_row(mae_cm, fps, grid, kind, p) for kind, p in _h_specs(grid)]
    return {
        "schema_version": SCHEMA_VERSION,
        "task": 60,
        "phase": "B1",
        "written": WRITTEN,
        "seed": grid.seed,
        "source": {
            "clip": CLIP_NAME,
            "sha256": clip_sha256,
            "skeletons": len(mae_cm),
            "fps": fps,
            "skeletons_under_cap": {str(c): len(under_cap(mae_cm, c)) for c in grid.caps_cm},
            "cap_joints": [JOINTS[j] for j in gait.ANKLES],
        },
        "parameters": {
            "widths": list(grid.widths),
            "caps_cm": list(grid.caps_cm),
            "cadences_hz": list(grid.cadences_hz),
            "rhos": list(grid.rhos),
            "windows_s": grid.windows_s,
            "windows_h": grid.windows_h,
            "separation_m": _r(grid.separation_m),
            "separation": "5.5 / 4.3 m in every cadence (plan hypotheses, no source)",
            "lifts_m": list(grid.lifts_m),
            "kzs": list(grid.kzs),
            "swap_lift_m": grid.swap_lift_m,
            "lean_deg": list(grid.lean_deg),
            "band_z": gait.BAND_Z,
            "nan_rule": "first local max with r[k] > 0 after the first r[k] < 0; NaN if none or "
            "if r[k] / r[0] <= band_z / sqrt(n - k) (reading A)",
            "noise": "per ankle and frame, sd = its p90_mae_cm in a skeleton of the clip under "
            "the cap drawn per frame; along d N(0, mae), in z kz x as large; AR(1) along the "
            "frames with coefficient rho",
            "rel_err": "|cad_s - planted| / planted over the windows with a finite cad_s",
        },
        "bar": {
            "p95_rel_err_max": BAR_P95,
            "nan_s_max": BAR_NAN,
            "rho": BAR_RHO,
            "rule": "a (W, cap) cell passes when every cadence meets the bar at rho 0; at rho "
            "0.5 to 0.9 meets_bar is printed and judged by no rule",
            "cells": bar_cells(s_rows, grid),
        },
        "s_rows": {"columns": list(S_COLUMNS), "rows": s_rows},
        "noise_twins": {"columns": list(TWIN_COLUMNS), "rows": twins},
        "h_rows": {
            "note": "informative, read by no rule: sane, the broken rows no_gait (i) and "
            "flat_h (ii), the blind spots swap and lean; abs_diff over the windows with both "
            "cadences finite; rel_err_h against the planted cadence",
            "columns": list(H_COLUMNS),
            "rows": h_rows,
        },
    }


def render(value: Any, indent: int = 0) -> str:
    """JSON with two spaces per level and every list of scalars on one line (a row per line)."""
    pad = "  " * indent
    if isinstance(value, dict) and value:
        items = [f"{pad}  {json.dumps(k)}: {render(v, indent + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
        items = [f"{pad}  {render(v, indent + 1)}" for v in value]
        return "[\n" + ",\n".join(items) + f"\n{pad}]"
    return json.dumps(value, allow_nan=False)


def _summary(report: dict[str, Any]) -> str:
    passing = [f"W{c['width']}/{c['cap_cm']}" for c in report["bar"]["cells"] if c["passes"]]
    return (
        f"pose sweep: {len(report['s_rows']['rows'])} s rows, "
        f"{len(report['noise_twins']['rows'])} noise twins, "
        f"{len(report['h_rows']['rows'])} h rows; "
        f"cells meeting the bar at rho 0: {', '.join(passing) or 'none'}"
    )


def run_pose_sweep(
    reports_dir: Path,
    clip: Path = CLIP,
    *,
    check: bool = False,
    grid: Grid = PROTOCOL,
) -> int:
    if not clip.is_file():
        print(f"pose sweep: the clip {clip} is missing; nothing to sweep")
        return 1
    raw = clip.read_bytes()
    fps, mae = clip_mae(json.loads(raw))
    started = time.perf_counter()
    report = build_sweep(mae, fps, hashlib.sha256(raw).hexdigest(), grid)
    text = render(report) + "\n"
    print(f"{_summary(report)} ({time.perf_counter() - started:.1f} s)")
    target = reports_dir / SWEEP_NAME
    if not check:
        reports_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"pose sweep: {target} ({len(text.encode())} bytes)")
        return 0
    if not target.is_file():
        print(f"pose sweep --check: {target} is missing")
        return 1
    if target.read_bytes() != text.encode():
        versioned = json.loads(target.read_text(encoding="utf-8"))
        bad = [k for k in report if versioned.get(k) != json.loads(render(report[k]))]
        print(
            f"pose sweep --check: {target} differs from the regenerated sweep in {bad or 'bytes'}"
        )
        return 1
    print(
        f"pose sweep --check: FULL; every row regenerated from the clip (sha256 "
        f"{report['source']['sha256'][:12]}) and the bytes are equal; no data root read"
    )
    return 0
