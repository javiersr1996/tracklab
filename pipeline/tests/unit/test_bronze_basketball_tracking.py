"""bronze basketball tracking on a synthetic two-match bundle. No real data, no network.

The bundle is built to a known truth: full frames of 5 + 5 + ball, empty frames
(`[]`, `[]`, `{}`), a jump in `frameIdx` that must stay a jump, `shotClock` as null,
int and float, `isDetected` as int for players and float for the ball, a negative
`predError` and a negative ball z. Every row and type of both Parquet tables is then
asserted, and each way the input can break the declared schema is fed to the
builder to prove it fails with the column, key or line in the message and leaves
no Parquet behind.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from tracklab.bronze.basketball.tracking import (
    TRACKING_FRAMES,
    TRACKING_OBJECTS,
    build_tracking_match,
    frame_batches,
)
from tracklab.bronze.common import raw_root_for
from tracklab.cli import main
from tracklab.ingest.fetch import RECEIPT_NAME
from tracklab.ingest.manifest import FileEntry, Manifest, Source, save_manifest

SOURCE_ID = "opendata-basketball"
COMMIT = "4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66"
MATCH_A, MATCH_B = 999001, 999002
HOME_IDS = (101, 102, 103, 104, 105)
AWAY_IDS = (201, 202, 203, 204, 205)


def tracking_path(match_id: int) -> str:
    return f"data/matches/{match_id}/{match_id}_tracking_data.jsonl.gz"


def player(player_id: int, i: int) -> dict[str, Any]:
    return {
        "xyz": [-20.0 + i, 3.5 - i, 0.0],
        "speed": 1.5 * i,
        "predError": -0.158 if i == 1 else 4.5,  # a negative predError exists in the bundle
        "jersey": str(10 + i),
        "isDetected": i % 2,  # players: int 0/1
        "playerId": player_id,
    }


def full_frame(idx: int, shot_clock: float | int | None, ball_detected: float) -> dict[str, Any]:
    return {
        "frameIdx": idx,
        "wallClock": idx * 40,
        "gameClock": 600.0 - idx * 0.04,
        "gameClockStopped": False,
        "period": 1,
        "homePlayers": [player(pid, i) for i, pid in enumerate(HOME_IDS)],
        "awayPlayers": [player(pid, i) for i, pid in enumerate(AWAY_IDS)],
        "ball": {
            "xyz": [1.0, -2.0, -1.5],
            "speed": 7.25,
            "isDetected": ball_detected,
            "predError": 0.5,
        },
        "shotClock": shot_clock,
    }


def empty_frame(idx: int) -> dict[str, Any]:
    return {
        "frameIdx": idx,
        "wallClock": idx * 40,
        "gameClock": 600.0,
        "gameClockStopped": True,
        "period": 1,
        "homePlayers": [],
        "awayPlayers": [],
        "ball": {},
        "shotClock": None,
    }


# Line 3 is frame 600: a jump of 598 frames, like a break. Bronze must keep it a jump.
FRAMES_A = [
    empty_frame(0),
    full_frame(1, shot_clock=24, ball_detected=1.0),  # int shotClock, ball detected as float
    empty_frame(2),
    full_frame(600, shot_clock=13.7, ball_detected=0.0),
    empty_frame(601),
]
FRAMES_B = [full_frame(0, shot_clock=None, ball_detected=1.0), empty_frame(1)]


def gz_bytes(frames: list[dict[str, Any]]) -> bytes:
    text = "".join(json.dumps(f) + "\n" for f in frames)
    return gzip.compress(text.encode("utf-8"), mtime=0)  # deterministic bytes, stable sha256


def write_gz(path: Path, frames: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gz_bytes(frames))


def entry_for(match_id: int, blob: bytes) -> FileEntry:
    return FileEntry(
        path=tracking_path(match_id),
        bytes=len(blob),
        sha256=hashlib.sha256(blob).hexdigest(),
        lfs=True,
        role="tracking",
        match_id=match_id,
    )


def frozen_source(files: list[FileEntry]) -> Source:
    repo = "SkillCorner/opendata-basketball"
    return Source(
        source_id=SOURCE_ID,
        sport="basketball",
        kind="github",
        repo=repo,
        ref="main",
        commit=COMMIT,
        license="MIT",
        raw_url=f"https://raw.githubusercontent.com/{repo}/{{commit}}/",
        lfs_url=f"https://media.githubusercontent.com/media/{repo}/{{commit}}/",
        files=files,
    )


def write_receipt(data_dir: Path, source_path: Path | None, failed: list[str]) -> None:
    receipt_dir = data_dir / "raw" / SOURCE_ID
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "source_id": SOURCE_ID,
        "commit": COMMIT,
        "verified": 2,
        "downloaded": 0,
        "failed": failed,
        "finished_at": "2026-09-21T15:47:27+00:00",
        "source_path": str(source_path) if source_path else None,
    }
    (receipt_dir / RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")


@pytest.fixture
def bundle(tmp_path: Path) -> tuple[Path, Path]:
    """(manifest path, data dir): two matches in an outside clone, verified by receipt."""
    clone = tmp_path / "clone"
    data_dir = tmp_path / "data"
    entries = []
    for match_id, frames in ((MATCH_A, FRAMES_A), (MATCH_B, FRAMES_B)):
        blob = gz_bytes(frames)
        path = clone / tracking_path(match_id)
        path.parent.mkdir(parents=True)
        path.write_bytes(blob)
        entries.append(entry_for(match_id, blob))
    # The manifest also lists a non-tracking file: the builder must not touch it.
    entries.append(FileEntry("data/matches.json", 2, "00" * 32, False, "matches", None))
    manifest_path = tmp_path / "sources.json"
    save_manifest(Manifest(schema_version=1, sources=[frozen_source(entries)]), manifest_path)
    write_receipt(data_dir, clone, failed=[])
    return manifest_path, data_dir


def rows(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


# --- the CLI on the synthetic bundle -------------------------------------------------


def test_cli_builds_both_tables_per_match(
    bundle: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path, data_dir = bundle
    rc = main(
        [
            "bronze",
            "basketball",
            "--tables",
            "tracking",
            "--manifest",
            str(manifest_path),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("bronze basketball tracking: ")
    assert out[1].split() == ["match_id", "frames", "objects", "seconds", "MB"]
    assert out[2].split()[:3] == [str(MATCH_A), "5", "22"]
    assert out[3].split()[:3] == [str(MATCH_B), "2", "11"]
    assert out[4].startswith("total seconds=")

    for table in ("tracking_frames", "tracking_objects"):
        names = sorted(p.name for p in (data_dir / "bronze" / "basketball" / table).iterdir())
        assert names == [f"{MATCH_A}.parquet", f"{MATCH_B}.parquet"], "one file per match"


def test_schema_metadata_and_lineage(bundle: tuple[Path, Path]) -> None:
    manifest_path, data_dir = bundle
    main(
        [
            "bronze",
            "basketball",
            "--tables",
            "tracking",
            "--manifest",
            str(manifest_path),
            "--data-dir",
            str(data_dir),
        ]
    )
    frames_path = data_dir / "bronze" / "basketball" / "tracking_frames" / f"{MATCH_A}.parquet"
    objects_path = data_dir / "bronze" / "basketball" / "tracking_objects" / f"{MATCH_A}.parquet"

    for path, declared in ((frames_path, TRACKING_FRAMES), (objects_path, TRACKING_OBJECTS)):
        written = pq.read_schema(path)
        assert written.equals(declared, check_metadata=False), f"{path.name}: {written}"
        meta = {k.decode(): v.decode() for k, v in written.metadata.items() if k != b"ARROW:schema"}
        assert meta == {
            "tracklab.sport": "basketball",
            "tracklab.source_file": tracking_path(MATCH_A),
            "tracklab.source_sha256": hashlib.sha256(gz_bytes(FRAMES_A)).hexdigest(),
            "tracklab.source_commit": COMMIT,
        }

    for row in rows(frames_path) + rows(objects_path):
        assert (row["sport"], row["match_id"], row["source_file"]) == (
            "basketball",
            MATCH_A,
            tracking_path(MATCH_A),
        )


def test_frames_keep_the_gap_and_the_empty_frames(bundle: tuple[Path, Path]) -> None:
    manifest_path, data_dir = bundle
    main(
        [
            "bronze",
            "basketball",
            "--tables",
            "tracking",
            "--manifest",
            str(manifest_path),
            "--data-dir",
            str(data_dir),
        ]
    )
    frames = rows(data_dir / "bronze" / "basketball" / "tracking_frames" / f"{MATCH_A}.parquet")

    assert [f["frameIdx"] for f in frames] == [0, 1, 2, 600, 601], "no frame invented in the gap"
    assert [f["source_row"] for f in frames] == [0, 1, 2, 3, 4], "line N is not frame N"
    assert [f["wallClock"] for f in frames] == [0, 40, 80, 24000, 24040]
    assert [f["shotClock"] for f in frames] == [None, 24.0, None, 13.7, None]
    assert [f["period"] for f in frames] == [1] * 5
    assert [f["gameClockStopped"] for f in frames] == [True, False, True, False, True]

    empty = frames[0]
    assert (empty["n_home"], empty["n_away"], empty["has_ball"]) == (0, 0, False)
    full = frames[1]
    assert (full["n_home"], full["n_away"], full["has_ball"]) == (5, 5, True)


def test_objects_are_typed_as_delivered(bundle: tuple[Path, Path]) -> None:
    manifest_path, data_dir = bundle
    main(
        [
            "bronze",
            "basketball",
            "--tables",
            "tracking",
            "--manifest",
            str(manifest_path),
            "--data-dir",
            str(data_dir),
        ]
    )
    objects = rows(data_dir / "bronze" / "basketball" / "tracking_objects" / f"{MATCH_A}.parquet")

    assert len(objects) == 22, "11 per full frame, nothing for the 3 empty ones"
    assert sorted({o["frameIdx"] for o in objects}) == [1, 600]
    assert {o["source_row"] for o in objects if o["frameIdx"] == 600} == {3}

    frame1 = [o for o in objects if o["frameIdx"] == 1]
    assert [o["side"] for o in frame1] == ["home"] * 5 + ["away"] * 5 + ["ball"]
    assert [o["playerId"] for o in frame1] == [*HOME_IDS, *AWAY_IDS, None]
    assert [o["jersey"] for o in frame1] == [str(10 + i) for i in range(5)] * 2 + [None]
    assert [o["isDetected"] for o in frame1] == [False, True, False, True, False] * 2 + [True]
    assert all(isinstance(o["isDetected"], bool) for o in frame1)
    assert [o["z"] for o in frame1] == [0.0] * 10 + [-1.5], "z stored as delivered"
    assert [o["predError"] for o in frame1][:2] == [4.5, -0.158], "negative predError kept"
    assert (frame1[0]["x"], frame1[0]["y"]) == (-20.0, 3.5)

    ball600 = next(o for o in objects if o["frameIdx"] == 600 and o["side"] == "ball")
    assert ball600["isDetected"] is False, "ball isDetected 0.0 -> false"


# --- every way the input can break the declared schema ------------------------------


def broken(mutate: Any) -> tuple[dict[str, Any], str]:
    """One full frame with `mutate(frame)` applied, and the source_file it belongs to."""
    frame = full_frame(1, shot_clock=24, ball_detected=1.0)
    mutate(frame)
    return frame, tracking_path(MATCH_A)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda f: f["homePlayers"][0].__setitem__("isDetected", 2), "isDetected=2 is not 0 or 1"),
        (lambda f: f["ball"].__setitem__("isDetected", 0.5), "isDetected=0.5 is not 0 or 1"),
        (lambda f: f["awayPlayers"][2].__setitem__("extra", 1), "player keys"),
        (lambda f: f["ball"].pop("speed"), "ball keys"),
        (lambda f: f.pop("shotClock"), "frame keys"),
        (lambda f: f.__setitem__("period", None), r"column period: 1 null\(s\), declared NOT NULL"),
        (lambda f: f.__setitem__("period", 70000), "column period"),
        (lambda f: f["homePlayers"][1].__setitem__("xyz", [1.0, 2.0]), "line 0"),
        (lambda f: f["homePlayers"][1].__setitem__("jersey", 7), "column jersey"),
    ],
)
def test_schema_violations_fail_with_the_name(tmp_path: Path, mutate: Any, message: str) -> None:
    frame, source_file = broken(mutate)
    path = tmp_path / "broken.jsonl.gz"
    write_gz(path, [frame])
    with pytest.raises(ValueError, match=message):
        list(frame_batches(path, MATCH_A, source_file))


def test_a_failed_match_leaves_no_parquet_behind(tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    data_dir = tmp_path / "data"
    frame, _ = broken(lambda f: f["ball"].__setitem__("isDetected", 3.0))
    frames = [empty_frame(0), frame]
    write_gz(clone / tracking_path(MATCH_A), frames)
    entry = entry_for(MATCH_A, gz_bytes(frames))

    with pytest.raises(ValueError, match="line 1: isDetected=3.0"):
        build_tracking_match(entry, clone, data_dir, COMMIT)

    for table in ("tracking_frames", "tracking_objects"):
        assert list((data_dir / "bronze" / "basketball" / table).iterdir()) == []


# --- raw root and CLI guards -----------------------------------------------------------


def test_raw_root_from_receipt(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with pytest.raises(FileNotFoundError, match="tracklab ingest opendata-basketball"):
        raw_root_for(data_dir, SOURCE_ID)

    write_receipt(data_dir, None, failed=[])
    assert raw_root_for(data_dir, SOURCE_ID) == data_dir / "raw" / SOURCE_ID

    write_receipt(data_dir, tmp_path / "clone", failed=[])
    assert raw_root_for(data_dir, SOURCE_ID) == tmp_path / "clone"

    write_receipt(data_dir, tmp_path / "clone", failed=["data/matches.json"])
    with pytest.raises(RuntimeError, match="1 file\\(s\\) failed verification"):
        raw_root_for(data_dir, SOURCE_ID)


def test_cli_refuses_an_unknown_table_group(bundle: tuple[Path, Path]) -> None:
    manifest_path, data_dir = bundle
    # 'silver' is never registered for any sport: a stand-in for whatever group does
    # not exist yet, so this test survives new groups (events, meta, aggregates)
    # being registered by later tasks.
    with pytest.raises(SystemExit, match="no bronze builder for basketball \\['silver'\\]"):
        main(
            [
                "bronze",
                "basketball",
                "--tables",
                "tracking,silver",
                "--manifest",
                str(manifest_path),
                "--data-dir",
                str(data_dir),
            ]
        )
    assert not (data_dir / "bronze").exists(), "nothing built before the check"
