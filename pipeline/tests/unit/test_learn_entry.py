"""`learn/entry.py`, the script of lesson 8's "Reproduce it", against P3's entry-angle check, and
`tracklab learn entry`, which publishes the lesson's example.

A synthetic match in feet: three made shots whose ball flies a true parabola to the rim from
different heights and horizontal speeds, one blocked shot and one miss, with the ball at every
frame. The script, reading the public files' layout, and `quality.entry_angle`, reading samples,
are two implementations of one method; on the synthetic they give the same angles, medians and
reordered share, at every decimal.

Mutations (a test that cannot fail protects nothing): v_h over 4 samples instead of 8; the rim at
3.05 m instead of 3.048; the arrival rounded with `int` instead of `round`; and the script's
selection without the blocked rule. Each moves a figure away from P3's.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.cli import main
from tracklab.learn import entry as script
from tracklab.learn import entry_lesson as el
from tracklab.quality import entry_angle as p3

FT = 0.3048
MATCH = 114086
G = 9.80665
# (start frame, release height m, horizontal speed m/s, horizontal distance to the rim m)
FLIGHTS = [(1000, 2.2, 5.0, 5.0), (2000, 2.6, 6.5, 7.2), (3000, 1.9, 4.2, 4.6)]
BLOCKED, MISSED = 4000, 5000
DECEL = 1.5  # m/s²


def _ball() -> dict[int, tuple[float, float, float]]:
    """Frame -> ball (m): each flight leaves `start + 2` along y = 0 toward the rim at +x, slowing
    horizontally by `DECEL` (as the tracked ball does), its height a true parabola under G."""
    ball: dict[int, tuple[float, float, float]] = {}
    for start, z0, v_h, d in [*FLIGHTS, (BLOCKED, 2.2, 5.0, 5.0), (MISSED, 2.2, 5.0, 5.0)]:
        t_flight = d / v_h
        v_z0 = (script.RIM_HEIGHT - z0 + 0.5 * G * t_flight**2) / t_flight
        for k in range(-10, 70):
            t = k / 25
            x = script.RIM_X - d + v_h * t - 0.5 * DECEL * t * t
            ball[start + 2 + k] = (x, 0.0, z0 + v_z0 * t - 0.5 * G * t * t)
    return ball


def _v_z(flight: tuple[int, float, float, float], t: float) -> float:
    start, z0, v_h, d = flight
    t_flight = d / v_h
    return (script.RIM_HEIGHT - z0 + 0.5 * G * t_flight**2) / t_flight - G * t


def _shots() -> list[dict[str, Any]]:
    shots = [
        {"startFrame": s, "endFrame": s + 30, "distance": 10.0, "outcome": True, "blocked": False}
        for s, *_ in FLIGHTS
    ]
    shots.append(
        {
            "startFrame": BLOCKED,
            "endFrame": BLOCKED + 30,
            "distance": 10.0,
            "outcome": True,
            "blocked": True,
        }
    )
    shots.append(
        {
            "startFrame": MISSED,
            "endFrame": MISSED + 30,
            "distance": 10.0,
            "outcome": False,
            "blocked": False,
        }
    )
    return shots


def write_raw(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{MATCH}_dynamic_events.json").write_text(
        json.dumps({"shots": _shots()}), encoding="utf-8"
    )
    lines = [
        json.dumps({"frameIdx": f, "period": 1, "ball": {"xyz": [x / FT, y / FT, z / FT]}})
        for f, (x, y, z) in sorted(_ball().items())
    ]
    with gzip.open(folder / f"{MATCH}_tracking_data.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_bronze(root: Path) -> None:
    bronze = root / "bronze" / "basketball"
    for table in ("tracking_objects", "tracking_frames"):
        (bronze / table).mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE o (frameIdx BIGINT, side VARCHAR, x DOUBLE, y DOUBLE, z DOUBLE)")
    con.executemany(
        "INSERT INTO o VALUES (?, 'ball', ?, ?, ?)",
        [(f, x / FT, y / FT, z / FT) for f, (x, y, z) in sorted(_ball().items())],
    )
    con.execute("CREATE TABLE f AS SELECT DISTINCT frameIdx, 1::SMALLINT AS period FROM o")
    for name, table in (("tracking_objects", "o"), ("tracking_frames", "f")):
        con.execute(
            f"COPY {table} TO '{(bronze / name / f'{MATCH}.parquet').as_posix()}' (FORMAT parquet)"
        )


def _p3_rows(samples: list[script.Sample]) -> dict[str, float | None]:
    """P3's own module on the same samples: the five figures `entry.summary` names."""
    starts = [s["startFrame"] for s in _shots() if s["outcome"] and not s["blocked"]]
    results = p3._results(f"bb:{MATCH}", MATCH, p3._match(samples, sorted(starts)))
    by = {r.metric: r.value for r in results}
    return {k: by.get(metric) for k, metric in el.METRICS.items()}


def test_the_script_on_the_raw_layout_is_p3s_check(tmp_path: Path) -> None:
    write_raw(tmp_path / "m" / str(MATCH))
    starts, samples = script.load(tmp_path / "m" / str(MATCH))
    assert starts == [s for s, *_ in FLIGHTS]
    got = script.summary(starts, samples)
    print(f"learn entry synthetic: {got}")
    assert got["shots"] == len(FLIGHTS)
    assert {k: None if v is None else float(v) for k, v in got.items()} == _p3_rows(samples)


def test_on_a_true_parabola_the_reported_angle_is_the_tangent_three_frames_early(
    tmp_path: Path,
) -> None:
    """The tail's line runs through samples k - 6 to k; on a parabola its slope is the tangent at
    the middle one, three frames before the arrival. So even a flight that obeys gravity exactly
    reports a shallower angle than the one it arrives at: the method's own gap."""
    write_raw(tmp_path / "m" / str(MATCH))
    _, samples = script.load(tmp_path / "m" / str(MATCH))
    for flight in FLIGHTS:
        run = script.run_of(samples, flight[0])
        assert not isinstance(run, str)
        fl = script.flight(run)
        assert not isinstance(fl, str)
        middle = (int(fl["k"]) - script.TAIL_BACK // 2) / 25
        want = math.degrees(math.atan2(abs(_v_z(flight, middle)), fl["v_h"]))
        assert fl["reported"] == pytest.approx(want, abs=1e-9)
        assert fl["required"] > fl["reported"] + 3


def test_the_constants_are_p3s() -> None:
    assert (script.RIM_HEIGHT, script.V_H_FRAMES, script.V_H_MIN) == (
        p3.RIM_HEIGHT,
        p3.V_H_FRAMES,
        p3.V_H_MIN,
    )
    assert (script.T_MIN, script.T_MAX, script.TAIL_BACK, script.TAIL_MIN_INDEX) == (
        p3.T_MIN,
        p3.T_MAX,
        p3.TAIL_BACK,
        p3.TAIL_MIN_INDEX,
    )
    assert (script.SEARCH_OFFSET, script.SEG_LEN, script.MIN_CONTIG) == (
        p3.SEARCH_OFFSET,
        p3.SEG_LEN,
        p3.MIN_CONTIG,
    )
    assert script.G == p3.G
    assert script.RIM_X == pytest.approx(p3.RIM_X, abs=1e-12)


MUTATIONS: dict[str, tuple[str, Any]] = {
    "v_h over 4 samples": ("V_H_FRAMES", 4),
    "the rim at 3.05 m": ("RIM_HEIGHT", 3.05),
}


@pytest.mark.parametrize("name", MUTATIONS)
def test_each_mutation_moves_a_figure_away_from_p3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    write_raw(tmp_path / "m" / str(MATCH))
    starts, samples = script.load(tmp_path / "m" / str(MATCH))
    want = _p3_rows(samples)
    attr, value = MUTATIONS[name]
    monkeypatch.setattr(script, attr, value)
    got = script.summary(starts, samples)
    assert {k: None if v is None else float(v) for k, v in got.items()} != want, name


def test_mutation_arrival_by_int_and_no_blocked_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_raw(tmp_path / "m" / str(MATCH))
    starts, samples = script.load(tmp_path / "m" / str(MATCH))
    want = script.summary(starts, samples)
    real = round
    monkeypatch.setattr(
        script, "round", lambda x, n=None: int(x) if n is None else real(x, n), raising=False
    )
    assert script.summary(starts, samples) != want
    monkeypatch.undo()
    assert len(starts) + 1 == len([s for s in _shots() if s["outcome"]])  # the blocked one is out


def test_the_script_is_lf_and_imports_nothing_of_track_lab() -> None:
    text = el.SCRIPT_PATH.read_bytes()
    assert b"\r" not in text
    assert b"tracklab" not in text.split(b'"""')[2]  # nothing after the docstring names it


# The example and the command, on a data root made in tmp_path.


def _quality(path: Path, samples: list[script.Sample]) -> None:
    rows = [
        {
            "sport": "basketball",
            "match_id": f"bb:{MATCH}",
            "metric": metric,
            "value": value,
            "unit": "",
            "n": 1,
        }
        for k, metric in el.METRICS.items()
        if (value := _p3_rows(samples)[k]) is not None
    ]
    hook = {"match_id": f"bb:{MATCH}", "shot_id": f"shot-{MATCH}-1-1", "start_frame": FLIGHTS[0][0]}
    path.write_text(json.dumps({"checks": {"entry_angle": rows}, "hook": hook}), encoding="utf-8")


def _root(tmp_path: Path, *, raw: bool) -> Path:
    root = tmp_path / "data"
    write_bronze(root)
    write_raw(tmp_path / "scratch" / str(MATCH))
    _quality(tmp_path / "quality.json", script.load(tmp_path / "scratch" / str(MATCH))[1])
    if raw:
        receipt = root / "raw" / "opendata-basketball"
        receipt.mkdir(parents=True)
        (receipt / "_receipt.json").write_text(json.dumps({"failed": []}), encoding="utf-8")
        write_raw(receipt / "data" / "matches" / str(MATCH))
    return root


def _run(root: Path, out: Path, *extra: str) -> int:
    args = ["learn", "entry", "--data-dir", str(root), "--out", str(out)]
    return main([*args, "--quality", str(root.parent / "quality.json"), *extra])


def test_the_example_reaches_the_rim_and_its_angles_follow_from_its_samples(tmp_path: Path) -> None:
    root = _root(tmp_path, raw=False)
    out = tmp_path / "entry.json"
    assert _run(root, out) == 0
    ex = json.loads(out.read_text(encoding="utf-8"))["example"]
    assert ex["start_frame"] == FLIGHTS[0][0]
    run = script.run_of(script.load(tmp_path / "scratch" / str(MATCH))[1], FLIGHTS[0][0])
    full = script.flight(run) if not isinstance(run, str) else run
    assert not isinstance(full, str)
    assert ex["published"]["k"] == full["k"]
    assert len(ex["z"]) > ex["published"]["k"] + script.SEARCH_OFFSET
    assert ex["z"][-1] <= script.RIM_HEIGHT < max(ex["z"])
    assert ex["published"]["required"] == pytest.approx(ex["full_precision"]["required"], abs=0.01)


def test_the_file_is_lf_and_checks_full_then_partial_then_fails_on_a_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=True)
    out = tmp_path / "learn" / "entry.json"
    assert _run(root, out) == 0
    assert b"\r" not in out.read_bytes()
    assert _run(root, out, "--check") == 0
    assert "FULL 1/1" in capsys.readouterr().out
    out.write_text(
        out.read_text(encoding="utf-8").replace('"tail_back": 6', '"tail_back": 5'),
        encoding="utf-8",
        newline="\n",
    )
    assert _run(root, out, "--check") == 1
    assert "differs from what bronze gives" in capsys.readouterr().out
