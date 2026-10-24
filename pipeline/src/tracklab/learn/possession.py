"""`tracklab learn possession`: how often does possession change hands (lesson 10, P9)?

Two sports, two files, one question: how long does a team keep the ball?

Football: bronze `phases_of_play`, read through five columns only (`index, frame_start, frame_end,
period, team_in_possession_id`; never a width, a length or any other column), for the matches
the Analytics Cup fence leaves outside its held-out list (`web/lib/learn/fence.json`): a match it
holds out is never read. A run is a stretch of consecutive phases (by `index`) of one period with
the same team in possession; a phase with no team breaks it and is no run. It spans from its first
`frame_start` to its last `frame_end`, at `FOOTBALL_HZ`. Per match: phases, runs, the median and
90th percentile of the run (s, linear interpolation as DuckDB's `quantile_cont`) and the share of
runs that span more than one phase.

Basketball: bronze `events_possessions`, one row per possession from `startFrame` to `endFrame` at
`BASKETBALL_FPS`. Per match: possessions, the median and the 90th percentile (s).

The timelines are the runs of one football match and the possessions of one basketball match, in
order, for the figure.

`--check` rebuilds the file from bronze and compares its bytes, and runs the two queries of
`possession.sql` (the ones "Reproduce it" shows) on the public raw files, comparing them with the
file: `FULL n/n` per sport when both were done for its n matches, else `PARTIAL k/n` and what it
checked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from tracklab.bronze.common import raw_root_for

FENCE_PATH = Path(__file__).resolve().parents[4] / "web" / "lib" / "learn" / "fence.json"
SQL_PATH = Path(__file__).with_name("possession.sql")
FOOTBALL_SOURCE = "opendata-football"
BASKETBALL_SOURCE = "opendata-basketball"
FOOTBALL_SQL_ID = "1874553"  # the football match the public SQL is written for, and the timeline's
BASKETBALL_SQL_ID = "114086"  # the basketball one
SQL_NAMES = 2  # each query names its match in one folder and one file name

FOOTBALL_HZ = 10  # the provider's README: "the frame of the video the data comes from at 10 fps"
BASKETBALL_FPS = 25  # the provider's dictionary: `startFrame`, "Frame (at 25fps)"
SECONDS_DIGITS = 4
PCT_DIGITS = 2
PHASE_COLUMNS = "index, frame_start, frame_end, period, team_in_possession_id"


def held_out() -> set[str]:
    return set(json.loads(FENCE_PATH.read_text(encoding="utf-8"))["held_out"])


def _q(values: list[float], q: float) -> float | None:
    return round(float(np.quantile(values, q)), SECONDS_DIGITS) if values else None


# Football.


Phase = tuple[int, int, int, int, int | None]  # index, frame_start, frame_end, period, team


def football_runs(phases: list[Phase]) -> list[tuple[int, int, int, int, int]]:
    """The runs of same-team phases within a period: (period, first frame, last frame, team,
    phases), in order. A phase with no team ends the run before it and starts none."""
    runs: list[list[int]] = []
    last: tuple[int, int | None] | None = None
    for _, f0, f1, period, team in sorted(phases, key=lambda p: (p[3], p[0])):
        if team is not None and last == (period, team):
            runs[-1][2] = max(runs[-1][2], f1)
            runs[-1][1] = min(runs[-1][1], f0)
            runs[-1][4] += 1
        elif team is not None:
            runs.append([period, f0, f1, team, 1])
        last = (period, team)
    return [(p, a, b, t, n) for p, a, b, t, n in runs]


def football_figures(phases: list[Phase]) -> dict[str, Any]:
    runs = football_runs(phases)
    seconds = [(b - a) / FOOTBALL_HZ for _, a, b, _, _ in runs]
    multi = [n > 1 for *_, n in runs]
    return {
        "phases": len(phases),
        "runs": len(runs),
        "run_median_s": _q(seconds, 0.5),
        "run_p90_s": _q(seconds, 0.9),
        "multi_phase_pct": round(100 * sum(multi) / len(multi), PCT_DIGITS) if multi else None,
    }


def read_phases(bronze: Path, match: int) -> list[Phase]:
    rows = (
        duckdb.connect()
        .execute(
            f"SELECT {PHASE_COLUMNS} FROM read_parquet(?)",
            [(bronze / "phases_of_play" / f"{match}.parquet").as_posix()],
        )
        .fetchall()
    )
    return [
        (int(i), int(a), int(b), int(p), None if t is None else int(t)) for i, a, b, p, t in rows
    ]


def football_matches(bronze: Path) -> list[int]:
    """The football matches of bronze outside the fence's held-out list."""
    out = held_out()
    found = sorted(p.stem for p in (bronze / "phases_of_play").glob("*.parquet"))
    return [int(m) for m in found if m not in out]


# Basketball.


def read_possessions(bronze: Path, match: int) -> list[tuple[int, int, int, int]]:
    """(period, startFrame, endFrame, offTeamId) of every possession with both frames, in order."""
    rows = (
        duckdb.connect()
        .execute(
            "SELECT period, startFrame, endFrame, offTeamId FROM read_parquet(?) "
            "WHERE startFrame IS NOT NULL AND endFrame IS NOT NULL ORDER BY startFrame, id",
            [(bronze / "events_possessions" / f"{match}.parquet").as_posix()],
        )
        .fetchall()
    )
    return [(int(p), int(a), int(b), int(t)) for p, a, b, t in rows]


def basketball_figures(possessions: list[tuple[int, int, int, int]]) -> dict[str, Any]:
    seconds = [(b - a) / BASKETBALL_FPS for _, a, b, _ in possessions]
    return {
        "possessions": len(possessions),
        "median_s": _q(seconds, 0.5),
        "p90_s": _q(seconds, 0.9),
    }


def basketball_matches(bronze: Path) -> list[int]:
    return sorted(int(p.stem) for p in (bronze / "events_possessions").glob("*.parquet"))


# The file.


def _teams(ids: list[int]) -> list[int]:
    """Team ids in the order they first appear."""
    return list(dict.fromkeys(ids))


def build(data_dir: Path) -> dict[str, Any]:
    fb = data_dir / "bronze" / "football"
    bb = data_dir / "bronze" / "basketball"
    fb_matches, bb_matches = football_matches(fb), basketball_matches(bb)
    if not fb_matches or not bb_matches:
        raise FileNotFoundError(
            f"no bronze phases_of_play under {fb} or events_possessions under {bb}"
        )
    fb_example, bb_example = int(FOOTBALL_SQL_ID), int(BASKETBALL_SQL_ID)
    runs = football_runs(read_phases(fb, fb_example))
    fb_teams = _teams([t for *_, t, _ in runs])
    poss = read_possessions(bb, bb_example)
    bb_teams = _teams([t for *_, t in poss])
    return {
        "schema_version": 1,
        "football_hz": FOOTBALL_HZ,
        "basketball_fps": BASKETBALL_FPS,
        "football": {
            "matches": [
                {"match_id": f"fb:{m}", **football_figures(read_phases(fb, m))} for m in fb_matches
            ],
            "timeline": {
                "match_id": f"fb:{fb_example}",
                "teams": fb_teams,
                "columns": ["period", "start_s", "end_s", "team", "phases"],
                "rows": [
                    [p, a / FOOTBALL_HZ, b / FOOTBALL_HZ, fb_teams.index(t), n]
                    for p, a, b, t, n in runs
                ],
            },
        },
        "basketball": {
            "matches": [
                {"match_id": f"bb:{m}", **basketball_figures(read_possessions(bb, m))}
                for m in bb_matches
            ],
            "timeline": {
                "match_id": f"bb:{bb_example}",
                "teams": bb_teams,
                "columns": ["period", "start_s", "end_s", "team"],
                "rows": [
                    [p, a / BASKETBALL_FPS, b / BASKETBALL_FPS, bb_teams.index(t)]
                    for p, a, b, t in poss
                ],
            },
        },
    }


SCALARS = re.compile(r"\[\s+([^\[\]{}\"]*?)\s+\]")


def render(payload: dict[str, Any]) -> str:
    """Indented JSON with every list of numbers on one line, so a timeline is a row per line."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        SCALARS.sub(lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", text)
        + "\n"
    )


# The public SQL, run on the raw files.

FOOTBALL_FIELDS = ("phases", "runs", "run_median_s", "run_p90_s", "multi_phase_pct")
BASKETBALL_FIELDS = ("possessions", "median_s", "p90_s")
COUNTS = {"phases", "runs", "possessions"}


def read_sql() -> tuple[str, str]:
    """The football query and the basketball query, in that order."""
    text = SQL_PATH.read_bytes().decode("utf-8")
    football, basketball = (s.strip() for s in re.split(r";[ \t]*\n", text) if s.strip())
    return football, basketball


def run_sql(sql: str, roots: dict[str, Path], fields: tuple[str, ...]) -> tuple[Any, ...]:
    """A query with its repositories' folders (`opendata/`, `opendata-basketball/`) at `roots`."""
    for name, root in roots.items():
        sql = sql.replace(f"'{name}/", f"'{root.as_posix()}/")
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    row = con.execute(sql).fetchone()
    assert row is not None
    return tuple(
        None if v is None else int(v) if k in COUNTS else float(v)
        for k, v in zip(fields, row, strict=True)
    )


def _raw(data_dir: Path, source: str) -> Path | None:
    try:
        return raw_root_for(data_dir, source)
    except (FileNotFoundError, RuntimeError):
        return None


def run_learn_possession(data_dir: Path, out: Path, *, check: bool = False) -> int:
    if not check:
        text = render(build(data_dir))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"learn possession: {out} ({out.stat().st_size} bytes)")
        return 0

    football_sql, basketball_sql = read_sql()
    for sql, sid in ((football_sql, FOOTBALL_SQL_ID), (basketball_sql, BASKETBALL_SQL_ID)):
        if sql.count(sid) != SQL_NAMES:
            print(f"learn possession: a query names {sid} {sql.count(sid)} times, not {SQL_NAMES}")
            return 1
    raw_bytes = out.read_bytes()
    if b"\r" in raw_bytes:
        print(f"learn possession --check: {out.name} has CR line ends")
        return 1
    on_disk = json.loads(raw_bytes.decode("utf-8"))
    out_ids = {f"fb:{h}" for h in held_out()}
    fenced = [m["match_id"] for m in on_disk["football"]["matches"] if m["match_id"] in out_ids]
    if fenced or on_disk["football"]["timeline"]["match_id"] in out_ids:
        print(f"learn possession --check: {out.name} holds held-out matches {fenced}")
        return 1
    done: list[str] = [f"no football match of {out.name} is held out by the fence"]

    # 1. The bytes, rebuilt from bronze, when bronze holds every match the file was measured on.
    fb = data_dir / "bronze" / "football"
    bb = data_dir / "bronze" / "basketball"
    rows = {
        sport: {m["match_id"]: m for m in on_disk[sport]["matches"]}
        for sport in ("football", "basketball")
    }
    have = {
        "football": {f"fb:{m}" for m in football_matches(fb)}
        if (fb / "phases_of_play").is_dir()
        else set(),
        "basketball": {f"bb:{m}" for m in basketball_matches(bb)}
        if (bb / "events_possessions").is_dir()
        else set(),
    }
    rebuilt = all(have[s] == set(rows[s]) for s in rows)
    if rebuilt:
        if render(build(data_dir)).encode("utf-8") != raw_bytes:
            print(f"learn possession --check: {out.name} differs from what bronze gives")
            return 1
        done.append(f"the bytes of {out.name} rebuilt from bronze")
    else:
        # A slice (the CI fixtures): the code runs on it, but its figures are not the file's.
        for m in football_matches(fb) if have["football"] else []:
            print(f"learn possession fb:{m} (bronze slice, not compared): ", end="")
            print(football_figures(read_phases(fb, m)))
        for m in basketball_matches(bb) if have["basketball"] else []:
            print(f"learn possession bb:{m} (bronze slice, not compared): ", end="")
            print(basketball_figures(read_possessions(bb, m)))
        n = len(have["football"]) + len(have["basketball"])
        done.append(f"the code ran on the bronze of {n} match(es) not compared")

    # 2. The public SQL on the raw files.
    fb_raw, bb_raw = _raw(data_dir, FOOTBALL_SOURCE), _raw(data_dir, BASKETBALL_SOURCE)
    plan = (
        ("football", football_sql, FOOTBALL_SQL_ID, "opendata", fb_raw, FOOTBALL_FIELDS),
        (
            "basketball",
            basketball_sql,
            BASKETBALL_SQL_ID,
            "opendata-basketball",
            bb_raw,
            BASKETBALL_FIELDS,
        ),
    )
    compared = {"football": 0, "basketball": 0}
    different: list[str] = []
    for sport, sql, sid, repo, root, fields in plan:
        for match_id, row in sorted(rows[sport].items()):
            native = match_id.split(":")[1]
            if root is None or not (root / "data" / "matches" / native).is_dir():
                continue
            got = run_sql(sql.replace(sid, native), {repo: root}, fields)
            want = tuple(row[k] for k in fields)
            compared[sport] += 1
            print(
                f"learn possession {match_id}: "
                + " ".join(f"{k}={v}" for k, v in zip(fields, got, strict=True))
                + f" ({'equal' if got == want else f'DIFFERENT, {out.name}: {want}'})"
            )
            if got != want:
                different.append(match_id)
    if different:
        print(f"learn possession: {different} differ from {out.name}")
        return 1
    for sport, n in compared.items():
        if n:
            done.append(f"possession.sql's {sport} query on the raw files of {n} match(es)")

    shape = _shape_problems(on_disk)
    if shape:
        print(f"learn possession --check: {shape}")
        return 1
    done.append(f"{out.name} has every field, and its timelines agree with their match's row")
    verdicts = []
    for sport in ("football", "basketball"):
        total = len(rows[sport])
        k = compared[sport] if rebuilt else 0
        verdicts.append(f"{sport} {'FULL' if k == total else 'PARTIAL'} {k}/{total}")
    print(f"learn possession --check: {', '.join(verdicts)}: " + "; ".join(done))
    return 0


def _shape_problems(payload: dict[str, Any]) -> str:
    """What the file must hold whatever data is at hand."""
    want = {
        "football": {"match_id", *FOOTBALL_FIELDS},
        "basketball": {"match_id", *BASKETBALL_FIELDS},
    }
    for sport, fields in want.items():
        for m in payload[sport]["matches"]:
            if set(m) != fields:
                return f"{m.get('match_id')}: fields {sorted(set(m) ^ fields)}"
    tl = payload["football"]["timeline"]
    row = {m["match_id"]: m for m in payload["football"]["matches"]}.get(tl["match_id"])
    if row is None or len(tl["rows"]) != row["runs"]:
        return f"the football timeline is not its match's {row and row['runs']} runs"
    tl = payload["basketball"]["timeline"]
    row = {m["match_id"]: m for m in payload["basketball"]["matches"]}.get(tl["match_id"])
    if row is None or len(tl["rows"]) != row["possessions"]:
        return "the basketball timeline is not its match's possessions"
    return ""
