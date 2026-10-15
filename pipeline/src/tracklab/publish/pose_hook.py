"""The clips of `tracklab publish pose` that come from the bronze of a whole match (task 62 of
tasks/todo.md, P6): the hook clip of each match when P6 lives or is unreplicated, the stretch of
most skeletons when it died.

A clip is 4 s (100 frames at 25 fps) inside one period, in the schema of the sample's clip
(`web/lib/pose/schema.json`), plus `selection` (the rule that chose it) and `windows` (the
windows of the hook player that fit inside it, with their frames, s(t), cadence and its sd).

* **Hook.** The window of the high band, among the high windows of the match with a finite
  cadence of s, whose cadence is nearest to the median of those cadences; a tie goes to the
  smaller (player_id, frame). Never the maximum. The windows are `verdict.window_estimates`
  at the frozen (W, cap), the same the metric counts; the clip starts `PRE` frames before the
  window and is moved inside its period if it does not fit.
* **Stretch.** Without a metric: the 100 consecutive frames of one period with most skeletons
  (sum of `n_with_pose`); a tie goes to the smaller first frame.

The bronze keeps no row for a player without a pose, so its `x`, `y` are not there: a clip from
the bronze lists only the players with joints in each frame (the sample's clip also lists the
others as discs). Nothing is interpolated or carried over. The coverage block counts every
player the frame lists (`bodypose_frames.n_players`), so its denominators are the file's.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from numpy.typing import NDArray

from tracklab.bronze.common import bronze_path
from tracklab.ingest.manifest import FileEntry
from tracklab.pose import criteria, gait
from tracklab.pose.data import PoseRows, require_readable
from tracklab.pose.jsonl import PoseFrame, PosePlayer
from tracklab.pose.verdict import Window
from tracklab.publish import pose as base

CLIP_FRAMES = 100  # 4 s at 25 fps
PRE = 25  # frames of the clip before the hook window
FPS = base.FPS

HOOK_RULE = (
    "the high-band window whose cad_s is nearest to the median cad_s of the match's high "
    "windows (finite ones); ties to the smaller (player_id, frame); never the maximum"
)
STRETCH_RULE = (
    "the 100 consecutive frames of one period with most skeletons (sum of n_with_pose); "
    "ties to the smaller first frame"
)

Array = NDArray[np.float64]


@dataclass(frozen=True)
class FrameTable:
    """`bodypose_frames` of a match, in frame order: counts, ball and period per frame."""

    frame: NDArray[np.int64]
    period: list[int | None]
    n_players: NDArray[np.int64]
    n_with_pose: NDArray[np.int64]
    ball: list[tuple[float, float, bool | None] | None]

    def __post_init__(self) -> None:
        if np.any(np.diff(self.frame) != 1):
            raise base.PosePublishError("bodypose_frames is not one row per consecutive frame")


def read_frame_table(data_dir: Path, match_id: int) -> FrameTable:
    """The frame table: counts and the ball, no joint and no player position. Read only after
    the guard (`require_readable`) has let the match through."""
    require_readable(match_id)
    path = bronze_path(data_dir, "football", "bodypose_frames", match_id).as_posix()
    rows = (
        duckdb.connect()
        .execute(
            "select frame, period, n_players, n_with_pose, ball_x, ball_y, ball_is_detected "
            "from read_parquet(?) order by frame",
            [path],
        )
        .fetchall()
    )
    return FrameTable(
        np.array([r[0] for r in rows], dtype=np.int64),
        [None if r[1] is None else int(r[1]) for r in rows],
        np.array([r[2] for r in rows], dtype=np.int64),
        np.array([r[3] for r in rows], dtype=np.int64),
        [None if r[4] is None else (float(r[4]), float(r[5]), r[6]) for r in rows],
    )


def high_median_hz(windows: list[Window]) -> float:
    """The median cad_s of the match's high windows with a finite cadence."""
    cad = [w.estimate.cadence_hz for w in windows if w.band == "high"]
    cad = [c for c in cad if math.isfinite(c)]
    if not cad:
        raise base.PosePublishError("the match has no high window with a finite cadence")
    return float(np.median(cad))


def choose_hook(windows: list[Window]) -> Window:
    """The window nearest to the median cadence of the match; ties to (player_id, frame)."""
    median = high_median_hz(windows)
    pool = [w for w in windows if w.band == "high" and math.isfinite(w.estimate.cadence_hz)]
    return min(pool, key=lambda w: (abs(w.estimate.cadence_hz - median), w.player_id, w.frame))


def clip_range(
    first: int, width: int, table: FrameTable, period: int, n: int = CLIP_FRAMES
) -> tuple[int, int]:
    """`[lo, hi]` of `n` frames that holds the window from `first`, `PRE` frames before it when
    they exist, moved inside the frames of `period`."""
    inside = [int(f) for f, p in zip(table.frame, table.period, strict=True) if p == period]
    p_lo, p_hi = min(inside), max(inside)
    if p_hi - p_lo + 1 < n:
        raise base.PosePublishError(f"period {period} is shorter than a clip")
    lo = min(max(first - PRE, p_lo), p_hi - n + 1)
    if lo > first or lo + n - 1 < first + width - 1:
        raise base.PosePublishError("the window does not fit in a clip of this period")
    return lo, lo + n - 1


def choose_stretch(table: FrameTable, n: int = CLIP_FRAMES) -> tuple[int, int]:
    """The `n` consecutive frames of one period with most skeletons, ties to the first frame."""
    best: tuple[int, int, int] | None = None  # (skeletons, -first frame, first index)
    count = len(table.frame)
    csum = np.concatenate([[0], np.cumsum(table.n_with_pose)])
    for i in range(count - n + 1):
        period = table.period[i]
        if period is None or any(p != period for p in table.period[i : i + n]):
            continue
        key = (int(csum[i + n] - csum[i]), -int(table.frame[i]), i)
        if best is None or key > best:
            best = key
    if best is None:
        raise base.PosePublishError("no period holds a clip")
    first = int(table.frame[best[2]])
    return first, first + n - 1


def detected_flags(data_dir: Path, match_id: int, lo: int, hi: int) -> dict[tuple[int, int], bool]:
    """`is_detected` of the pose rows in `[lo, hi]`, by (player_id, frame): a flag, no position.
    Past the guard like everything that reads a match."""
    require_readable(match_id)
    path = bronze_path(data_dir, "football", "bodypose_players", match_id).as_posix()
    rows = (
        duckdb.connect()
        .execute(
            "select player_id, frame, is_detected from read_parquet(?) where frame between ? and ?",
            [path, lo, hi],
        )
        .fetchall()
    )
    return {(int(p), int(f)): bool(d) for p, f, d in rows}


def pose_frames(
    rows: PoseRows,
    table: FrameTable,
    detected: dict[tuple[int, int], bool],
    lo: int,
    hi: int,
) -> list[PoseFrame]:
    """The frames `[lo, hi]` as `PoseFrame`s: only the players with a pose have a row."""
    by_frame: dict[int, list[int]] = {}
    for i in np.flatnonzero((rows.frame >= lo) & (rows.frame <= hi)):
        by_frame.setdefault(int(rows.frame[i]), []).append(int(i))
    at = {int(f): i for i, f in enumerate(table.frame)}
    out = []
    for f in range(lo, hi + 1):
        j = at[f]
        ball = table.ball[j]
        if ball is None:
            raise base.PosePublishError(f"frame {f} has no ball")
        players = tuple(
            PosePlayer(
                int(rows.player_id[i]),
                float(rows.x[i]),
                float(rows.y[i]),
                detected[(int(rows.player_id[i]), f)],
                rows.joints[i].astype(np.float64),
                rows.mae_cm[i].astype(np.float64),
            )
            for i in by_frame.get(f, [])
        )
        out.append(PoseFrame(f, table.period[j], (ball[0], ball[1], 0.0, ball[2]), players))
    return out


def coverage_of(frames: list[PoseFrame], table: FrameTable) -> dict[str, Any]:
    """The clip's coverage with the file's denominators: every player a frame lists."""
    at = {int(f): i for i, f in enumerate(table.frame)}
    idx = [at[f.frame] for f in frames]
    listed = int(table.n_players[idx].sum())
    posed = int(table.n_with_pose[idx].sum())
    per_frame = [int(table.n_with_pose[i]) for i in idx]
    mae = np.concatenate([p.mae_cm for f in frames for p in f.players if p.mae_cm is not None])
    return {
        "frames": len(frames),
        "player_frames": listed,
        "with_joints": posed,
        "with_joints_share": round(posed / listed, 4),
        "joint_observations": int(mae.size),
        "skeletons_per_frame": {"min": min(per_frame), "max": max(per_frame)},
        "p90_mae_cm": {
            "min": round(float(mae.min()), 4),
            "median": round(float(np.median(mae)), 4),
            "p90": round(float(np.percentile(mae, 90)), 4),
            "max": round(float(mae.max()), 4),
        },
    }


def player_windows(
    rows: PoseRows,
    windows: list[Window],
    player_id: int,
    lo: int,
    hi: int,
    index: dict[int, int],
    width: int,
) -> list[dict[str, Any]]:
    """The windows of `player_id` that fit inside `[lo, hi]`: frames, s(t) in whole mm (the
    sign along his own displacement), cad_s and its sd over the Monte Carlo of that window
    (`window_seed`, the metric's), and the mean speed that put it in its band."""
    sl = dict(rows.players())[player_id]
    frame = rows.frame[sl]
    out = []
    for w in sorted((w for w in windows if w.player_id == player_id), key=lambda w: w.frame):
        if w.frame < lo or w.frame + width - 1 > hi:
            continue
        a = int(np.searchsorted(frame, w.frame))
        joints = rows.joints[sl][a : a + width].astype(np.float64)
        mae = rows.mae_cm[sl][a : a + width].astype(np.float64)
        xy = np.c_[rows.x[sl][a : a + width], rows.y[sl][a : a + width]]
        s = gait.signal(gait.centre_on_midhip(joints), gait.direction(xy))
        seed = gait.window_seed(rows.match_id, player_id, w.frame)
        draws = gait.monte_carlo(joints, xy, mae, fps=FPS, seed=seed)
        sd = criteria.propagated_sd(draws[None, :, 0])
        cad = w.estimate.cadence_hz
        out.append(
            {
                "player": index[player_id],
                "band": w.band,
                "frame_lo": w.frame,
                "frame_hi": w.frame + width - 1,
                "speed_m_s": round(w.speed_m_s, 6),
                "cadence_hz": round(cad, 6) if math.isfinite(cad) else None,
                "cadence_sd_hz": round(sd, 6) if math.isfinite(sd) else None,
                "s_mm": [int(v) for v in base.mm(s * 100.0)],
            }
        )
    return out


def hook_clip(
    clip: dict[str, Any],
    *,
    kind: str,
    rule: str,
    detail: dict[str, Any],
    windows: list[dict[str, Any]],
) -> dict[str, Any]:
    """The clip with its selection and windows, which the sample's clip does not carry."""
    return {**clip, "selection": {"kind": kind, "rule": rule, **detail}, "windows": windows}


def zip_entry(manifest_path: Path, match_id: int) -> FileEntry:
    from tracklab.ingest.manifest import load_manifest

    for entry in load_manifest(manifest_path).source("opendata-bodypose").files:
        if entry.role == "bodypose_zip" and entry.match_id == match_id:
            return entry
    raise base.PosePublishError(f"no bodypose zip of match {match_id} in {manifest_path}")


# --- the clips of a publication ----------------------------------------------------------


def clip_file(kind: str, match_id: int) -> str:
    return f"pose/{kind}_{match_id}.json"


def matches_to_clip(reports: dict[str, Any], status: str, dead_at: str | None) -> list[int]:
    """The matches whose bronze may be opened for a clip: the calibration match always; the
    confirmation one when its metric was read (alive, unreplicated, or dead at M4)."""
    split = reports["protocol"]["design"]["split"]
    calibration, confirmation = int(split["calibration"][0]), int(split["confirmation"][0])
    if status in ("alive", "unreplicated") or dead_at == "M4":
        return [calibration, confirmation]
    return [calibration]


def _clip_of_match(
    data_dir: Path, manifest_path: Path, reports: dict[str, Any], match_id: int, status: str
) -> dict[str, Any]:
    from tracklab.pose.data import load_players
    from tracklab.pose.verdict import window_estimates

    table = read_frame_table(data_dir, match_id)
    rows = load_players(data_dir, match_id)
    windows: list[Window] = []
    frozen = reports["protocol"].get("frozen") or {}
    width = int(frozen.get("width", 0))
    if status in ("alive", "unreplicated") and frozen:
        windows = window_estimates(rows, width, float(frozen["cap_cm"]), mc_bands=())
    hook = (
        choose_hook(windows)
        if any(w.band == "high" and math.isfinite(w.estimate.cadence_hz) for w in windows)
        else None
    )
    if hook is not None:
        lo, hi = clip_range(hook.frame, width, table, hook.period)
    else:
        lo, hi = choose_stretch(table)
    detected = detected_flags(data_dir, match_id, lo, hi)
    frames = pose_frames(rows, table, detected, lo, hi)
    con = duckdb.connect()
    ids = {p.player_id for f in frames for p in f.players}
    players, teams = base._players_block(con, data_dir, ids, match_id)
    surface = base._surface_block(con, data_dir, match_id)
    clip = base.build_clip(
        frames, zip_entry(manifest_path, match_id), players, teams, surface, match_id
    )
    clip["coverage"] = coverage_of(frames, table)
    index = base._player_index(players)
    if hook is None:
        skeletons = int(table.n_with_pose[(table.frame >= lo) & (table.frame <= hi)].sum())
        return hook_clip(
            clip,
            kind="stretch",
            rule=STRETCH_RULE,
            detail={"skeletons": skeletons},
            windows=[],
        )
    detail = {
        "player": index[hook.player_id],
        "player_id": hook.player_id,
        "window_frame": hook.frame,
        "width": width,
        "cadence_hz": round(hook.estimate.cadence_hz, 6),
        "match_median_hz": round(high_median_hz(windows), 6),
        "high_windows": sum(
            w.band == "high" and math.isfinite(w.estimate.cadence_hz) for w in windows
        ),
    }
    wins = player_windows(rows, windows, hook.player_id, lo, hi, index, width)
    return hook_clip(clip, kind="hook", rule=HOOK_RULE, detail=detail, windows=wins)


def build_clips(
    data_dir: Path, manifest_path: Path, reports: dict[str, Any], status: str, dead_at: str | None
) -> dict[str, dict[str, Any]]:
    """{relative file: clip} of every match the status lets open, in match order."""
    out = {}
    for match_id in matches_to_clip(reports, status, dead_at):
        clip = _clip_of_match(data_dir, manifest_path, reports, match_id, status)
        out[clip_file(clip["selection"]["kind"], match_id)] = clip
    return out


def record_of(file: str, text: str, clip: dict[str, Any]) -> dict[str, Any]:
    import hashlib

    data = text.encode("utf-8")
    return {
        "match_id": clip["match_id"],
        "kind": clip["selection"]["kind"],
        "file": file,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "period": clip["period"],
        "frame_lo": clip["frame_lo"],
        "frame_hi": clip["frame_hi"],
        "coverage": clip["coverage"],
        "selection": clip["selection"],
        "windows": [
            {
                k: w[k]
                for k in ("player", "band", "frame_lo", "frame_hi", "cadence_hz", "cadence_sd_hz")
            }
            for w in clip["windows"]
        ],
    }
