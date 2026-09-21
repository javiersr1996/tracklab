"""Bronze of the basketball tracking: ``tracking_frames`` and ``tracking_objects``.

Reads ``<match_id>_tracking_data.jsonl.gz`` line by line (never whole in memory) in
batches of 100k frames and writes one Parquet per match and table with the schemas
declared below. Bronze does not correct, filter or interpolate: every line becomes a
row of ``tracking_frames``, every player and ball entry a row of ``tracking_objects``,
and values are stored as delivered. Every correction belongs to silver.

Decisions that the other bronze builders copy, each with its reason:

- ``xyz`` becomes three DOUBLE columns ``x``, ``y``, ``z``: per-axis statistics and
  predicate pushdown, silver reads them without unnesting, and football delivers x
  and y as separate keys, so the two sports share one shape.
- ``isDetected`` is BOOLEAN. Players deliver it as int 0/1, the ball as float
  0.0/1.0: the same fact in two encodings, unified by a cast that accepts exactly 0
  and 1 and fails on anything else (a 0.5 would be a change of meaning, not of
  encoding).
- ``shotClock`` is DOUBLE and nullable: the JSON carries null, floats and whole
  seconds as ints (24 next to 24.0); int to double is exact.
- ``predError`` and ``z`` are stored as delivered: negative ``predError`` exists and
  the players' ``z`` is a constant 0.0 (a filler, not a measurement). Silver sends
  the players' z to NULL; bronze keeps the provider's value.
- An empty frame (no players, ``ball: {}``) is a row of ``tracking_frames`` with
  ``n_home = n_away = 0`` and ``has_ball = false`` and no row in ``tracking_objects``:
  the timeline the provider delivered lives complete in bronze, and silver decides
  what to drop. A frame absent from the file stays absent: ``frameIdx`` jumps at
  every break (gaps of 593 and 2075 frames exist), and bronze never fills a gap
  because that would fabricate frames the provider never delivered. ``source_row``
  next to ``frameIdx`` keeps the two kinds of absence apart.
"""

from __future__ import annotations

import gzip
import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa

from tracklab.bronze.common import LINEAGE_FIELDS, ParquetSink, batch_from_columns, bronze_path
from tracklab.ingest.manifest import FileEntry, Source

SPORT = "basketball"
BATCH_FRAMES = 100_000
Log = Callable[[str], None]

# Exactly the keys the provider delivers. One more or one less fails the run.
FRAME_KEYS = frozenset(
    {
        "frameIdx",
        "wallClock",
        "gameClock",
        "gameClockStopped",
        "period",
        "homePlayers",
        "awayPlayers",
        "ball",
        "shotClock",
    }
)
PLAYER_KEYS = frozenset({"xyz", "speed", "predError", "jersey", "isDetected", "playerId"})
BALL_KEYS = frozenset({"xyz", "speed", "isDetected", "predError"})

TRACKING_FRAMES = pa.schema(
    [
        *LINEAGE_FIELDS,
        pa.field("frameIdx", pa.int64(), nullable=False),
        pa.field("wallClock", pa.int64(), nullable=False),
        pa.field("gameClock", pa.float64(), nullable=False),
        pa.field("gameClockStopped", pa.bool_(), nullable=False),
        pa.field("period", pa.int16(), nullable=False),
        pa.field("shotClock", pa.float64()),
        pa.field("n_home", pa.int16(), nullable=False),
        pa.field("n_away", pa.int16(), nullable=False),
        pa.field("has_ball", pa.bool_(), nullable=False),
    ]
)

TRACKING_OBJECTS = pa.schema(
    [
        *LINEAGE_FIELDS,
        pa.field("frameIdx", pa.int64(), nullable=False),
        pa.field("side", pa.string(), nullable=False),  # 'home' | 'away' | 'ball'
        pa.field("playerId", pa.int64()),  # null for the ball, which carries no id
        pa.field("jersey", pa.string()),  # null for the ball
        pa.field("x", pa.float64(), nullable=False),
        pa.field("y", pa.float64(), nullable=False),
        pa.field("z", pa.float64(), nullable=False),
        pa.field("speed", pa.float64(), nullable=False),
        pa.field("isDetected", pa.bool_(), nullable=False),
        pa.field("predError", pa.float64(), nullable=False),
    ]
)

TABLES = {"tracking_frames": TRACKING_FRAMES, "tracking_objects": TRACKING_OBJECTS}


@dataclass(frozen=True)
class TrackingStats:
    match_id: int
    frames: int
    objects: int
    seconds: float
    mb: float


def iter_frames(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """(line number, frame) for every line of the gzipped JSONL, one line at a time."""
    with gzip.open(path, "rb") as fh:
        for row, line in enumerate(fh):
            yield row, json.loads(line)


def _detected(value: object) -> bool:
    if value == 1:
        return True
    if value == 0:
        return False
    raise ValueError(f"isDetected={value!r} is not 0 or 1")


def frame_batches(
    path: Path, match_id: int, source_file: str, batch_frames: int = BATCH_FRAMES
) -> Iterator[tuple[pa.RecordBatch, pa.RecordBatch]]:
    """Pairs of (tracking_frames batch, tracking_objects batch) per ``batch_frames`` lines."""
    frames: dict[str, list[Any]] = {name: [] for name in TRACKING_FRAMES.names[4:]}
    objects: dict[str, list[Any]] = {name: [] for name in TRACKING_OBJECTS.names[4:]}
    f_row: list[int] = []
    o_row: list[int] = []
    lineage = {"sport": SPORT, "match_id": match_id, "source_file": source_file}

    def flush() -> tuple[pa.RecordBatch, pa.RecordBatch]:
        fb = batch_from_columns(
            TRACKING_FRAMES, {**lineage, "source_row": f_row, **frames}, len(f_row)
        )
        ob = batch_from_columns(
            TRACKING_OBJECTS, {**lineage, "source_row": o_row, **objects}, len(o_row)
        )
        f_row.clear()
        o_row.clear()
        for column in (*frames.values(), *objects.values()):
            column.clear()
        return fb, ob

    for row, frame in iter_frames(path):
        try:
            if frame.keys() != FRAME_KEYS:
                raise ValueError(f"frame keys {sorted(frame)} != {sorted(FRAME_KEYS)}")
            idx: int = frame["frameIdx"]
            home = frame["homePlayers"]
            away = frame["awayPlayers"]
            ball = frame["ball"]
            f_row.append(row)
            frames["frameIdx"].append(idx)
            frames["wallClock"].append(frame["wallClock"])
            frames["gameClock"].append(frame["gameClock"])
            frames["gameClockStopped"].append(frame["gameClockStopped"])
            frames["period"].append(frame["period"])
            frames["shotClock"].append(frame["shotClock"])
            frames["n_home"].append(len(home))
            frames["n_away"].append(len(away))
            frames["has_ball"].append(bool(ball))
            for side, players in (("home", home), ("away", away)):
                for player in players:
                    if player.keys() != PLAYER_KEYS:
                        raise ValueError(f"player keys {sorted(player)} != {sorted(PLAYER_KEYS)}")
                    x, y, z = player["xyz"]
                    o_row.append(row)
                    objects["frameIdx"].append(idx)
                    objects["side"].append(side)
                    objects["playerId"].append(player["playerId"])
                    objects["jersey"].append(player["jersey"])
                    objects["x"].append(x)
                    objects["y"].append(y)
                    objects["z"].append(z)
                    objects["speed"].append(player["speed"])
                    objects["isDetected"].append(_detected(player["isDetected"]))
                    objects["predError"].append(player["predError"])
            if ball:
                if ball.keys() != BALL_KEYS:
                    raise ValueError(f"ball keys {sorted(ball)} != {sorted(BALL_KEYS)}")
                x, y, z = ball["xyz"]
                o_row.append(row)
                objects["frameIdx"].append(idx)
                objects["side"].append("ball")
                objects["playerId"].append(None)
                objects["jersey"].append(None)
                objects["x"].append(x)
                objects["y"].append(y)
                objects["z"].append(z)
                objects["speed"].append(ball["speed"])
                objects["isDetected"].append(_detected(ball["isDetected"]))
                objects["predError"].append(ball["predError"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"{source_file} line {row}: {exc}") from exc
        if len(f_row) >= batch_frames:
            yield flush()
    if f_row:
        yield flush()


def build_tracking_match(
    entry: FileEntry, raw_root: Path, data_dir: Path, commit: str
) -> TrackingStats:
    """Write ``tracking_frames/<id>.parquet`` and ``tracking_objects/<id>.parquet`` of one match."""
    assert entry.match_id is not None
    started = time.perf_counter()
    metadata = {
        "tracklab.sport": SPORT,
        "tracklab.source_file": entry.path,
        "tracklab.source_sha256": entry.sha256,
        "tracklab.source_commit": commit,
    }
    frames_path = bronze_path(data_dir, SPORT, "tracking_frames", entry.match_id)
    objects_path = bronze_path(data_dir, SPORT, "tracking_objects", entry.match_id)
    with (
        ParquetSink(frames_path, TRACKING_FRAMES, metadata) as frames,
        ParquetSink(objects_path, TRACKING_OBJECTS, metadata) as objects,
    ):
        for frames_batch, objects_batch in frame_batches(
            raw_root / entry.path, entry.match_id, entry.path
        ):
            frames.write(frames_batch)
            objects.write(objects_batch)
    return TrackingStats(
        match_id=entry.match_id,
        frames=frames.rows,
        objects=objects.rows,
        seconds=time.perf_counter() - started,
        mb=(frames.bytes + objects.bytes) / 1e6,
    )


def build_tracking(
    source: Source, raw_root: Path, data_dir: Path, log: Log = print
) -> list[TrackingStats]:
    """Every tracking file the manifest pins, in match id order, one line printed per match."""
    if source.commit is None:
        raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
    entries = sorted(
        (f for f in source.files if f.role == "tracking" and f.match_id is not None),
        key=lambda f: f.match_id or 0,
    )
    log(f"{'match_id':>8} {'frames':>8} {'objects':>9} {'seconds':>8} {'MB':>7}")
    stats: list[TrackingStats] = []
    for entry in entries:
        s = build_tracking_match(entry, raw_root, data_dir, source.commit)
        log(f"{s.match_id:>8} {s.frames:>8} {s.objects:>9} {s.seconds:>8.1f} {s.mb:>7.1f}")
        stats.append(s)
    return stats
