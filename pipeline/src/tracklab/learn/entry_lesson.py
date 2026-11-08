"""`tracklab learn entry`: at what angle does the ball reach the rim (lesson 8, P9)?

The table is P3's and is already published: `checks.entry_angle` of `web/public/data/quality.json`,
five metrics per basketball match. This module writes only the example, `learn/entry.json`: the
flight of the hook of lesson 1 (`quality.json`'s `hook`, a made shot of its match) from
`startFrame` to the first frame after its highest one at or under the rim, 3.048 m, extended if
needed to the arrival sample the check computes. Every sample is x, y and z in metres at `DIGITS`
decimals, from bronze (feet, to metres; time the frame / 25 s, as silver keeps it); the file also
gives the check's constants and the shot's v_h, D, T, k and two angles computed from the published
samples, and the two angles at full precision.

`v_h_sweep` is how far the gap moves with the way v_h is measured: entry.py's arithmetic rerun
with v_h's window at each of `SWEEP_WINDOWS` samples and the search starting each of
`SWEEP_OFFSETS` frames after `startFrame` (entry.py's own 8 and 2 among them; a run needs the
window and as many samples more as entry.py asks). For the example shot, its gap (required minus
reported, at full precision) at each; for every match of `quality.json`, the lowest and the
highest median gap of a match at each, and the range over all. At entry.py's own window and
offset the median of every match must be `quality.json`'s, or the build stops.

The arithmetic is `entry.py`'s, the script "Reproduce it" shows, which reruns the check from the
public raw files alone. `--check` rebuilds the file from bronze and compares its bytes, and runs
`entry.py` on the raw files of every match of `quality.json`, comparing its five figures with
the published rows: `FULL n/n` when both were done for all n matches, else `PARTIAL k/n` and what
it checked.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from tracklab.bronze.common import raw_root_for
from tracklab.learn import entry as script
from tracklab.quality.entry_angle import _made_shots

SOURCE_ID = "opendata-basketball"
SCRIPT_PATH = Path(script.__file__)
DIGITS = 4
METRICS = {
    "shots": "shots",
    "reported": "angle_reported_median_deg",
    "required": "angle_required_median_deg",
    "gap": "gap_median_deg",
    "reordered_pct": "pairs_reordered_pct",
}
SWEEP_WINDOWS = (8, 12)  # samples v_h is the median over: entry.py's and a wider one
SWEEP_OFFSETS = (0, 1, 2)  # frames after startFrame the search for the flight begins
RUN_EXTRA = script.MIN_CONTIG - script.V_H_FRAMES  # samples a run needs beyond the window


def read_samples(bronze: Path, match: int) -> list[script.Sample]:
    """The ball's samples of one match from bronze, as `entry.load` reads them from the raw file:
    frames with a period and a ball height, in metres, at time frame / 25 s."""
    rows = (
        duckdb.connect()
        .execute(
            "SELECT o.frameIdx, o.x, o.y, o.z FROM read_parquet(?) o JOIN read_parquet(?) f "
            "USING (frameIdx) WHERE o.side = 'ball' AND o.z IS NOT NULL AND f.period IS NOT NULL "
            "ORDER BY o.frameIdx",
            [
                (bronze / "tracking_objects" / f"{match}.parquet").as_posix(),
                (bronze / "tracking_frames" / f"{match}.parquet").as_posix(),
            ],
        )
        .fetchall()
    )
    ft = script.FT
    return [
        (int(f), int(f) * 1000 // script.FPS / 1000, x * ft, y * ft, z * ft) for f, x, y, z in rows
    ]


def _angles(fl: dict[str, float]) -> dict[str, float | int]:
    return {
        "v_h": round(fl["v_h"], DIGITS),
        "d": round(fl["d"], DIGITS),
        "t": round(fl["t"], DIGITS),
        "k": int(fl["k"]),
        "reported": round(fl["reported"], DIGITS),
        "required": round(fl["required"], DIGITS),
    }


def example(bronze: Path, hook: dict[str, Any]) -> dict[str, Any]:
    match = int(hook["match_id"].removeprefix("bb:"))
    start = int(hook["start_frame"])
    samples = read_samples(bronze, match)
    run = script.run_of(samples, start)
    if isinstance(run, str):
        raise ValueError(f"{hook['shot_id']}: the check drops it ({run})")
    full = script.flight(run)
    if isinstance(full, str):
        raise ValueError(f"{hook['shot_id']}: the check drops it ({full})")
    by_frame = {s[0]: s for s in samples}
    last = run[int(full["k"])][0]
    flight: list[script.Sample] = []
    for f in range(start, start + script.SEARCH_OFFSET + script.SEG_LEN):
        if f not in by_frame:
            raise ValueError(f"{hook['shot_id']}: no ball at frame {f}")
        flight.append(by_frame[f])
        apex = max(range(len(flight)), key=lambda i: flight[i][4])
        down = len(flight) - 1 > apex and flight[-1][4] <= script.RIM_HEIGHT < flight[apex][4]
        if down and f >= last:
            break
    rounded: list[script.Sample] = [
        (s[0], s[1], round(s[2], DIGITS), round(s[3], DIGITS), round(s[4], DIGITS)) for s in flight
    ]
    published = script.flight(rounded[script.SEARCH_OFFSET :])
    if isinstance(published, str) or published["k"] != full["k"]:
        raise ValueError(f"{hook['shot_id']}: rounding to {DIGITS} decimals changes the flight")
    return {
        "match_id": hook["match_id"],
        "shot_id": hook["shot_id"],
        "start_frame": start,
        "x": [s[2] for s in rounded],
        "y": [s[3] for s in rounded],
        "z": [s[4] for s in rounded],
        "rim_x": round(script.RIM_X if rounded[script.SEARCH_OFFSET][2] > 0 else -script.RIM_X, 6),
        "published": _angles(published),
        "full_precision": {k: round(full[k], DIGITS) for k in ("reported", "required")},
    }


@contextmanager
def _variant(window: int, offset: int) -> Iterator[None]:
    """entry.py's arithmetic with another v_h window and search offset: its module constants,
    set for the block and put back after, so the public script itself is what runs."""
    saved = script.V_H_FRAMES, script.SEARCH_OFFSET, script.MIN_CONTIG
    script.V_H_FRAMES, script.SEARCH_OFFSET = window, offset
    script.MIN_CONTIG = window + RUN_EXTRA
    try:
        yield
    finally:
        script.V_H_FRAMES, script.SEARCH_OFFSET, script.MIN_CONTIG = saved


def gaps(samples: list[script.Sample], starts: list[int]) -> list[float]:
    """Required minus reported (degrees) of every shot the check keeps, as `entry.summary`."""
    out = []
    for start in starts:
        run = script.run_of(samples, start)
        got = script.flight(run) if not isinstance(run, str) else run
        if not isinstance(got, str):
            out.append(got["required"] - got["reported"])
    return out


def v_h_sweep(data_dir: Path, quality: Path, hook: dict[str, Any]) -> dict[str, Any]:
    bronze = data_dir / "bronze" / "basketball"
    rows = published_rows(quality)
    shots = _made_shots(data_dir)
    example: list[list[float]] = []
    matches: list[list[float]] = []
    medians: dict[tuple[int, int], list[float]] = {}
    for match_id in sorted(rows):
        native = int(match_id.removeprefix("bb:"))
        if not (bronze / "tracking_objects" / f"{native}.parquet").is_file():
            raise ValueError(f"no bronze ball for {match_id}")
        samples = read_samples(bronze, native)
        for window in SWEEP_WINDOWS:
            for offset in SWEEP_OFFSETS:
                with _variant(window, offset):
                    median = round(statistics.median(gaps(samples, shots[native])), DIGITS)
                    if match_id == hook["match_id"]:
                        one = gaps(samples, [int(hook["start_frame"])])
                        if not one:
                            raise ValueError(f"the example is dropped at {window}, {offset}")
                        example.append([window, offset, round(one[0], DIGITS)])
                own = (window, offset) == (script.V_H_FRAMES, script.SEARCH_OFFSET)
                if own and median != rows[match_id]["gap"]:
                    raise ValueError(f"{match_id}: median gap {median}, quality.json's differs")
                medians.setdefault((window, offset), []).append(median)
    for (window, offset), ms in medians.items():
        matches.append([window, offset, min(ms), max(ms)])
    return {
        "windows": list(SWEEP_WINDOWS),
        "offsets": list(SWEEP_OFFSETS),
        "example_gaps": example,
        "example_gap_lo": min(g for *_, g in example),
        "example_gap_hi": max(g for *_, g in example),
        "match_gap_medians": matches,
        "match_gap_median_lo": min(lo for _, _, lo, _ in matches),
        "match_gap_median_hi": max(hi for *_, hi in matches),
    }


def build(data_dir: Path, quality: Path) -> dict[str, Any]:
    hook = json.loads(quality.read_text(encoding="utf-8"))["hook"]
    return {
        "schema_version": 1,
        "fps": script.FPS,
        "g": script.G,
        "rim_height": round(script.RIM_HEIGHT, 6),
        "v_h_frames": script.V_H_FRAMES,
        "search_offset": script.SEARCH_OFFSET,
        "tail_back": script.TAIL_BACK,
        "tail_min_index": script.TAIL_MIN_INDEX,
        "digits": DIGITS,
        "example": example(data_dir / "bronze" / "basketball", hook),
        "v_h_sweep": v_h_sweep(data_dir, quality, hook),
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def published_rows(quality: Path) -> dict[str, dict[str, float | None]]:
    """match id -> the five figures of `checks.entry_angle`, named as `entry.summary` names them."""
    rows: dict[str, dict[str, float]] = {}
    for r in json.loads(quality.read_text(encoding="utf-8"))["checks"]["entry_angle"]:
        rows.setdefault(r["match_id"], {})[r["metric"]] = r["value"]
    return {m: {k: v.get(metric) for k, metric in METRICS.items()} for m, v in rows.items()}


def _raw_matches(data_dir: Path) -> Path | None:
    try:
        return raw_root_for(data_dir, SOURCE_ID) / "data" / "matches"
    except (FileNotFoundError, RuntimeError):
        return None


def run_learn_entry(data_dir: Path, out: Path, quality: Path, *, check: bool = False) -> int:
    if not check:
        text = render(build(data_dir, quality))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"learn entry: {out} ({out.stat().st_size} bytes)")
        return 0

    raw_bytes = out.read_bytes()
    if b"\r" in raw_bytes or b"\r" in SCRIPT_PATH.read_bytes():
        print(f"learn entry --check: {out.name} or entry.py has CR line ends")
        return 1
    on_disk = json.loads(raw_bytes.decode("utf-8"))
    rows = published_rows(quality)
    total = len(rows)
    done: list[str] = []

    # 1. The bytes, rebuilt from bronze, when bronze holds the example's match.
    bronze = data_dir / "bronze" / "basketball"
    native = on_disk["example"]["match_id"].removeprefix("bb:")
    rebuilt = False
    if (bronze / "tracking_objects" / f"{native}.parquet").is_file():
        try:
            fresh = render(build(data_dir, quality)).encode("utf-8")
        except ValueError as e:  # a slice without the hook's flight or the sweep's matches
            print(f"learn entry --check: the bronze at hand cannot rebuild the file ({e})")
        else:
            if fresh != raw_bytes:
                print(f"learn entry --check: {out.name} differs from what bronze gives")
                return 1
            rebuilt = True
            done.append(f"the bytes of {out.name} rebuilt from bronze")

    # 2. The public script on the raw files of every match of quality.json.
    matches = _raw_matches(data_dir)
    compared = 0
    different: list[str] = []
    for match_id, want in sorted(rows.items()):
        folder = None if matches is None else matches / match_id.removeprefix("bb:")
        if folder is None or not folder.is_dir():
            continue
        got = script.summary(*script.load(folder))
        compared += 1
        same = {k: None if v is None else float(v) for k, v in got.items()} == want
        verdict = "equal" if same else f"DIFFERENT, quality.json: {want}"
        print(f"learn entry {match_id}: {got} ({verdict})")
        if not same:
            different.append(match_id)
    if different:
        print(f"learn entry: {different} differ from quality.json")
        return 1
    if compared:
        done.append(f"entry.py on the raw files of {compared} match(es) gives quality.json's rows")

    shape = _shape_problems(on_disk)
    if shape:
        print(f"learn entry --check: {shape}")
        return 1
    done.append(
        f"{out.name}'s constants are entry.py's, and its example's angles follow from its "
        "published samples; its sweep's ranges are its rows'"
    )
    if rebuilt and compared == total:
        print(f"learn entry --check: FULL {total}/{total}: " + "; ".join(done))
    else:
        k = compared if rebuilt else 0
        print(f"learn entry --check: PARTIAL {k}/{total}: " + "; ".join(done))
    return 0


def _shape_problems(payload: dict[str, Any]) -> str:
    """What the file must hold whatever data is at hand."""
    constants = {
        "fps": script.FPS,
        "g": script.G,
        "rim_height": round(script.RIM_HEIGHT, 6),
        "v_h_frames": script.V_H_FRAMES,
        "search_offset": script.SEARCH_OFFSET,
        "tail_back": script.TAIL_BACK,
        "tail_min_index": script.TAIL_MIN_INDEX,
    }
    if any(payload[k] != v for k, v in constants.items()):
        return "a constant of the file is not entry.py's"
    ex = payload["example"]
    if not len(ex["x"]) == len(ex["y"]) == len(ex["z"]):
        return "the example's coordinates differ in length"
    fps = payload["fps"]
    samples = [
        (ex["start_frame"] + i, (ex["start_frame"] + i) * 1000 // fps / 1000, x, y, z)
        for i, (x, y, z) in enumerate(zip(ex["x"], ex["y"], ex["z"], strict=True))
    ]
    got = script.flight(samples[payload["search_offset"] :])
    if isinstance(got, str) or _angles(got) != ex["published"]:
        return "the example's angles do not follow from its published samples"
    sw = payload["v_h_sweep"]
    if script.V_H_FRAMES not in sw["windows"] or script.SEARCH_OFFSET not in sw["offsets"]:
        return "the sweep leaves out entry.py's own window or offset"
    spans = (
        (sw["example_gap_lo"], sw["example_gap_hi"], [g for *_, g in sw["example_gaps"]]),
        (
            sw["match_gap_median_lo"],
            sw["match_gap_median_hi"],
            [x for _, _, lo, hi in sw["match_gap_medians"] for x in (lo, hi)],
        ),
    )
    if any((lo, hi) != (min(xs), max(xs)) for lo, hi, xs in spans):
        return "a range of the sweep is not its rows'"
    return ""
