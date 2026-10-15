"""`tracklab publish pose`: the clip of the Body Pose sample and its record (task 55 of
tasks/todo.md, P6).

* **The clip** `web/public/data/pose/1925299_phase406.json`: the 309 frames of the sample
  (`bodypose_sample`), whose sha256 is checked against the manifest before a byte is read. Per
  frame and player: `[idx, x_cm, y_cm, detected, joints | null]`, `joints` being the 29 joints
  in the order of `JOINTS` as `[dx, dy, dz]` in whole centimetres from the player's own
  `(x, y, 0)` (z is already relative to the centroid and is kept as the file has it), then the
  29 `p90_mae_cm` in whole millimetres. A player whose `joints` is null stays null: nothing is
  interpolated, carried over or invented.
  The header carries the pitch (`surface`, from the bronze of the match, named as `dim_match`
  names it) so the viewer draws the replay's markings without a size typed into the web.
* **The record** `pipeline/reports/pose_clip.json`: the bytes and sha256 of the clip, the
  coverage of the sample read from the file, and what the code measured (distance of `midHip`
  to the body origin, quantisation error, alignment with the 10 fps tracking). Every number
  the page or the plan quotes about the clip comes from here.
* **`--check`** regenerates both and compares bytes when the sample is under the data root
  (`FULL 1/1`); without it (CI runs on fixtures, which carry no `raw/`) it verifies the clip as
  versioned (schema, size, sha256 against the record, source sha256 against the manifest) and
  says `PARTIAL 0/1`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from tracklab.ingest.manifest import FileEntry, load_manifest
from tracklab.ingest.verify import sha256_file
from tracklab.pose import jsonl
from tracklab.pose.jsonl import PoseFrame

SCHEMA_VERSION = 1
MATCH_ID = 1925299
SOURCE_ID = "opendata-football"
SAMPLE_PATH = "data/bodypose/sample_1925299_phase406.jsonl.gz"
SAMPLE_ROLE = "bodypose_sample"
CLIP_FILE = "pose/1925299_phase406.json"
RECORD_FILE = "pose_clip.json"
FPS = 25
TRACKING_FRAME_FACTOR = 2.5
ALIGN_FRAME = 124490  # pose frame of the alignment test; tracking frame 124490 / 2.5 = 49796
MAX_POSE_CLIP_BYTES = 3_000_000  # hypothesis of decision 5, measured and printed, not enforced

# The three limits of SkillCorner, copied from the README of the HF dataset (hard-wrapped lines
# joined by a space), each with its line: they are code (rule of P6), not a footnote.
LIMITS: tuple[dict[str, str], ...] = (
    {
        "id": "detected_only",
        "readme": "readme.md:139",
        "text": "Body Pose is only provided for detected players.",
    },
    {
        "id": "z_relative",
        "readme": "readme.md:140-142",
        "text": "Position on the z-axis is accurate relatively to the player's centroid, but "
        "not necessarily in the pitch coordinate system. This will come with future Body Pose "
        "enhancements.",
    },
    {
        "id": "separate_generation",
        "readme": "readme.md:143-145",
        "text": "XY Tracking data and Body Pose are generated separately. This can cause minor "
        "misalignments between the XY attributes (positions, `is_detected` flag) and the Body "
        "Pose joints.",
    },
)


def limit_problems(
    readme_lines: list[str], limits: tuple[dict[str, str], ...] = LIMITS
) -> list[str]:
    """Each limit against the README it quotes: its text is the lines it names (the bullet's
    marker dropped, the wrapped lines joined by a space), and those lines start and end a bullet."""
    problems = []
    for limit in limits:
        found = re.fullmatch(r"readme\.md:(\d+)(?:-(\d+))?", limit["readme"])
        if not found:
            problems.append(f"{limit['id']}: {limit['readme']} is no line range")
            continue
        first = int(found.group(1))
        last = int(found.group(2) or first)
        text = " ".join(line.strip().removeprefix("* ") for line in readme_lines[first - 1 : last])
        if text != limit["text"]:
            problems.append(f"{limit['id']}: lines {first}-{last} say {text!r}")
        if not readme_lines[first - 1].startswith("* "):
            problems.append(f"{limit['id']}: line {first} does not start a bullet")
        if last < len(readme_lines) and readme_lines[last].startswith("  "):
            problems.append(f"{limit['id']}: the bullet goes on past line {last}")
    return problems


# Bones as joint-name pairs; the clip carries them as index pairs into its own `joints`.
BONE_NAMES: tuple[tuple[str, str], ...] = (
    ("nose", "neck"), ("nose", "lEye"), ("nose", "rEye"), ("lEye", "lEar"), ("rEye", "rEar"),
    ("neck", "lShoulder"), ("neck", "rShoulder"), ("neck", "midHip"),
    ("lShoulder", "lElbow"), ("lElbow", "lWrist"), ("lWrist", "lThumb"), ("lWrist", "lPinky"),
    ("rShoulder", "rElbow"), ("rElbow", "rWrist"), ("rWrist", "rThumb"), ("rWrist", "rPinky"),
    ("midHip", "lHip"), ("midHip", "rHip"),
    ("lHip", "lKnee"), ("lKnee", "lAnkle"), ("rHip", "rKnee"), ("rKnee", "rAnkle"),
    ("lAnkle", "lHeel"), ("lAnkle", "lBigToe"), ("lBigToe", "lSmallToe"), ("lSmallToe", "lHeel"),
    ("rAnkle", "rHeel"), ("rAnkle", "rBigToe"), ("rBigToe", "rSmallToe"), ("rSmallToe", "rHeel"),
)  # fmt: skip


class PosePublishError(RuntimeError):
    """The sample or the warehouse does not support what the clip would say."""


def cm(metres: Any) -> Any:
    """Metres to whole centimetres, half up (floor(v + 1/2)): an error of at most 0.5 cm."""
    return np.floor(np.asarray(metres, dtype=np.float64) * 100.0 + 0.5).astype(np.int64)


def mm(centimetres: Any) -> Any:
    return np.floor(np.asarray(centimetres, dtype=np.float64) * 10.0 + 0.5).astype(np.int64)


def _write_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sample_entry(manifest_path: Path) -> FileEntry:
    manifest = load_manifest(manifest_path)
    for entry in manifest.source(SOURCE_ID).files:
        if entry.role == SAMPLE_ROLE and entry.path == SAMPLE_PATH:
            return entry
    raise PosePublishError(f"{SAMPLE_PATH} (role {SAMPLE_ROLE}) is not in {manifest_path}")


def sample_path(data_dir: Path) -> Path:
    return data_dir / "raw" / SOURCE_ID / SAMPLE_PATH


def _bronze(data_dir: Path, table: str, match_id: int = MATCH_ID) -> str:
    return (data_dir / "bronze" / "football" / table / f"{match_id}.parquet").as_posix()


def read_sample(data_dir: Path, manifest_path: Path) -> tuple[list[PoseFrame], FileEntry]:
    """The frames of the sample, after its sha256 and size have been checked against the
    manifest: nothing is read from a file the manifest does not vouch for."""
    entry = sample_entry(manifest_path)
    path = sample_path(data_dir)
    if not path.is_file():
        raise PosePublishError(f"{path} is not at hand")
    if path.stat().st_size != entry.bytes or sha256_file(path) != entry.sha256:
        raise PosePublishError(f"{path} is not the file the manifest pins ({entry.sha256})")
    with jsonl.open_lines(path) as lines:
        frames = list(jsonl.iter_frames(lines))
    if not frames:
        raise PosePublishError(f"{path} holds no frames")
    return frames, entry


def _players_block(
    con: duckdb.DuckDBPyConnection, data_dir: Path, ids: set[int], match_id: int = MATCH_ID
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = con.execute(
        "select id, team_id, number from read_parquet(?) order by team_id, number, id",
        [_bronze(data_dir, "match_players", match_id)],
    ).fetchall()
    known = {int(r[0]) for r in rows}
    missing = sorted(ids - known)
    if missing:
        raise PosePublishError(f"player ids not in match_players: {missing}")
    players = [
        {"player_id": int(r[0]), "team_id": int(r[1]), "number": int(r[2])}
        for r in rows
        if int(r[0]) in ids
    ]
    match = con.execute(
        "select home_team_id, away_team_id from read_parquet(?)",
        [_bronze(data_dir, "match", match_id)],
    ).fetchone()
    assert match is not None
    teams = [{"team_id": int(match[0]), "side": "home"}, {"team_id": int(match[1]), "side": "away"}]
    if {p["team_id"] for p in players} - {t["team_id"] for t in teams}:
        raise PosePublishError("a player's team is neither the home nor the away team")
    return players, teams


def _surface_block(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int = MATCH_ID
) -> dict[str, Any]:
    """The pitch of the match as `dim_match` names it, `provider_<length>x<width>` (task 56:
    the viewer draws the replay's markings with it)."""
    row = con.execute(
        "select pitch_length, pitch_width from read_parquet(?)",
        [_bronze(data_dir, "match", match_id)],
    ).fetchone()
    assert row is not None
    length, width = int(row[0]), int(row[1])
    return {"spec": f"provider_{length}x{width}", "length_m": length, "width_m": width}


def coverage(frames: list[PoseFrame]) -> dict[str, Any]:
    """What the sample holds, read from the frames as parsed (full precision, not the clip)."""
    per_frame = [sum(p.xyz is not None for p in f.players) for f in frames]
    player_frames = sum(len(f.players) for f in frames)
    with_joints = sum(per_frame)
    mae = np.concatenate([p.mae_cm for f in frames for p in f.players if p.mae_cm is not None])
    return {
        "frames": len(frames),
        "player_frames": player_frames,
        "with_joints": with_joints,
        "with_joints_share": round(with_joints / player_frames, 4),
        "joint_observations": int(mae.size),
        "skeletons_per_frame": {"min": min(per_frame), "max": max(per_frame)},
        "p90_mae_cm": {
            "min": float(mae.min()),
            "median": float(np.median(mae)),
            "p90": float(np.percentile(mae, 90)),
            "max": float(mae.max()),
        },
    }


def _player_index(players: list[dict[str, Any]]) -> dict[int, int]:
    return {p["player_id"]: i for i, p in enumerate(players)}


def build_clip(
    frames: list[PoseFrame],
    entry: FileEntry,
    players: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    surface: dict[str, Any],
    match_id: int = MATCH_ID,
) -> dict[str, Any]:
    order = jsonl.JOINTS
    index = _player_index(players)
    first = frames[0].frame
    out_frames = []
    for f in frames:
        by_id = {p.player_id: p for p in f.players}
        if len(by_id) != len(f.players) or set(by_id) - index.keys():
            raise PosePublishError(f"frame {f.frame}: repeated or unknown player")
        entries = []
        for pid in sorted(by_id, key=index.__getitem__):
            p = by_id[pid]
            joints = None
            if p.xyz is not None and p.mae_cm is not None:
                rel = p.xyz - np.array([p.x, p.y, 0.0])  # the body frame: origin (x, y, 0)
                joints = [cm(rel).tolist(), mm(p.mae_cm).tolist()]
            entries.append(
                [index[pid], int(cm(p.x)), int(cm(p.y)), 1 if p.is_detected else 0, joints]
            )
        assert f.ball is not None, f"frame {f.frame} of the sample has no ball"
        bx, by, _bz, detected = f.ball
        out_frames.append(
            {
                "f": f.frame,
                "t": (f.frame - first) * 1000 // FPS,
                "ball": [int(cm(bx)), int(cm(by)), 1 if detected else 0],
                "p": entries,
            }
        )
    position = {name: i for i, name in enumerate(order)}
    return {
        "schema_version": SCHEMA_VERSION,
        "match_id": match_id,
        "period": frames[0].period,
        "frame_lo": first,
        "frame_hi": frames[-1].frame,
        "fps": FPS,
        "tracking_frame_factor": TRACKING_FRAME_FACTOR,
        "surface": surface,
        "source": {"file": entry.path, "bytes": entry.bytes, "sha256": entry.sha256},
        "units": {"xy": "cm", "joints": "cm, from the player's own (x, y, 0)", "mae": "mm"},
        "joints": list(order),
        "bones": [[position[a], position[b]] for a, b in BONE_NAMES],
        "limits": [dict(item) for item in LIMITS],
        "teams": teams,
        "players": players,
        "coverage": coverage(frames),
        "frames": out_frames,
    }


# --- what the code measures about the clip -------------------------------------------------


def midhip_distance_cm(clip: dict[str, Any]) -> dict[str, Any]:
    """Horizontal distance (cm) from `midHip` to the body origin, over every skeleton."""
    mid = clip["joints"].index("midHip")
    d = [
        float(np.hypot(p[4][0][mid][0], p[4][0][mid][1]))
        for f in clip["frames"]
        for p in f["p"]
        if p[4] is not None
    ]
    return {
        "skeletons": len(d),
        "median": round(float(np.median(d)), 2),
        "p99": round(float(np.percentile(d, 99)), 2),
        "max": round(max(d), 2),
    }


def quantisation_cm(frames: list[PoseFrame], clip: dict[str, Any]) -> dict[str, float]:
    """The largest per-coordinate gap between the clip's integers and the exact values: joint
    offsets (cm), player (x, y) (cm) and the mae (published in mm, compared in cm)."""
    offsets = positions = mae = 0.0
    index = _player_index(clip["players"])
    by_frame = {f["f"]: f for f in clip["frames"]}
    for f in frames:
        published = by_frame[f.frame]["p"]
        ordered = sorted(f.players, key=lambda q: index[q.player_id])
        for entry, p in zip(published, ordered, strict=True):
            positions = max(positions, abs(entry[1] - p.x * 100), abs(entry[2] - p.y * 100))
            if p.xyz is None or p.mae_cm is None:
                continue
            exact = (p.xyz - np.array([p.x, p.y, 0.0])) * 100
            offsets = max(offsets, float(np.abs(np.array(entry[4][0]) - exact).max()))
            mae = max(mae, float(np.abs(np.array(entry[4][1]) / 10 - p.mae_cm).max()))
    return {
        "joint_offset_max_abs_cm": round(offsets, 4),
        "player_xy_max_abs_cm": round(positions, 4),
        "mae_max_abs_cm": round(mae, 4),
    }


def alignment(
    con: duckdb.DuckDBPyConnection, data_dir: Path, clip: dict[str, Any]
) -> dict[str, Any]:
    """Distance (m) between the clip's (x, y) and the tracking's, by `frame` (never by
    timestamp): the frame of the plan's test, and every pose frame that is a multiple of 5
    (they land on an even tracking frame, README `Frame rate`)."""
    ids = [p["player_id"] for p in clip["players"]]
    by_frame = {f["f"]: f for f in clip["frames"]}

    def gap(pose_frame: int) -> list[tuple[float, bool]]:
        tracking = pose_frame / TRACKING_FRAME_FACTOR
        rows = con.execute(
            "select player_id, x, y from read_parquet(?) where frame = ?",
            [_bronze(data_dir, "tracking_objects"), int(tracking)],
        ).fetchall()
        pose = {ids[e[0]]: e for e in by_frame[pose_frame]["p"]}
        missing = [r[0] for r in rows if r[0] not in pose]
        if missing:
            raise PosePublishError(f"tracking players {missing} are not in pose frame {pose_frame}")
        return [
            (
                float(np.hypot(pose[r[0]][1] / 100 - r[1], pose[r[0]][2] / 100 - r[2])),
                bool(pose[r[0]][3]),
            )
            for r in rows
        ]

    one = [d for d, _ in gap(ALIGN_FRAME)]
    aligned = [f for f in by_frame if f % 5 == 0]
    every = [pair for f in aligned for pair in gap(f)]
    distances = [d for d, _ in every]
    detected = [d for d, seen in every if seen]
    return {
        "pose_frame": ALIGN_FRAME,
        "tracking_frame": int(ALIGN_FRAME / TRACKING_FRAME_FACTOR),
        "players": len(one),
        "max_distance_m": round(max(one), 3),
        "median_distance_m": round(float(np.median(one)), 3),
        "aligned_frames": {
            "frames": len(aligned),
            "pairs": len(every),
            "max_distance_m": round(max(distances), 3),
            "median_distance_m": round(float(np.median(distances)), 3),
            "pairs_over_1_5_m": sum(d > 1.5 for d in distances),
            "detected_in_pose": {
                "pairs": len(detected),
                "max_distance_m": round(max(detected), 3),
                "pairs_over_1_5_m": sum(d > 1.5 for d in detected),
            },
        },
    }


def build(data_dir: Path, manifest_path: Path) -> tuple[str, dict[str, Any]]:
    """The clip's text and the record, from the sample and the bronze of the match."""
    frames, entry = read_sample(data_dir, manifest_path)
    con = duckdb.connect()
    ids = {p.player_id for f in frames for p in f.players}
    players, teams = _players_block(con, data_dir, ids)
    clip = build_clip(frames, entry, players, teams, _surface_block(con, data_dir))
    text = _write_text(clip)
    data = text.encode("utf-8")
    slots = Counter(sum(p[4] is not None for p in f["p"]) for f in clip["frames"])
    record = {
        "schema_version": SCHEMA_VERSION,
        "clip": {
            "file": f"web/public/data/{CLIP_FILE}",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "max_bytes_hypothesis": MAX_POSE_CLIP_BYTES,
            "within_hypothesis": len(data) <= MAX_POSE_CLIP_BYTES,
        },
        "source": clip["source"],
        "coverage": clip["coverage"],
        "midhip_horizontal_cm": midhip_distance_cm(clip),
        "quantisation": quantisation_cm(frames, clip),
        "alignment": alignment(con, data_dir, clip),
        "skeletons_per_frame_histogram": {str(k): v for k, v in sorted(slots.items())},
    }
    return text, record


# --- writing and checking ------------------------------------------------------------------


def validate_clip(clip: dict[str, Any], schema_path: Path) -> list[str]:
    from jsonschema import Draft202012Validator  # type: ignore[import-untyped]  # dev group

    validator = Draft202012Validator(_load(schema_path))
    return sorted(
        f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator.iter_errors(clip)
    )


def _manifest_source(manifest_path: Path) -> dict[str, Any]:
    entry = sample_entry(manifest_path)
    return {"file": entry.path, "bytes": entry.bytes, "sha256": entry.sha256}


SUMMARY_FILE = "pose.json"
SUMMARY_SCHEMA = "summary.schema.json"


def _validate(document: Any, schema_path: Path) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(_load(schema_path))
    return sorted(
        f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
        for e in validator.iter_errors(document)
    )


def _versioned_problems(
    out_dir: Path,
    reports_dir: Path,
    schema_path: Path,
    manifest_path: Path,
    named: set[str],
) -> list[str]:
    """The sample's clip as versioned (schema, size, sha256 against the record, source against
    the manifest); `named` are the other clips of `pose/` the summary names."""
    clip_path, record_path = out_dir / CLIP_FILE, reports_dir / RECORD_FILE
    for path in (clip_path, record_path):
        if not path.is_file():
            return [f"{path.name} is missing"]
    data, record = clip_path.read_bytes(), _load(record_path)
    clip = json.loads(data)
    problems = [f"schema: {e}" for e in validate_clip(clip, schema_path)[:5]]
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != record["clip"]["bytes"] or digest != record["clip"]["sha256"]:
        problems.append(f"{clip_path.name} is not the clip {RECORD_FILE} describes")
    if clip["coverage"] != record["coverage"] or clip["source"] != record["source"]:
        problems.append(f"the clip and {RECORD_FILE} disagree on coverage or source")
    if clip["source"] != _manifest_source(manifest_path):
        problems.append("the clip's source is not the manifest's entry for the sample")
    here = {p.name for p in clip_path.parent.glob("*.json")} - {clip_path.name}
    if here != {Path(n).name for n in named}:
        problems.append(
            f"{Path(CLIP_FILE).parent}/ holds {sorted(here)}, the summary names {sorted(named)}"
        )
    return problems


def _clip_problems(out_dir: Path, schema_path: Path, record: dict[str, Any], cap: int) -> list[str]:
    """One clip of a whole match as versioned: present, the bytes and sha256 the summary says,
    valid, and under the cap of the sample's clip (task 55's measured bytes)."""
    path = out_dir / record["file"]
    if not path.is_file():
        return [f"{record['file']} is missing"]
    data = path.read_bytes()
    schema = [f"{record['file']} schema: {e}" for e in validate_clip(json.loads(data), schema_path)]
    problems = schema[:5]
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        problems.append(f"{record['file']} is not the clip {SUMMARY_FILE} describes")
    if len(data) > cap:
        problems.append(f"{record['file']} has {len(data)} bytes, over the cap of {cap}")
    return problems


def _site(data_dir: Path, manifest_path: Path, reports_dir: Path) -> tuple[dict[str, str], str]:
    """What the publication writes besides the sample's clip: the clips of the whole matches
    (relative file to text) and the text of pose.json. Reads a match's bronze past the guard."""
    from tracklab.publish import pose_hook, pose_summary

    reports = pose_summary.load_reports(reports_dir)
    status, dead_at = pose_summary.status_of(reports)
    cap = int(reports["clip"]["clip"]["bytes"])
    clips = pose_hook.build_clips(data_dir, manifest_path, reports, status, dead_at)
    texts = {file: _write_text(clip) for file, clip in clips.items()}
    for file, text in texts.items():
        if len(text.encode("utf-8")) > cap:
            raise PosePublishError(f"{file} is over the cap of {cap} bytes (task 55's clip)")
    records = [pose_hook.record_of(f, texts[f], clips[f]) for f in texts]
    summary = pose_summary.build_summary(reports, records)
    return texts, _write_text(summary) + "\n"


def _whole(data_dir: Path, match_id: int) -> bool:
    from tracklab.pose.data import CountingHandle

    handle = CountingHandle(data_dir, match_id)
    return handle.exists() and handle.is_whole()


def _expected_matches(reports_dir: Path) -> list[int]:
    from tracklab.publish import pose_hook, pose_summary

    reports = pose_summary.load_reports(reports_dir)
    status, dead_at = pose_summary.status_of(reports)
    return pose_hook.matches_to_clip(reports, status, dead_at)


def _summary_problems(out_dir: Path, reports_dir: Path, schema_path: Path) -> tuple[list[str], int]:
    """pose.json as versioned: valid, built from the reports it names (nothing typed), its clips
    in place. Returns the problems and the number of clips it names."""
    from tracklab.publish import pose_summary

    path = out_dir / SUMMARY_FILE
    if not path.is_file():
        return [f"{SUMMARY_FILE} is missing"], 0
    summary = json.loads(path.read_text(encoding="utf-8"))
    problems = [
        f"{SUMMARY_FILE} schema: {e}"
        for e in _validate(summary, schema_path.parent / SUMMARY_SCHEMA)[:5]
    ]
    reports = pose_summary.load_reports(reports_dir)
    rebuilt = pose_summary.build_summary(reports, summary["clips"])
    if _write_text(rebuilt) + "\n" != path.read_text(encoding="utf-8"):
        problems.append(f"{SUMMARY_FILE} is not what the reports in {reports_dir.name}/ give")
    cap = int(reports["clip"]["clip"]["bytes"])
    for record in summary["clips"]:
        problems += _clip_problems(out_dir, schema_path, record, cap)
    return problems, len(summary["clips"])


def _check(
    data_dir: Path,
    reports_dir: Path,
    out_dir: Path,
    manifest_path: Path,
    schema_path: Path,
) -> tuple[list[str], int, int]:
    """(problems, units recomputed, units named): the versioned files verified, and every unit
    whose bronze (or sample) is whole recomputed and compared byte for byte."""
    clip_path, record_path = out_dir / CLIP_FILE, reports_dir / RECORD_FILE
    summary_path = out_dir / SUMMARY_FILE
    problems, named = _summary_problems(out_dir, reports_dir, schema_path)
    names = (
        {r["file"] for r in json.loads(summary_path.read_text(encoding="utf-8"))["clips"]}
        if summary_path.is_file()
        else set()
    )
    problems += _versioned_problems(out_dir, reports_dir, schema_path, manifest_path, names)
    done = 0
    if sample_path(data_dir).is_file():
        text, record = build(data_dir, manifest_path)
        if not clip_path.is_file() or clip_path.read_bytes() != text.encode("utf-8"):
            problems.append(f"{clip_path.name} differs from what the code writes")
        if not record_path.is_file() or record_path.read_text(encoding="utf-8") != render(record):
            problems.append(f"{RECORD_FILE} differs from what the code writes")
        done += 1
    matches = _expected_matches(reports_dir)
    if all(_whole(data_dir, m) for m in matches):
        texts, summary_text = _site(data_dir, manifest_path, reports_dir)
        for file, text in texts.items():
            if not (out_dir / file).is_file() or (out_dir / file).read_bytes() != text.encode():
                problems.append(f"{file} differs from what the code writes")
        if not summary_path.is_file() or summary_path.read_text(encoding="utf-8") != summary_text:
            problems.append(f"{SUMMARY_FILE} differs from what the code writes")
        done += len(matches)
    return problems, done, 1 + named


def run_publish_pose(
    data_dir: Path,
    reports_dir: Path,
    out_dir: Path,
    manifest_path: Path,
    schema_path: Path,
    *,
    check: bool = False,
) -> int:
    from tracklab.runs.data import HeldOutLocked

    clip_path, record_path = out_dir / CLIP_FILE, reports_dir / RECORD_FILE
    if check:
        try:
            problems, done, total = _check(
                data_dir, reports_dir, out_dir, manifest_path, schema_path
            )
        except HeldOutLocked as error:
            print(f"publish pose --check: the confirmation match stays closed: {error}")
            return 1
        except (OSError, KeyError, PosePublishError) as error:
            print(f"publish pose --check: {error!r}")
            return 1
        status = (
            f"FULL {done}/{total} recomputed and equal"
            if done == total
            else f"PARTIAL {done}/{total}: schema, size, sha256 and the reports of the "
            "versioned files verified"
        )
        if problems:
            print(f"publish pose --check: {status}; " + "; ".join(problems))
            return 1
        print(f"publish pose --check: {SUMMARY_FILE} and its {total - 1} clips match ({status})")
        return 0
    try:
        text, record = build(data_dir, manifest_path)
        problems = validate_clip(json.loads(text), schema_path)
        texts, summary_text = _site(data_dir, manifest_path, reports_dir)
        problems += _validate(json.loads(summary_text), schema_path.parent / SUMMARY_SCHEMA)
        for clip_text in texts.values():
            problems += validate_clip(json.loads(clip_text), schema_path)
    except (OSError, KeyError, PosePublishError, HeldOutLocked) as error:
        print(f"publish pose: {error!r}")
        return 1
    if problems:
        print("publish pose: does not validate: " + "; ".join(problems[:5]))
        return 1
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in clip_path.parent.glob("*.json"):
        if stale.name != clip_path.name:
            stale.unlink()
    clip_path.write_bytes(text.encode("utf-8"))
    for file, clip_text in texts.items():
        (out_dir / file).write_bytes(clip_text.encode("utf-8"))
    (out_dir / SUMMARY_FILE).write_bytes(summary_text.encode("utf-8"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    record_path.write_text(render(record), encoding="utf-8", newline="\n")
    c = record["clip"]
    sizes = ", ".join(f"{f} {len(t.encode())} bytes" for f, t in texts.items())
    print(
        f"publish pose: {clip_path} ({c['bytes']} bytes, hypothesis {MAX_POSE_CLIP_BYTES}: "
        f"{'within' if c['within_hypothesis'] else 'OVER'}); {sizes}; {SUMMARY_FILE} "
        f"{len(summary_text.encode())} bytes; midHip max "
        f"{record['midhip_horizontal_cm']['max']} cm; alignment max "
        f"{record['alignment']['max_distance_m']} m at frame {ALIGN_FRAME}"
    )
    return 0
