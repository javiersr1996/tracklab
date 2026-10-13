"""Bronze of the football Body Pose: ``bodypose_players`` and ``bodypose_frames`` (task 58).

Reads the single ``.jsonl`` member of ``raw/<match_id>.jsonl.zip`` (opendata-bodypose, ~3.3 GB
inflated per match) as a text stream, one line at a time through ``pose.jsonl``: the member is
never extracted to disk and never held whole. Batches of ``BATCH_FRAMES`` frames go straight to
two Parquet files per match.

- ``bodypose_players``: one row per frame-player **with a pose**. A player whose ``joints`` is
  null has no row here (the provider has no pose for them and nothing is invented); that player
  still counts in the frame's ``n_players`` and ``player_ids`` of ``bodypose_frames``, which is
  what gives the coverage its denominator without storing ~4.9M null rows.
  ``joints`` is 29 x (x, y, z) metres in the order of ``JOINTS`` (mapped by name by the reader,
  never by position: the files order the keys differently from the README) and ``mae`` the 29
  ``p90_mae_cm`` in the same order. ``x``/``y`` are the pose file's own, not the tracking's.
- ``bodypose_frames``: one row per line of the file, in the file's own frame numbering (25 fps,
  ``pose_frame = 2.5 * tracking_frame``). The file opens with frames outside every period
  (``period``, ``timestamp`` and the ball null, no players): they are rows with ``n_players = 0``,
  as in ``tracking_frames``. The period is the file's ``period`` field, never read from the
  ``timestamp``: the timestamp of the same frame differs between the file and the README.

``source_row`` is the line index of the member, ``frame`` the provider's counter.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from tracklab.bronze.common import LINEAGE_FIELDS, ParquetSink, batch_from_columns, bronze_path
from tracklab.ingest.manifest import FileEntry, Source
from tracklab.pose import jsonl
from tracklab.pose.jsonl import JOINTS, parse_frame

SPORT = "football"
SOURCE_ID = "opendata-bodypose"
BATCH_FRAMES = 10_000
N_JOINTS = len(JOINTS)
Log = Callable[[str], None]

BODYPOSE_PLAYERS = pa.schema(
    [
        *LINEAGE_FIELDS,
        pa.field("frame", pa.int64(), nullable=False),
        pa.field("period", pa.int16()),
        pa.field("player_id", pa.int64(), nullable=False),
        pa.field("x", pa.float64(), nullable=False),
        pa.field("y", pa.float64(), nullable=False),
        pa.field("is_detected", pa.bool_(), nullable=False),
        pa.field("joints", pa.list_(pa.float32(), 3 * N_JOINTS), nullable=False),
        pa.field("mae", pa.list_(pa.float32(), N_JOINTS), nullable=False),
    ]
)

BODYPOSE_FRAMES = pa.schema(
    [
        *LINEAGE_FIELDS,
        pa.field("frame", pa.int64(), nullable=False),
        pa.field("timestamp", pa.string()),
        pa.field("period", pa.int16()),
        pa.field("ball_x", pa.float64()),
        pa.field("ball_y", pa.float64()),
        pa.field("ball_z", pa.float64()),
        pa.field("ball_is_detected", pa.bool_()),
        pa.field("possession_group", pa.string()),
        pa.field("possession_player_id", pa.int64()),
        pa.field("n_players", pa.int16(), nullable=False),
        pa.field("n_with_pose", pa.int16(), nullable=False),
        pa.field("player_ids", pa.list_(pa.int64()), nullable=False),
    ]
)

TABLES = {"bodypose_players": BODYPOSE_PLAYERS, "bodypose_frames": BODYPOSE_FRAMES}


@dataclass(frozen=True)
class BodyposeStats:
    match_id: int
    frames: int
    players: int
    seconds: float
    mb: float


def frame_batches(
    path: Path, match_id: int, source_file: str, batch_frames: int = BATCH_FRAMES
) -> Iterator[tuple[pa.RecordBatch, pa.RecordBatch]]:
    """Pairs of (bodypose_frames batch, bodypose_players batch) per ``batch_frames`` lines."""
    frames: dict[str, list[Any]] = {name: [] for name in BODYPOSE_FRAMES.names[4:]}
    players: dict[str, list[Any]] = {
        name: [] for name in BODYPOSE_PLAYERS.names[4:] if name not in ("joints", "mae")
    }
    joints: list[Any] = []
    mae: list[Any] = []
    f_row: list[int] = []
    p_row: list[int] = []
    lineage = {"sport": SPORT, "match_id": match_id, "source_file": source_file}

    def flush() -> tuple[pa.RecordBatch, pa.RecordBatch]:
        n = len(p_row)
        flat_joints = np.concatenate(joints) if n else np.empty(0, np.float32)
        flat_mae = np.concatenate(mae) if n else np.empty(0, np.float32)
        fb = batch_from_columns(
            BODYPOSE_FRAMES, {**lineage, "source_row": f_row, **frames}, len(f_row)
        )
        pb = batch_from_columns(
            BODYPOSE_PLAYERS,
            {
                **lineage,
                "source_row": p_row,
                **players,
                "joints": pa.FixedSizeListArray.from_arrays(pa.array(flat_joints), 3 * N_JOINTS),
                "mae": pa.FixedSizeListArray.from_arrays(pa.array(flat_mae), N_JOINTS),
            },
            n,
        )
        f_row.clear()
        p_row.clear()
        joints.clear()
        mae.clear()
        for column in (*frames.values(), *players.values()):
            column.clear()
        return fb, pb

    with jsonl.open_lines(path) as lines:
        for row, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                frame = parse_frame(line)
            except (KeyError, ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"{source_file} line {row}: {exc}") from exc
            ball = frame.ball
            f_row.append(row)
            frames["frame"].append(frame.frame)
            frames["timestamp"].append(frame.timestamp)
            frames["period"].append(frame.period)
            frames["ball_x"].append(None if ball is None else ball[0])
            frames["ball_y"].append(None if ball is None else ball[1])
            frames["ball_z"].append(None if ball is None else ball[2])
            frames["ball_is_detected"].append(None if ball is None else ball[3])
            frames["possession_group"].append(frame.possession_group)
            frames["possession_player_id"].append(frame.possession_player_id)
            frames["n_players"].append(len(frame.players))
            frames["player_ids"].append([p.player_id for p in frame.players])
            posed = 0
            for p in frame.players:
                if p.xyz is None or p.mae_cm is None:
                    continue  # no pose: no row, never an invented one
                posed += 1
                p_row.append(row)
                players["frame"].append(frame.frame)
                players["period"].append(frame.period)
                players["player_id"].append(p.player_id)
                players["x"].append(p.x)
                players["y"].append(p.y)
                players["is_detected"].append(p.is_detected)
                joints.append(p.xyz.astype(np.float32).ravel())
                mae.append(p.mae_cm.astype(np.float32))
            frames["n_with_pose"].append(posed)
            if len(f_row) >= batch_frames:
                yield flush()
    if f_row:
        yield flush()


def build_bodypose_match(
    entry: FileEntry, raw_root: Path, data_dir: Path, commit: str
) -> BodyposeStats:
    """Write ``bodypose_frames/<id>.parquet`` and ``bodypose_players/<id>.parquet`` of one match."""
    assert entry.match_id is not None
    started = time.perf_counter()
    metadata = {
        "tracklab.sport": SPORT,
        "tracklab.source_file": entry.path,
        "tracklab.source_sha256": entry.sha256,
        "tracklab.source_commit": commit,
    }
    frames_path = bronze_path(data_dir, SPORT, "bodypose_frames", entry.match_id)
    players_path = bronze_path(data_dir, SPORT, "bodypose_players", entry.match_id)
    with (
        ParquetSink(frames_path, BODYPOSE_FRAMES, metadata) as frames,
        ParquetSink(players_path, BODYPOSE_PLAYERS, metadata) as players,
    ):
        for frames_batch, players_batch in frame_batches(
            raw_root / entry.path, entry.match_id, entry.path
        ):
            frames.write(frames_batch)
            players.write(players_batch)
    return BodyposeStats(
        match_id=entry.match_id,
        frames=frames.rows,
        players=players.rows,
        seconds=time.perf_counter() - started,
        mb=(frames.bytes + players.bytes) / 1e6,
    )


def build_bodypose(
    source: Source, raw_root: Path, data_dir: Path, log: Log = print
) -> list[BodyposeStats]:
    """Every full-match zip the manifest pins, in match id order, one line printed per match."""
    if source.commit is None:
        raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
    entries = sorted(
        (f for f in source.files if f.role == "bodypose_zip" and f.match_id is not None),
        key=lambda f: f.match_id or 0,
    )
    log(f"{'match_id':>8} {'frames':>8} {'players':>9} {'seconds':>8} {'MB':>7}")
    stats: list[BodyposeStats] = []
    for entry in entries:
        s = build_bodypose_match(entry, raw_root, data_dir, source.commit)
        log(f"{s.match_id:>8} {s.frames:>8} {s.players:>9} {s.seconds:>8.1f} {s.mb:>7.1f}")
        stats.append(s)
    return stats
