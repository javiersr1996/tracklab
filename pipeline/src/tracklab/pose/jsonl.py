"""A frame iterator over Body Pose JSON lines (task 55 of tasks/todo.md).

The file is read one line at a time and never held whole: the sample is a gzip, the matches
(task 58) are the single member of a zip, and `open_lines` hands back the same text stream for
both. Joints are mapped **by name** through `JOINTS`: the key order of the file is not the
README's and nothing here relies on it. A player whose joint names are not exactly the 29 of
`JOINTS` is refused (`PoseFormatError`), never padded or truncated.
"""

from __future__ import annotations

import gzip
import io
import json
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import numpy as np
from numpy.typing import NDArray

# The README's order (`readme.md:87-90`, "The 29 joints"); the files use another one.
JOINTS: tuple[str, ...] = (
    "nose", "neck", "lEye", "rEye", "lEar", "rEar", "lShoulder", "rShoulder",
    "lElbow", "rElbow", "lWrist", "rWrist", "lThumb", "rThumb", "lPinky", "rPinky",
    "midHip", "lHip", "rHip", "lKnee", "rKnee", "lAnkle", "rAnkle", "lHeel",
    "rHeel", "lBigToe", "rBigToe", "lSmallToe", "rSmallToe",
)  # fmt: skip


class PoseFormatError(ValueError):
    """A line that is not the Body Pose format the code was written against."""


@dataclass(frozen=True)
class PosePlayer:
    """One player of one frame. `xyz` (29, 3) metres and `mae_cm` (29,) follow `JOINTS`;
    both are None when the file says `joints: null` (no pose, never an invented one)."""

    player_id: int
    x: float
    y: float
    is_detected: bool
    xyz: NDArray[np.float64] | None
    mae_cm: NDArray[np.float64] | None


@dataclass(frozen=True)
class PoseFrame:
    """One line. The whole match (task 58) opens with frames outside every period: `period`,
    `timestamp` and `ball` are None there, as are `possession_group` and `possession_player_id`
    when nobody has the ball, and `players` is empty. The sample has none of them. The ball keeps
    its position with `is_detected` null in a fifth of the match's frames (measured by task 58)."""

    frame: int
    period: int | None
    ball: tuple[float, float, float, bool | None] | None
    players: tuple[PosePlayer, ...]
    timestamp: str | None = None
    possession_group: str | None = None
    possession_player_id: int | None = None


def _joints(
    raw: dict[str, dict[str, object]], order: tuple[str, ...]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if set(raw) != set(order) or len(raw) != len(order):
        extra, missing = sorted(set(raw) - set(order)), sorted(set(order) - set(raw))
        raise PoseFormatError(f"joint names differ from JOINTS: extra {extra}, missing {missing}")
    xyz = np.array([raw[name]["xyz"] for name in order], dtype=np.float64)
    mae = np.array([raw[name]["p90_mae_cm"] for name in order], dtype=np.float64)
    if xyz.shape != (len(order), 3):
        raise PoseFormatError(f"a joint's xyz is not three numbers: shape {xyz.shape}")
    return xyz, mae


def parse_frame(line: str, order: tuple[str, ...] | None = None) -> PoseFrame:
    """One JSON line as a `PoseFrame`. `order` defaults to `JOINTS` (read at call time)."""
    order = JOINTS if order is None else order
    record = json.loads(line)
    raw_ball = record["ball_data"]
    players = []
    for p in record["player_data"]:
        raw = p["joints"]
        xyz, mae = (None, None) if raw is None else _joints(raw, order)
        players.append(
            PosePlayer(
                int(p["player_id"]), float(p["x"]), float(p["y"]), bool(p["is_detected"]), xyz, mae
            )
        )
    position = (raw_ball["x"], raw_ball["y"], raw_ball["z"])
    detected = raw_ball["is_detected"]
    if all(v is None for v in position):
        ball = None
    elif any(v is None for v in position):
        raise PoseFormatError(
            f"ball position is partly null in frame {record['frame']}: {raw_ball}"
        )
    else:
        ball = (
            float(position[0]),
            float(position[1]),
            float(position[2]),
            None if detected is None else bool(detected),
        )
    period = record["period"]
    owner = record["possession"]["player_id"]
    return PoseFrame(
        int(record["frame"]),
        None if period is None else int(period),
        ball,
        tuple(players),
        record["timestamp"],
        record["possession"]["group"],
        None if owner is None else int(owner),
    )


def iter_frames(lines: Iterable[str]) -> Iterator[PoseFrame]:
    """Frames from an iterable of lines, one at a time; blank lines are skipped."""
    for line in lines:
        if line.strip():
            yield parse_frame(line)


@contextmanager
def open_lines(path: Path, member: str | None = None) -> Iterator[TextIO]:
    """A text stream over a `.jsonl.gz`, or over the one `.jsonl` member of a `.zip`
    (`member` None: the zip must hold exactly one). Nothing is inflated to disk."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            # The HuggingFace zips carry a macOS `__MACOSX/._<name>.jsonl` resource fork beside
            # the data: it is not JSON and it is not the member.
            names = [
                n
                for n in archive.namelist()
                if n.endswith(".jsonl") and not n.startswith("__MACOSX/")
            ]
            chosen = member if member is not None else (names[0] if len(names) == 1 else None)
            if chosen is None:
                raise PoseFormatError(f"{path.name} does not hold exactly one .jsonl: {names}")
            with archive.open(chosen) as binary:
                yield io.TextIOWrapper(binary, encoding="utf-8")
    else:
        with gzip.open(path, "rt", encoding="utf-8") as text:
            yield text
