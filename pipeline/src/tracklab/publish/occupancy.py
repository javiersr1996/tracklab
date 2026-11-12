"""`tracklab publish occupancy`: where the players of each football position group are (task 184b).

`web/public/data/occupancy.json` is a heat map per position group, pooled over the football matches
the Analytics Cup fence leaves outside its held-out list (`web/lib/learn/fence.json`): a match it
holds out is never read, and one passed in is refused. It is plain occupancy over whole matches,
every frame silver holds: no split by phase, by team or by player, and nothing about how a position
was measured. Only aggregates are published, never a player or a team.

Inputs, one match at a time so DuckDB never holds more than one match's frames: silver `frames`
(the players' `x_m`, `y_m`, `period` and `team_id`), `dim_team_period` (`attack_sign`, which way
each team attacks in each period), `dim_match` (the pitch's size, competition and season),
`dim_sport` (the sample rate) and the bronze `match_players` of the match, whose `position_group`
is the provider's label for a player in that match (the label of the season aggregates
`/warehouse/positions` groups by). A goalkeeper (`player_role_name` "Goalkeeper", group "Other")
and a player with no group of the five are left out and counted.

1. **Every team attacks left to right.** A position is turned with its own team's sign in that
   period: `x = attack_sign * x_m`, `y = attack_sign * y_m`, the 180 degree turn of the replay's
   "normalize attack", with each player's own team rather than the team with the ball. +y is then
   the left of a player facing the goal he attacks.
2. **One pitch.** The pitches measure 104 to 106 m by 68 m. Each match is scaled onto
   `LENGTH_M` by `WIDTH_M` (x by `LENGTH_M / length`, y by `WIDTH_M / width`, at most 1 % here),
   so goal lines and touchlines land on the same cells.
3. **The grid.** `COLS` by `ROWS` cells of 3.5 m by 3.4 m; thirds of the pitch and five lanes of
   four rows fall on cell edges. Cell `row * COLS + col`, col 0 at the own goal line (x = -52.5),
   row 0 at the right touchline (y = -34).
4. **Off the pitch or missing.** A position outside the lines of its own pitch (`|x_m| > length /
   2` or `|y_m| > width / 2`) is counted in `off_pitch` and not binned; one without `x_m` or
   `y_m` in `missing`. A position on a line is binned in the edge cell.
5. **Shares.** Per group, a cell's share is its player-frames over the group's binned
   player-frames, in units of 1 / `SHARE_SCALE`, rounded by largest remainder (ties to the lower
   cell) so every group sums to exactly `SHARE_SCALE`. "Outfield" pools the five groups.

`--check` recomputes the file when every match it names is at hand and compares the bytes (`FULL
n/n`); on a slice (the CI fixtures) the code runs on what is there and says `PARTIAL k/n`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import duckdb

from tracklab.learn.possession import held_out

OCCUPANCY_JSON = "occupancy.json"
SCHEMA_VERSION = 1
LENGTH_M = 105.0
WIDTH_M = 68.0
COLS = 30
ROWS = 20
SHARE_SCALE = 100_000
GROUPS = ("Central Defender", "Full Back", "Midfield", "Wide Attacker", "Center Forward")
OUTFIELD = "Outfield"
GOALKEEPER_ROLE = "Goalkeeper"
SOURCE = (
    "SkillCorner open data (github.com/SkillCorner/opendata): silver frames, dim_team_period, "
    "dim_match and dim_sport, and the bronze match_players of each match"
)
NOTE = (
    "occupancy pooled over whole matches: every player-frame of the matches listed, turned so "
    "each team attacks towards +x and scaled onto one pitch; a position group is the provider's "
    "label for a player in that match; goalkeepers and players with no group are left out; a "
    "position off its pitch or missing is counted, not binned; shares in units of 1/share_scale, "
    "each group summing to share_scale"
)
_SCALARS = re.compile(r"\[\s+([^\[\]{}\"]*?)\s+\]")


class FenceError(ValueError):
    """A held-out match reached the code that reads frames."""


def silver(data_dir: Path) -> Path:
    return data_dir / "silver"


def frames_dir(data_dir: Path, match: str) -> Path:
    return silver(data_dir) / "frames" / "sport=football" / f"native_match_id={match}"


def players_file(data_dir: Path, match: str) -> Path:
    return data_dir / "bronze" / "football" / "match_players" / f"{match}.parquet"


def matches_at_hand(data_dir: Path) -> list[str]:
    """The football matches with silver frames and bronze players, outside the fence: a held-out
    partition is skipped by its name, before anything in it is opened."""
    root = silver(data_dir) / "frames" / "sport=football"
    out = held_out()
    found = sorted(p.name.removeprefix("native_match_id=") for p in root.glob("native_match_id=*"))
    return [
        m
        for m in found
        if m not in out
        and any(frames_dir(data_dir, m).glob("*.parquet"))
        and players_file(data_dir, m).is_file()
    ]


def _one(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> tuple[Any, ...]:
    row = con.execute(sql, params).fetchone()
    if row is None:
        raise ValueError(f"no row for {params}")
    return tuple(row)


# A match's player-frames counted by player, group (or why it has none) and cell (or why it is
# not binned): a few thousand rows, which Python adds up. No player leaves this module.
MATCH_SQL = f"""
WITH f AS (
    SELECT entity_id, period, team_id, x_m, y_m
    FROM read_parquet($frames)
    WHERE entity_kind = 'player'
),
p AS (
    SELECT 'fb:' || id AS entity_id, position_group, player_role_name
    FROM read_parquet($players)
),
tp AS (
    SELECT period, team_id, attack_sign
    FROM read_parquet($team_period)
    WHERE match_id = $match_id
),
j AS (
    SELECT
        f.entity_id,
        CASE
            WHEN p.player_role_name = '{GOALKEEPER_ROLE}' THEN '#goalkeeper'
            WHEN p.position_group IN ({", ".join(f"'{g}'" for g in GROUPS)}) THEN p.position_group
            ELSE '#no_group'
        END AS grp,
        CASE
            WHEN f.x_m IS NULL OR f.y_m IS NULL THEN 'missing'
            WHEN abs(f.x_m) > $length / 2 OR abs(f.y_m) > $width / 2 THEN 'off_pitch'
            ELSE 'binned'
        END AS status,
        tp.attack_sign * f.x_m * {LENGTH_M} / $length AS x,
        tp.attack_sign * f.y_m * {WIDTH_M} / $width AS y,
        tp.attack_sign
    FROM f
    LEFT JOIN p USING (entity_id)
    LEFT JOIN tp ON tp.period = f.period AND tp.team_id = f.team_id
)
SELECT
    entity_id,
    grp,
    status,
    CASE WHEN status = 'binned'
        THEN least({COLS - 1}, CAST(floor((x + {LENGTH_M / 2}) * {COLS} / {LENGTH_M}) AS INTEGER))
    END AS col,
    CASE WHEN status = 'binned'
        THEN least({ROWS - 1}, CAST(floor((y + {WIDTH_M / 2}) * {ROWS} / {WIDTH_M}) AS INTEGER))
    END AS "row",
    count(*) AS n,
    count(*) FILTER (WHERE attack_sign IS NULL) AS unsigned
FROM j
GROUP BY ALL
"""


class Tally:
    """What the matches add up to: player-frames per group and cell, and what was left out."""

    def __init__(self) -> None:
        self.cells: dict[str, Counter[int]] = {g: Counter() for g in GROUPS}
        self.off_pitch: Counter[str] = Counter()
        self.missing: Counter[str] = Counter()
        self.left_out: Counter[str] = Counter()
        self.player_matches: Counter[str] = Counter()
        self.group_matches: Counter[str] = Counter()
        self.frames = 0

    def add_match(self, con: duckdb.DuckDBPyConnection, data_dir: Path, match: str) -> None:
        if match in held_out():
            raise FenceError(f"match {match} is held out by the Analytics Cup fence")
        frames = (frames_dir(data_dir, match) / "*.parquet").as_posix()
        dims = silver(data_dir)
        match_id = f"fb:{match}"
        length, width = _one(
            con,
            "SELECT surface_length_m, surface_width_m FROM read_parquet(?) WHERE match_id = ?",
            [(dims / "dim_match" / "data.parquet").as_posix(), match_id],
        )
        players = players_file(data_dir, match).as_posix()
        (twice,) = _one(con, "SELECT count(*) - count(DISTINCT id) FROM read_parquet(?)", [players])
        if twice:
            raise ValueError(f"{match_id}: {twice} player(s) listed twice in match_players")
        params = {
            "frames": frames,
            "players": players,
            "team_period": (dims / "dim_team_period" / "data.parquet").as_posix(),
            "match_id": match_id,
            "length": float(length),
            "width": float(width),
        }
        binned: dict[str, set[str]] = {}
        for entity, grp, status, col, row, n, unsigned in con.execute(MATCH_SQL, params).fetchall():
            if grp.startswith("#"):
                self.left_out[grp[1:]] += n
                continue
            if unsigned:
                raise ValueError(f"{match_id}: {unsigned} {grp} player-frames with no attack sign")
            if status == "binned":
                self.cells[grp][row * COLS + col] += n
                binned.setdefault(grp, set()).add(entity)
            elif status == "off_pitch":
                self.off_pitch[grp] += n
            else:
                self.missing[grp] += n
        for grp, entities in binned.items():
            self.group_matches[grp] += 1
            self.player_matches[grp] += len(entities)
        (frames_seen,) = _one(
            con, "SELECT count(DISTINCT frame_native) FROM read_parquet(?)", [frames]
        )
        self.frames += int(frames_seen)


def shares(counts: Counter[int], cells: int = COLS * ROWS, scale: int = SHARE_SCALE) -> list[int]:
    """Each cell's share of `counts` in units of 1 / `scale`, summing to exactly `scale`: the
    floor of each, then one more unit to the largest remainders, ties to the lower cell."""
    total = sum(counts.values())
    if total == 0:
        raise ValueError("no player-frame to share")
    floors, rests = [], []
    for c in range(cells):
        q, r = divmod(counts.get(c, 0) * scale, total)
        floors.append(q)
        rests.append((-r, c))
    for _, c in sorted(rests)[: scale - sum(floors)]:
        floors[c] += 1
    return floors


def _group_block(t: Tally, name: str, groups: Iterable[str], matches: int) -> dict[str, Any]:
    gs = list(groups)
    counts: Counter[int] = Counter()
    for g in gs:
        counts.update(t.cells[g])
    return {
        "group": name,
        "player_frames": sum(counts.values()),
        "player_matches": sum(t.player_matches[g] for g in gs),
        "matches": matches if name == OUTFIELD else t.group_matches[name],
        "off_pitch": sum(t.off_pitch[g] for g in gs),
        "missing": sum(t.missing[g] for g in gs),
        "share": shares(counts),
    }


def build(data_dir: Path, matches: list[str]) -> dict[str, Any]:
    fenced = sorted(set(matches) & held_out())
    if fenced:
        raise FenceError(f"held out by the Analytics Cup fence: {fenced}")
    if not matches:
        raise ValueError("no football match to read")
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    dims = silver(data_dir)
    ids = [f"fb:{m}" for m in matches]
    about = con.execute(
        "SELECT DISTINCT competition, season FROM read_parquet(?) WHERE list_contains(?, match_id)",
        [(dims / "dim_match" / "data.parquet").as_posix(), ids],
    ).fetchall()
    if len(about) != 1:
        raise ValueError(f"the matches span {len(about)} competitions and seasons")
    pitches = con.execute(
        "SELECT surface_length_m, surface_width_m, count(*) FROM read_parquet(?) "
        "WHERE list_contains(?, match_id) GROUP BY ALL ORDER BY 1, 2",
        [(dims / "dim_match" / "data.parquet").as_posix(), ids],
    ).fetchall()
    (hz,) = _one(
        con,
        "SELECT sample_rate_hz FROM read_parquet(?) WHERE sport = 'football'",
        [(dims / "dim_sport" / "data.parquet").as_posix()],
    )
    tally = Tally()
    for m in sorted(matches):
        tally.add_match(con, data_dir, m)
    blocks = [_group_block(tally, g, [g], len(matches)) for g in GROUPS]
    blocks.append(_group_block(tally, OUTFIELD, GROUPS, len(matches)))
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "note": NOTE,
        "sport": "football",
        "competition": about[0][0],
        "season": about[0][1],
        "sample_rate_hz": int(hz),
        "matches": sorted(matches),
        "frames": tally.frames,
        "grid": {
            "length_m": LENGTH_M,
            "width_m": WIDTH_M,
            "cols": COLS,
            "rows": ROWS,
            "cell_length_m": LENGTH_M / COLS,
            "cell_width_m": WIDTH_M / ROWS,
            "cell": "row * cols + col; col 0 at the own goal line (x = -length_m / 2), row 0 at "
            "the right touchline (y = -width_m / 2) of a team attacking towards +x",
            "pitches": [
                {"length_m": float(length), "width_m": float(width), "matches": int(n)}
                for length, width, n in pitches
            ],
            "scaling": "x by length_m / the pitch's length, y by width_m / its width",
        },
        "share_scale": SHARE_SCALE,
        "left_out": {
            "goalkeeper": tally.left_out["goalkeeper"],
            "no_group": tally.left_out["no_group"],
        },
        "groups": blocks,
    }


def render(payload: dict[str, Any]) -> str:
    """Indented JSON with every list of numbers on one line."""
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    return (
        _SCALARS.sub(lambda m: "[" + ",".join(x.strip() for x in m.group(1).split(",")) + "]", text)
        + "\n"
    )


def run_publish_occupancy(data_dir: Path, out_dir: Path, *, check: bool = False) -> int:
    try:
        return _run(data_dir, out_dir, check)
    except (FileNotFoundError, duckdb.IOException, ValueError) as error:
        print(f"publish occupancy: {error}")
        return 1


def _run(data_dir: Path, out_dir: Path, check: bool) -> int:
    path = out_dir / OCCUPANCY_JSON
    at_hand = matches_at_hand(data_dir)
    if not check:
        if not at_hand:
            print(
                f"publish occupancy: no football match outside the fence under {silver(data_dir)}"
            )
            return 1
        text = render(build(data_dir, at_hand))
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"publish occupancy: {len(at_hand)} matches, {path} ({path.stat().st_size} bytes)")
        return 0

    if not path.is_file():
        print(f"publish occupancy --check: {path} is missing")
        return 1
    raw = path.read_bytes()
    if b"\r" in raw:
        print(f"publish occupancy --check: {OCCUPANCY_JSON} has CR line ends")
        return 1
    named = [str(m) for m in json.loads(raw.decode("utf-8"))["matches"]]
    fenced = sorted(set(named) & held_out())
    if fenced:
        print(f"publish occupancy --check: {OCCUPANCY_JSON} names held-out matches {fenced}")
        return 1
    have = [m for m in named if m in at_hand]
    if len(have) < len(named):
        # A slice (the CI fixtures): the code runs on it, its figures are not the file's.
        if at_hand:
            slice_ = build(data_dir, at_hand)
            print(
                f"publish occupancy --check: the code ran on {len(at_hand)} match(es) at hand, "
                f"{slice_['groups'][-1]['player_frames']} outfield player-frames, not compared"
            )
        print(
            f"publish occupancy --check: PARTIAL {len(have)}/{len(named)}: "
            f"the matches of {OCCUPANCY_JSON} are not all at hand"
        )
        return 0
    if render(build(data_dir, at_hand)).encode("utf-8") != raw:
        print(f"publish occupancy --check: {OCCUPANCY_JSON} differs from what silver gives")
        return 1
    print(f"publish occupancy --check: FULL {len(named)}/{len(named)}: {OCCUPANCY_JSON} matches")
    return 0
