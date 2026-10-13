"""`tracklab pose coverage`: how much of each match the Body Pose actually covers (task 58).

Per match, per period and per player, with the denominator beside every count: the denominator
of a frame-player is what the file lists in `player_data` (`n_players` of `bodypose_frames`), not
a constant. The README counts 32 per frame for 1925299; 1996435 has 30. Everything is read from
the bronze Parquet by DuckDB; the file is the artefact `reports/pose_coverage.json`, versioned.

SkillCorner's three limits live here as numbers, not as a footer: the pose exists only for
detected players (`with_pose_detected` against `with_pose`), z is relative to the player's own
centroid (`z_m` is a range of that relative coordinate, never a height), and a whole match has
two periods, substitutions and long stretches without pose (`longest_run`, `runs_ge_*`, and the
`outside` pseudo-period of frames outside every period).

`--check` recomputes the matches whose bronze is whole (the file's lines 0..n, no cut) and
compares them with the versioned file. A slice, like the CI fixtures', cannot be recounted: it
prints `PARTIAL k/n` and verifies what it can (the versioned file holds every match of the
manifest); the whole warehouse prints `FULL n/n`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from tracklab.bronze.common import bronze_path
from tracklab.ingest.manifest import load_manifest
from tracklab.pose.jsonl import JOINTS

COVERAGE_NAME = "pose_coverage.json"
MANIFEST = Path("manifest/sources.json")
SOURCE_ID = "opendata-bodypose"
RUN_MINIMA = (25, 37, 50)  # frames: 1, 1.5 and 2 s at 25 fps
OUTSIDE = "outside"  # frames whose period is null: before kick-off, half-time, after the end
SCHEMA_VERSION = 1


def match_ids(manifest_path: Path = MANIFEST) -> list[int]:
    source = load_manifest(manifest_path).source(SOURCE_ID)
    return sorted(f.match_id for f in source.files if f.role == "bodypose_zip" and f.match_id)


def _paths(data_dir: Path, match_id: int) -> tuple[str, str]:
    return (
        bronze_path(data_dir, "football", "bodypose_frames", match_id).as_posix(),
        bronze_path(data_dir, "football", "bodypose_players", match_id).as_posix(),
    )


def is_whole(con: duckdb.DuckDBPyConnection, frames: str) -> bool:
    """The bronze holds every line of the member: `source_row` runs 0..n-1 without a cut."""
    row = con.execute(
        "select count(*), min(source_row), max(source_row) from read_parquet(?)", [frames]
    ).fetchone()
    assert row is not None
    n, lo, hi = row
    return bool(n) and lo == 0 and hi == n - 1


def _r(value: Any) -> Any:
    return round(float(value), 4) if value is not None else None


def _period_key(period: int | None) -> str:
    return OUTSIDE if period is None else str(period)


def _periods(con: duckdb.DuckDBPyConnection, frames: str, players: str) -> dict[str, Any]:
    by_frames = {
        _period_key(r[0]): r
        for r in con.execute(
            """
            select period, count(*), count(*) filter (where n_with_pose > 0),
                   sum(n_players), sum(n_with_pose), min(n_players), max(n_players),
                   min(n_with_pose) filter (where n_with_pose > 0), max(n_with_pose)
            from read_parquet(?) group by period
            """,
            [frames],
        ).fetchall()
    }
    by_players = {
        _period_key(r[0]): r
        for r in con.execute(
            """
            select period, count(*), count(*) filter (where is_detected), sum(len(mae))
            from read_parquet(?) group by period
            """,
            [players],
        ).fetchall()
    }
    out: dict[str, Any] = {}
    totals = [0, 0, 0, 0, 0, 0]
    ranges: list[tuple[int, int, int, int]] = []
    for key in sorted(by_frames):
        _, frames_n, with_any, pf, with_pose, nmin, nmax, smin, smax = by_frames[key]
        rows, detected, obs = by_players.get(key, (key, 0, 0, 0))[1:]
        if rows != with_pose:
            raise RuntimeError(f"period {key}: {rows} player rows, {with_pose} in the frames")
        out[key] = {
            "frames": frames_n,
            "frames_with_pose": with_any,
            "player_frames": int(pf),
            "with_pose": int(with_pose),
            "with_pose_detected": int(detected),
            "joint_observations": int(obs or 0),
            "players_per_frame": {"min": nmin, "max": nmax},
            "skeletons_per_frame": {
                "mean_over_frames_with_pose": _r(with_pose / with_any) if with_any else None,
                "min_over_frames_with_pose": smin,
                "max": smax,
            },
            "share_frames_with_pose": _r(with_any / frames_n),
            "share_player_frames_with_pose": _r(with_pose / pf) if pf else None,
        }
        for i, v in enumerate((frames_n, with_any, pf, with_pose, detected, obs or 0)):
            totals[i] += int(v)
        ranges.append((nmin, nmax, smin or 0, smax))
    frames_n, with_any, pf, with_pose, detected, obs = totals
    out["total"] = {
        "frames": frames_n,
        "frames_with_pose": with_any,
        "player_frames": pf,
        "with_pose": with_pose,
        "with_pose_detected": detected,
        "joint_observations": obs,
        "players_per_frame": {
            "min": min(r[0] for r in ranges if r[1]),
            "max": max(r[1] for r in ranges),
        },
        "skeletons_per_frame": {
            "mean_over_frames_with_pose": _r(with_pose / with_any),
            "min_over_frames_with_pose": min(r[2] for r in ranges if r[2]),
            "max": max(r[3] for r in ranges),
        },
        "share_frames_with_pose": _r(with_any / frames_n),
        "share_player_frames_with_pose": _r(with_pose / pf),
    }
    return out


def _players(con: duckdb.DuckDBPyConnection, frames: str, players: str) -> list[dict[str, Any]]:
    present = dict(
        con.execute(
            "select pid, count(*) from (select unnest(player_ids) as pid from read_parquet(?)) "
            "group by pid",
            [frames],
        ).fetchall()
    )
    posed = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            "select player_id, count(*), count(*) filter (where is_detected) "
            "from read_parquet(?) group by player_id",
            [players],
        ).fetchall()
    }
    minima = ", ".join(f"count(*) filter (where len >= {m})" for m in RUN_MINIMA)
    runs = {
        r[0]: r[1:]
        for r in con.execute(
            f"""
            with s as (
              select player_id, period, frame,
                     frame - row_number() over (partition by player_id, period order by frame) g
              from read_parquet(?)
            ), r as (select player_id, count(*) len from s group by player_id, period, g)
            select player_id, max(len), {minima} from r group by player_id
            """,
            [players],
        ).fetchall()
    }
    out = []
    for pid in sorted(present):
        with_pose, detected = posed.get(pid, (0, 0))
        longest, *counts = runs.get(pid, (0, *([0] * len(RUN_MINIMA))))
        out.append(
            {
                "player_id": int(pid),
                "frames_present": int(present[pid]),
                "with_pose": int(with_pose),
                "with_pose_detected": int(detected),
                "longest_run": int(longest),
                **{f"runs_ge_{m}": int(c) for m, c in zip(RUN_MINIMA, counts, strict=True)},
            }
        )
    unknown = set(posed) - set(present)
    if unknown:
        raise RuntimeError(f"players with pose that no frame lists: {sorted(unknown)}")
    return out


def _run_lengths(con: duckdb.DuckDBPyConnection, players: str) -> list[dict[str, int]]:
    """The three commonest lengths of a stretch of consecutive frames with pose, over every
    player and period: how the pose arrives, which the per-player maxima alone do not say."""
    rows = con.execute(
        """
        with s as (
          select player_id, period,
                 frame - row_number() over (partition by player_id, period order by frame) g
          from read_parquet(?)
        ), r as (select count(*) len from s group by player_id, period, g)
        select len, count(*) n from r group by len order by n desc, len limit 3
        """,
        [players],
    ).fetchall()
    return [{"length": int(length), "count": int(n)} for length, n in rows]


def _mae(con: duckdb.DuckDBPyConnection, players: str) -> dict[str, Any]:
    allv = con.execute(
        "select min(m), quantile_cont(m, 0.5), quantile_cont(m, 0.9), max(m) "
        "from (select unnest(mae)::double as m from read_parquet(?))",
        [players],
    ).fetchone()
    assert allv is not None
    cols = ", ".join(
        f"min(mae[{j}]::double), quantile_cont(mae[{j}]::double, [0.5, 0.9]), max(mae[{j}]::double)"
        for j in range(1, len(JOINTS) + 1)
    )
    row = con.execute(f"select {cols} from read_parquet(?)", [players]).fetchone()
    assert row is not None
    by_joint = {}
    for i, name in enumerate(JOINTS):
        lo, (p50, p90), hi = row[3 * i : 3 * i + 3]
        by_joint[name] = {"min": _r(lo), "p50": _r(p50), "p90": _r(p90), "max": _r(hi)}
    return {
        "all": {"min": _r(allv[0]), "p50": _r(allv[1]), "p90": _r(allv[2]), "max": _r(allv[3])},
        "by_joint": by_joint,
    }


def _z(con: duckdb.DuckDBPyConnection, players: str) -> dict[str, float | None]:
    """The range of z as delivered: relative to each player's centroid, not a height."""
    cols = ", ".join(
        f"min(joints[{3 * j + 3}]::double), max(joints[{3 * j + 3}]::double)"
        for j in range(len(JOINTS))
    )
    row = con.execute(f"select {cols} from read_parquet(?)", [players]).fetchone()
    assert row is not None
    values = [v for v in row if v is not None]
    if not values:
        return {"min": None, "max": None}
    return {"min": _r(min(values)), "max": _r(max(values))}


def coverage_match(data_dir: Path, match_id: int) -> dict[str, Any] | None:
    """The coverage of one match, or None when its bronze is absent or only a slice."""
    frames, players = _paths(data_dir, match_id)
    if not (Path(frames).is_file() and Path(players).is_file()):
        return None
    con = duckdb.connect()
    if not is_whole(con, frames):
        return None
    return {
        "periods": _periods(con, frames, players),
        "players": _players(con, frames, players),
        "common_run_lengths": _run_lengths(con, players),
        "mae_cm": _mae(con, players),
        "z_m": _z(con, players),
        # Any other key set is refused by the reader (`PoseFormatError`): a bronze that exists
        # was read to the end with one.
        "joint_key_sets": 1,
    }


def build_report(data_dir: Path, ids: list[int]) -> tuple[dict[str, Any], list[int]]:
    """(the report over the matches that can be recounted, the ids that could not)."""
    matches: dict[str, Any] = {}
    skipped: list[int] = []
    for mid in ids:
        m = coverage_match(data_dir, mid)
        if m is None:
            skipped.append(mid)
        else:
            matches[str(mid)] = m
    return {"schema_version": SCHEMA_VERSION, "joints": list(JOINTS), "matches": matches}, skipped


def _dump(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=False) + "\n"


def run_pose_coverage(
    data_dir: Path,
    reports_dir: Path,
    check: bool = False,
    manifest_path: Path = MANIFEST,
) -> int:
    ids = match_ids(manifest_path)
    target = reports_dir / COVERAGE_NAME
    report, skipped = build_report(data_dir, ids)
    done = len(ids) - len(skipped)
    for mid, m in report["matches"].items():
        t = m["periods"]["total"]
        print(
            f"pose coverage {mid}: frames={t['frames']} with_pose={t['frames_with_pose']} "
            f"player_frames={t['player_frames']} with_pose={t['with_pose']} "
            f"({t['share_player_frames_with_pose']})"
        )
    if not check:
        if skipped:
            print(f"pose coverage: no whole bronze for {skipped}; nothing written")
            return 1
        reports_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump(report), encoding="utf-8", newline="\n")
        print(f"pose coverage: FULL {done}/{len(ids)} written to {target}")
        return 0
    if not target.is_file():
        print(f"pose coverage --check: {target} is missing")
        return 1
    versioned = json.loads(target.read_text(encoding="utf-8"))
    if sorted(versioned["matches"], key=int) != [str(i) for i in ids]:
        print(f"pose coverage --check: {target} does not hold the manifest's matches {ids}")
        return 1
    bad = [mid for mid, m in report["matches"].items() if versioned["matches"][mid] != m]
    if bad:
        print(f"pose coverage --check: {target} differs from the bronze for {bad}")
        return 1
    status = f"FULL {done}/{len(ids)}" if not skipped else f"PARTIAL {done}/{len(ids)}"
    print(
        f"pose coverage --check: {status}; {done} match(es) recounted and equal, "
        f"{len(skipped)} only a slice or absent; the versioned file lists {ids}"
    )
    return 0
