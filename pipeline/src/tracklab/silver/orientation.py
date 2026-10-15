"""Orientation probe over the bronze artefact: which way each team attacks in each period,
in the two sports, and which court the basketball events are drawn on.

Everything here reads the bronze Parquet with DuckDB (never the raw files), prints its
evidence per match, writes it to ``reports/orientation_*.csv`` (one row per match, per
(match, period, team) group, or per residual shot; never an aggregate), renders the
orientation section of ``docs/decisions.md`` from those rows, and materialises
``bronze.common.orientation`` (``data/bronze/common/orientation/data.parquet``), the
table ``dim_team_period`` (task 10) is built from::

    sport | native_match_id | period | native_team_id | attack_sign | evidence

``attack_sign`` is +1 when the team attacks towards +x of the venue (tracking) frame in
that period, -1 otherwise; ``evidence`` names the provider field the sign comes from
and the counts that back it.

Basketball (tracking and event locations both in feet, as delivered)
- ``attack_sign`` comes from ``possessions.leftHoop`` per (period, offTeamId). Every
  possession of a team in a period must share the value (a mixed period fails the run
  naming file, period, team and the counts; nothing is averaged or voted), the two
  teams with possessions in a period must be the game's home and away, and their
  values must be opposite. ``leftHoop = true`` means the offence attacks the hoop at
  negative x of the venue frame, so ``attack_sign = -1``.
- Shot probe (the sibling repo's ``check_orientation.py``, read from bronze): the
  shooter's tracking position at ``shots.startFrame`` rotated into the attack frame of
  the events (attacked hoop at negative x) against ``shots.location``: ``(x, y)`` when
  ``leftHoop``, ``(-x, -y)`` otherwise; a 180-degree rotation is its own inverse. The
  assertion is binary and per (period, team) group, with no threshold: the rotation
  ``leftHoop`` predicts must be the closer of the two for every matched shot of the
  group, and the opposite rotation must land within 0.5 m (1.6404 ft) of no shot at
  all. A wrong rotation cannot pass that. The share of shots within 0.5 m under the
  rule is published per match as a number, never as a verdict: it mixes a second
  question ("is ``shots.location`` the shooter's position exactly at ``startFrame``?")
  whose answer is "not always", for reasons unrelated to orientation. The shots beyond
  0.5 m are listed one by one with a classification (extrapolated position, or the
  tracking frame at which the declared location is found, or unexplained), and
  ``touches.endLoc`` of the shot's touch is measured against the same tracking
  position so the discrepancy is located.
- Court geometry, FIBA 28 x 15 m against 94 x 50 ft, decided per match on two
  measurements. (1) ``shots.distance`` must equal ``hypot(x - hoop_x, y)`` for the hoop
  of one court and not the other (FIBA: -40.77 ft in the attack frame, NBA: -41.75 ft):
  the maximum residual against each hoop is reported. (2) The three-point radius is
  fitted as the threshold on ``distance`` that best separates ``three`` from two-point
  shots outside the corners (|y| <= 21 ft, under both courts' corner lines); the
  misclassification count at the fitted plateau, at the FIBA radius (22.15 ft) and at
  the NBA radius (23.75 ft) is reported. The extents of ``shots.location`` and
  ``rebounds.location`` are reported next to them.

Football (tracking and events both in metres)
- ``attack_sign`` comes from ``match.home_team_side[period]`` (``left_to_right`` = home
  attacks towards +x) and is crossed with ``phases_of_play.attacking_side`` per
  (period, team): the share of agreeing phases is reported and the bar is 100%.
- Event frame: ``player_possession`` (x_start, y_start) against the tracking position
  of ``player_id`` at ``frame_start`` under two hypotheses, "venue" (the coordinates
  are already in the tracking frame) and "attack" (``(x, y)`` when ``attacking_side`` is
  ``left_to_right``, ``(-x, -y)`` when ``right_to_left``); the share within 1 m of each
  is reported per match and the winner named. The share within 2 m is reported too,
  because that is the tolerance task 4 used. Whether the match's ``players[]`` carry
  ``last_modified`` (task 7's two regimes) is reported in the same row, because the
  two partitions coincide.

The run exits with 1 when the orientation is not consistent (a group where the
opposite rotation lands within 0.5 m of a shot, or where the predicted rotation is not
the closer one for every shot), when the football sides disagree with the phases, or
when the court is undetermined; the artefacts are written regardless, because they
are how the shortfall is reported.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from tracklab.bronze.common import ParquetSink, batch_from_columns, bronze_path
from tracklab.ingest.manifest import Source, load_manifest

Row = dict[str, object]
Log = Callable[[str], None]
XY = tuple[float, float]

SPORTS: tuple[str, ...] = ("basketball", "football")
SOURCE_IDS: dict[str, str] = {
    "basketball": "opendata-basketball",
    "football": "opendata-football",
}
TABLE = "orientation"
DOC_NAME = "decisions.md"
DOC_BELOW = "<!-- tracklab:orientation:generated-below -->"
DOC_ABOVE = "<!-- tracklab:orientation:generated-above -->"
REPORT_NAMES: tuple[str, ...] = (
    "basketball",
    "basketball_groups",
    "basketball_residual_shots",
    "football",
)

M_PER_FT = 0.3048
SHOT_TOL_M = 0.5
SHOT_TOL_FT = SHOT_TOL_M / M_PER_FT  # 1.6404 ft
RESIDUAL_WINDOW_FRAMES = 100  # 4 s at 25 fps, each side of startFrame
EVENT_TOL_M = 1.0
EVENT_TOL_TASK4_M = 2.0
CORNER_MAX_ABS_Y_FT = 21.0  # under both corner lines: FIBA 21.65 ft, NBA 22.0 ft
RADIUS_GRID_FT = (20.0, 25.0, 0.01)
SIDES: tuple[str, ...] = ("left_to_right", "right_to_left")

ORIENTATION_SCHEMA = pa.schema(
    [
        pa.field("sport", pa.string(), nullable=False),
        pa.field("native_match_id", pa.int64(), nullable=False),
        pa.field("period", pa.int16(), nullable=False),
        pa.field("native_team_id", pa.int64(), nullable=False),
        pa.field("attack_sign", pa.int16(), nullable=False),
        pa.field("evidence", pa.string(), nullable=False),
    ]
)


@dataclass(frozen=True)
class Court:
    spec: str
    length_ft: float
    width_ft: float
    hoop_from_baseline_ft: float
    three_radius_ft: float

    @property
    def hoop_x_ft(self) -> float:
        """The attacked hoop in the attack frame of the events (negative x)."""
        return -(self.length_ft / 2 - self.hoop_from_baseline_ft)


FIBA = Court("fiba_28x15", 28 / M_PER_FT, 15 / M_PER_FT, 1.575 / M_PER_FT, 6.75 / M_PER_FT)
NBA = Court("nba_94x50", 94.0, 50.0, 5.25, 23.75)
COURTS = (FIBA, NBA)


@dataclass(frozen=True)
class TeamPeriodSign:
    sport: str
    native_match_id: int
    period: int
    native_team_id: int
    attack_sign: int
    evidence: str


# --- the two rules, each written once ------------------------------------------------


def attack_sign_from_left_hoop(left_hoop: bool) -> int:
    """``leftHoop`` = the offence attacks the hoop at negative x of the venue frame."""
    return -1 if left_hoop else 1


def to_attack_factor(left_hoop: bool) -> int:
    """Factor mapping venue coordinates to the attack frame of the basketball events
    (attacked hoop at negative x): minus the attack sign of the possession."""
    return -attack_sign_from_left_hoop(left_hoop)


def attack_sign_from_side(side: str) -> int:
    """``left_to_right`` = the team attacks towards +x of the venue frame."""
    if side == "left_to_right":
        return 1
    if side == "right_to_left":
        return -1
    raise ValueError(f"unknown attacking side {side!r}, expected one of {SIDES}")


def side_from_attack_sign(sign: int) -> str:
    return "left_to_right" if sign > 0 else "right_to_left"


def _to_venue_sql(side_col: str) -> str:
    """SQL factor mapping football event coordinates (attacker towards +x) to the venue
    frame; NULL for a side outside ``SIDES`` so the row is counted, not guessed."""
    return (
        f"CASE WHEN {side_col} = 'left_to_right' THEN {attack_sign_from_side('left_to_right')} "
        f"WHEN {side_col} = 'right_to_left' THEN {attack_sign_from_side('right_to_left')} END"
    )


# --- helpers ---------------------------------------------------------------------------


def _parquet(data_dir: Path, sport: str, table: str, match_id: int) -> str:
    path = bronze_path(data_dir, sport, table, match_id)
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; run `tracklab bronze {sport}` first")
    return path.as_posix()


def _one(con: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object]) -> tuple[Any, ...]:
    row = con.execute(sql, list(params)).fetchone()
    assert row is not None
    return row


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def _r(value: object, digits: int = 2) -> float:
    return round(float(value), digits)  # type: ignore[arg-type]


def _quantile(values: Sequence[float], q: float) -> float:
    """Linear interpolation between order statistics (DuckDB's ``quantile_cont``)."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = q * (len(ordered) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _rot(f: int, xy: XY) -> XY:
    return (f * xy[0], f * xy[1])


def _dist(a: XY, b: XY) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def match_ids_of(source: Source) -> list[int]:
    """The matches of a source: the ids of its tracking files, in id order."""
    return sorted({f.match_id for f in source.files if f.role == "tracking" and f.match_id})


# --- basketball: the sign -------------------------------------------------------------


@dataclass(frozen=True)
class HoopGroup:
    period: int
    team_id: int
    left_hoop: bool
    possessions: int

    @property
    def attack_sign(self) -> int:
        return attack_sign_from_left_hoop(self.left_hoop)


def left_hoop_groups(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int
) -> list[HoopGroup]:
    """One group per (period, offTeamId) from ``possessions.leftHoop``, imposed: all the
    possessions of a team in a period share it, the two teams with possessions are the
    game's home and away, and they hold opposite values. Anything else fails naming
    the file, the period, the team and the counts."""
    games = _parquet(data_dir, "basketball", "games", match_id)
    possessions = _parquet(data_dir, "basketball", "events_possessions", match_id)
    teams = _one(con, "SELECT homeTeamId, awayTeamId FROM read_parquet(?)", [games])
    home, away = int(teams[0]), int(teams[1])
    rows = con.execute(
        "SELECT period, offTeamId, count(*), count(*) FILTER (WHERE leftHoop) "
        "FROM read_parquet(?) GROUP BY ALL ORDER BY 1, 2",
        [possessions],
    ).fetchall()
    by_period: dict[int, list[HoopGroup]] = {}
    for period, team, n, n_left in rows:
        where = f"{possessions}: period {period} team {team}"
        if team not in (home, away):
            raise ValueError(
                f"{where}: offTeamId is neither home {home} nor away {away} (games.parquet)"
            )
        if n_left not in (0, n):
            raise ValueError(
                f"{where}: leftHoop is true in {n_left} of {n} possessions; every possession "
                "of a team in a period must share it (column leftHoop)"
            )
        by_period.setdefault(int(period), []).append(
            HoopGroup(int(period), int(team), n_left == n, int(n))
        )
    out: list[HoopGroup] = []
    for period, groups in sorted(by_period.items()):
        where = f"{possessions}: period {period}"
        if {g.team_id for g in groups} != {home, away}:
            raise ValueError(
                f"{where}: teams with possessions {sorted(g.team_id for g in groups)}, "
                f"expected home {home} and away {away}"
            )
        if groups[0].left_hoop == groups[1].left_hoop:
            raise ValueError(
                f"{where}: both teams have leftHoop={str(groups[0].left_hoop).lower()}; "
                "expected opposite hoops"
            )
        out.extend(groups)
    return out


def basketball_signs(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int
) -> list[TeamPeriodSign]:
    return [
        TeamPeriodSign(
            "basketball",
            match_id,
            g.period,
            g.team_id,
            g.attack_sign,
            f"possessions.leftHoop={str(g.left_hoop).lower()} in "
            f"{g.possessions}/{g.possessions} possessions",
        )
        for g in left_hoop_groups(con, data_dir, match_id)
    ]


# --- basketball: the shot probe -------------------------------------------------------


@dataclass(frozen=True)
class ShotRow:
    """One row of ``events_shots`` joined to its possession, the shooter's tracking
    position at ``startFrame`` and the ``endLoc`` of its touch. Coordinates in feet."""

    shot_id: str
    period: int
    team_id: int
    start_frame: int
    shooter_id: int
    left_hoop: bool | None
    location: XY | None
    tracking: XY | None
    is_detected: bool | None
    pred_error: float | None
    touch_id: str | None
    touch_end: XY | None

    @property
    def status(self) -> str:
        if self.location is None:
            return "no_location"
        if self.left_hoop is None:
            return "no_possession"
        if self.tracking is None:
            return "no_tracking"
        return "matched"

    @property
    def factor(self) -> int:
        assert self.left_hoop is not None
        return to_attack_factor(self.left_hoop)

    @property
    def d_rule(self) -> float:
        """Distance between the rotated tracking position and ``shots.location``."""
        assert self.location is not None and self.tracking is not None
        return _dist(_rot(self.factor, self.tracking), self.location)

    @property
    def d_flipped(self) -> float:
        """The same under the opposite rotation."""
        assert self.location is not None and self.tracking is not None
        return _dist(_rot(-self.factor, self.tracking), self.location)


def basketball_shot_rows(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int
) -> list[ShotRow]:
    shots = _parquet(data_dir, "basketball", "events_shots", match_id)
    possessions = _parquet(data_dir, "basketball", "events_possessions", match_id)
    tracking = _parquet(data_dir, "basketball", "tracking_objects", match_id)
    touches = _parquet(data_dir, "basketball", "events_touches", match_id)
    (n_shots,) = _one(con, "SELECT count(*) FROM read_parquet(?)", [shots])
    rows = con.execute(
        """
        SELECT s.id, s.period, s.offTeamId, s.startFrame, s.shooterId,
               s.location_x, s.location_y, p.leftHoop, t.x, t.y, t.isDetected, t.predError,
               s.touchId, u.endLoc_x, u.endLoc_y
        FROM read_parquet(?) s
        LEFT JOIN read_parquet(?) p ON p.id = s.possessionId
        LEFT JOIN read_parquet(?) t ON t.frameIdx = s.startFrame AND t.playerId = s.shooterId
        LEFT JOIN read_parquet(?) u ON u.id = s.touchId
        ORDER BY s.startFrame, s.id
        """,
        [shots, possessions, tracking, touches],
    ).fetchall()
    if len(rows) != n_shots:
        raise ValueError(
            f"{shots}: {n_shots} shots but {len(rows)} rows after joining possessions, "
            f"tracking and touches; a key repeats in {possessions} (id), {tracking} "
            "(frameIdx, playerId) or the touches (id)"
        )

    def xy(x: object, y: object) -> XY | None:
        return None if x is None or y is None else (float(x), float(y))  # type: ignore[arg-type]

    return [
        ShotRow(
            shot_id=str(r[0]),
            period=int(r[1]),
            team_id=int(r[2]),
            start_frame=int(r[3]),
            shooter_id=int(r[4]),
            left_hoop=None if r[7] is None else bool(r[7]),
            location=xy(r[5], r[6]),
            tracking=xy(r[8], r[9]),
            is_detected=None if r[10] is None else bool(r[10]),
            pred_error=None if r[11] is None else float(r[11]),
            touch_id=None if r[12] is None else str(r[12]),
            touch_end=xy(r[13], r[14]),
        )
        for r in rows
    ]


@dataclass(frozen=True)
class GroupProbe:
    """The shot probe of one (period, team) group: binary, no threshold."""

    period: int
    team_id: int
    left_hoop: bool
    possessions: int
    matched: int
    rule_closer: int
    within: int
    within_flipped: int
    median_ft: float

    @property
    def attack_sign(self) -> int:
        return attack_sign_from_left_hoop(self.left_hoop)

    @property
    def verdict(self) -> str:
        if self.matched == 0:
            return "no_shots"
        if self.within_flipped == 0 and self.rule_closer == self.matched:
            return "ok"
        return "FAIL"


@dataclass(frozen=True)
class ResidualShot:
    """A matched shot whose declared location is more than 0.5 m from the rotated
    shooter position at ``startFrame``, with where the location is found instead."""

    shot_id: str
    period: int
    team_id: int
    start_frame: int
    shooter_id: int
    d_rule_ft: float
    is_detected: bool
    pred_error_ft: float
    frame_offset: int | None
    d_at_offset_ft: float | None
    touch_id: str | None
    touch_endloc_to_tracking_ft: float | None
    touch_endloc_to_location_ft: float | None

    @property
    def kind(self) -> str:
        if not self.is_detected:
            return "extrapolated"
        if self.d_at_offset_ft is not None and self.d_at_offset_ft <= SHOT_TOL_FT:
            return "time_offset"
        return "unexplained"


@dataclass(frozen=True)
class ShotProbe:
    shots: int
    no_location: int
    no_possession: int
    no_tracking: int
    matched: int
    rule_closer: int
    within: int
    within_flipped: int
    median_ft: float
    p95_ft: float
    max_ft: float
    shots_with_touch: int
    touch_within: int
    groups: tuple[GroupProbe, ...]
    residuals: tuple[ResidualShot, ...]

    @property
    def within_pct(self) -> float:
        return _pct(self.within, self.matched)

    @property
    def within_flipped_pct(self) -> float:
        return _pct(self.within_flipped, self.matched)

    @property
    def touch_within_pct(self) -> float:
        return _pct(self.touch_within, self.shots_with_touch)

    @property
    def groups_ok(self) -> int:
        return sum(1 for g in self.groups if g.verdict == "ok")

    @property
    def orientation_check(self) -> str:
        return "FAIL" if any(g.verdict == "FAIL" for g in self.groups) else "ok"

    def residual_count(self, kind: str) -> int:
        return sum(1 for r in self.residuals if r.kind == kind)


def _closest_frame(
    con: duckdb.DuckDBPyConnection, tracking: str, row: ShotRow
) -> tuple[int, float] | None:
    """The frame of closest approach: among the shooter's tracking frames other than
    ``startFrame`` and within ``RESIDUAL_WINDOW_FRAMES`` of it, the one whose rotated
    position is nearest to the declared location, as (offset, distance in ft); the
    closest in time wins a tie, earlier first. None when the window holds no frame."""
    assert row.location is not None
    lx, ly = row.location
    f = row.factor
    found = con.execute(
        """
        SELECT frameIdx - ? AS frame_offset, sqrt((? * x - ?)^2 + (? * y - ?)^2) AS d
        FROM read_parquet(?)
        WHERE playerId = ? AND frameIdx BETWEEN ? AND ? AND frameIdx != ?
        ORDER BY d, abs(frame_offset), frame_offset LIMIT 1
        """,
        [
            row.start_frame,
            f,
            lx,
            f,
            ly,
            tracking,
            row.shooter_id,
            row.start_frame - RESIDUAL_WINDOW_FRAMES,
            row.start_frame + RESIDUAL_WINDOW_FRAMES,
            row.start_frame,
        ],
    ).fetchone()
    return None if found is None else (int(found[0]), float(found[1]))


def basketball_shot_probe(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int
) -> ShotProbe:
    """The shooter's tracking position at ``startFrame``, rotated by the possession's
    ``leftHoop``, against ``shots.location``; feet on both sides. Per group: is the
    predicted rotation the closer one for every shot, and does the opposite land
    within 0.5 m of none? Per match: the share within 0.5 m, as a number."""
    tracking = _parquet(data_dir, "basketball", "tracking_objects", match_id)
    rows = basketball_shot_rows(con, data_dir, match_id)
    matched = [r for r in rows if r.status == "matched"]
    d_rule = [r.d_rule for r in matched]

    groups: list[GroupProbe] = []
    for g in left_hoop_groups(con, data_dir, match_id):
        own = [r for r in matched if r.period == g.period and r.team_id == g.team_id]
        groups.append(
            GroupProbe(
                period=g.period,
                team_id=g.team_id,
                left_hoop=g.left_hoop,
                possessions=g.possessions,
                matched=len(own),
                rule_closer=sum(1 for r in own if r.d_rule < r.d_flipped),
                within=sum(1 for r in own if r.d_rule <= SHOT_TOL_FT),
                within_flipped=sum(1 for r in own if r.d_flipped <= SHOT_TOL_FT),
                median_ft=_quantile([r.d_rule for r in own], 0.5),
            )
        )
    stray = {(r.period, r.team_id) for r in matched} - {(g.period, g.team_id) for g in groups}
    if stray:
        raise ValueError(
            f"{_parquet(data_dir, 'basketball', 'events_shots', match_id)}: shots of "
            f"(period, offTeamId) {sorted(stray)} without a possession group of that team"
        )

    residuals: list[ResidualShot] = []
    for r in matched:
        if r.d_rule <= SHOT_TOL_FT:
            continue
        assert r.tracking is not None and r.location is not None
        near = _closest_frame(con, tracking, r)
        rotated = _rot(r.factor, r.tracking)
        residuals.append(
            ResidualShot(
                shot_id=r.shot_id,
                period=r.period,
                team_id=r.team_id,
                start_frame=r.start_frame,
                shooter_id=r.shooter_id,
                d_rule_ft=r.d_rule,
                is_detected=bool(r.is_detected),
                pred_error_ft=float(r.pred_error or 0.0),
                frame_offset=None if near is None else near[0],
                d_at_offset_ft=None if near is None else near[1],
                touch_id=r.touch_id,
                touch_endloc_to_tracking_ft=(
                    None if r.touch_end is None else _dist(r.touch_end, rotated)
                ),
                touch_endloc_to_location_ft=(
                    None if r.touch_end is None else _dist(r.touch_end, r.location)
                ),
            )
        )

    with_touch = [r for r in matched if r.touch_end is not None]
    return ShotProbe(
        shots=len(rows),
        no_location=sum(1 for r in rows if r.status == "no_location"),
        no_possession=sum(1 for r in rows if r.status == "no_possession"),
        no_tracking=sum(1 for r in rows if r.status == "no_tracking"),
        matched=len(matched),
        rule_closer=sum(1 for r in matched if r.d_rule < r.d_flipped),
        within=sum(1 for d in d_rule if d <= SHOT_TOL_FT),
        within_flipped=sum(1 for r in matched if r.d_flipped <= SHOT_TOL_FT),
        median_ft=_quantile(d_rule, 0.5),
        p95_ft=_quantile(d_rule, 0.95),
        max_ft=max(d_rule, default=0.0),
        shots_with_touch=len(with_touch),
        touch_within=sum(
            1
            for r in with_touch
            if r.touch_end is not None
            and r.tracking is not None
            and _dist(r.touch_end, _rot(r.factor, r.tracking)) <= SHOT_TOL_FT
        ),
        groups=tuple(groups),
        residuals=tuple(residuals),
    )


# --- basketball: the court ------------------------------------------------------------


@dataclass(frozen=True)
class RadiusFit:
    n: int
    three_min_ft: float | None
    two_max_ft: float | None
    plateau_lo_ft: float
    plateau_hi_ft: float
    misclassified: int
    misclassified_fiba: int
    misclassified_nba: int

    @property
    def court(self) -> str:
        """The court whose radius misclassifies fewer shots; a tie decides nothing."""
        if self.misclassified_fiba < self.misclassified_nba:
            return FIBA.spec
        if self.misclassified_nba < self.misclassified_fiba:
            return NBA.spec
        return "tie"


def _misclassified(shots: Sequence[tuple[float, bool]], radius: float) -> int:
    return sum((d >= radius) != three for d, three in shots)


def fit_three_radius(shots: Sequence[tuple[float, bool]]) -> RadiusFit:
    """The radius r (grid of 0.01 ft) minimising the shots on the wrong side of
    ``distance >= r`` against the provider's ``three`` flag; reported as the plateau
    of radii sharing the minimum, never as a single made-up number."""
    lo, hi, step = RADIUS_GRID_FT
    grid = [round(lo + i * step, 2) for i in range(round((hi - lo) / step) + 1)]
    counts = [(r, _misclassified(shots, r)) for r in grid]
    best = min(m for _, m in counts)
    plateau = [r for r, m in counts if m == best]
    threes = [d for d, t in shots if t]
    twos = [d for d, t in shots if not t]
    return RadiusFit(
        n=len(shots),
        three_min_ft=min(threes) if threes else None,
        two_max_ft=max(twos) if twos else None,
        plateau_lo_ft=plateau[0],
        plateau_hi_ft=plateau[-1],
        misclassified=best,
        misclassified_fiba=_misclassified(shots, FIBA.three_radius_ft),
        misclassified_nba=_misclassified(shots, NBA.three_radius_ft),
    )


@dataclass(frozen=True)
class Geometry:
    shots_with_location: int
    shots_with_distance: int
    hoop_x_median_ft: float
    dist_resid_max_fiba_ft: float
    dist_resid_max_nba_ft: float
    shots_x_min_ft: float
    shots_x_max_ft: float
    shots_y_min_ft: float
    shots_y_max_ft: float
    rebounds: int
    rebounds_with_location: int
    rebounds_x_min_ft: float
    rebounds_x_max_ft: float
    rebounds_y_min_ft: float
    rebounds_y_max_ft: float
    fit: RadiusFit

    @property
    def hoop_court(self) -> str:
        """The court whose hoop reproduces ``shots.distance`` better; a tie decides nothing."""
        if self.dist_resid_max_fiba_ft < self.dist_resid_max_nba_ft:
            return FIBA.spec
        if self.dist_resid_max_nba_ft < self.dist_resid_max_fiba_ft:
            return NBA.spec
        return "tie"

    @property
    def court(self) -> str:
        return self.hoop_court if self.hoop_court == self.fit.court else "undetermined"


def basketball_geometry(con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int) -> Geometry:
    shots = _parquet(data_dir, "basketball", "events_shots", match_id)
    rebounds = _parquet(data_dir, "basketball", "events_rebounds", match_id)
    s = _one(
        con,
        """
        SELECT count(*) FILTER (WHERE location_x IS NOT NULL AND location_y IS NOT NULL),
               count(*) FILTER (WHERE location_x IS NOT NULL AND distance IS NOT NULL),
               coalesce(median(location_x - sqrt(distance * distance - location_y * location_y))
                 FILTER (WHERE distance >= abs(location_y)), 0),
               coalesce(max(abs(sqrt((location_x - ?)^2 + location_y^2) - distance)), 0),
               coalesce(max(abs(sqrt((location_x - ?)^2 + location_y^2) - distance)), 0),
               coalesce(min(location_x), 0), coalesce(max(location_x), 0),
               coalesce(min(location_y), 0), coalesce(max(location_y), 0)
        FROM read_parquet(?)
        """,
        [FIBA.hoop_x_ft, NBA.hoop_x_ft, shots],
    )
    fit_rows = con.execute(
        "SELECT distance, three FROM read_parquet(?) "
        "WHERE location_x IS NOT NULL AND distance IS NOT NULL AND location_x <= 0 "
        "AND abs(location_y) <= ?",
        [shots, CORNER_MAX_ABS_Y_FT],
    ).fetchall()
    r = _one(
        con,
        """
        SELECT count(*), count(*) FILTER (WHERE location_x IS NOT NULL),
               coalesce(min(location_x), 0), coalesce(max(location_x), 0),
               coalesce(min(location_y), 0), coalesce(max(location_y), 0)
        FROM read_parquet(?)
        """,
        [rebounds],
    )
    return Geometry(
        shots_with_location=int(s[0]),
        shots_with_distance=int(s[1]),
        hoop_x_median_ft=float(s[2]),
        dist_resid_max_fiba_ft=float(s[3]),
        dist_resid_max_nba_ft=float(s[4]),
        shots_x_min_ft=float(s[5]),
        shots_x_max_ft=float(s[6]),
        shots_y_min_ft=float(s[7]),
        shots_y_max_ft=float(s[8]),
        rebounds=int(r[0]),
        rebounds_with_location=int(r[1]),
        rebounds_x_min_ft=float(r[2]),
        rebounds_x_max_ft=float(r[3]),
        rebounds_y_min_ft=float(r[4]),
        rebounds_y_max_ft=float(r[5]),
        fit=fit_three_radius([(float(d), bool(t)) for d, t in fit_rows]),
    )


BASKETBALL_COLUMNS: tuple[str, ...] = (
    "match_id",
    "home_team_id",
    "away_team_id",
    "periods",
    "possessions",
    "left_hoop_consensus",
    "groups",
    "groups_ok",
    "groups_no_shots",
    "orientation_check",
    "shots",
    "shots_no_location",
    "shots_no_possession",
    "shots_no_tracking",
    "shots_matched",
    "shots_rule_closer",
    "shots_within_0_5m",
    "shots_within_0_5m_pct",
    "shots_within_0_5m_flipped",
    "shots_within_0_5m_flipped_pct",
    "shot_median_ft",
    "shot_p95_ft",
    "shot_max_ft",
    "shots_residual",
    "shots_residual_extrapolated",
    "shots_residual_time_offset",
    "shots_residual_unexplained",
    "shots_with_touch",
    "touch_endloc_within_0_5m",
    "touch_endloc_within_0_5m_pct",
    "shots_with_distance",
    "hoop_x_median_ft",
    "dist_resid_max_fiba_ft",
    "dist_resid_max_nba_ft",
    "hoop_court",
    "radius_n",
    "radius_three_min_ft",
    "radius_two_max_ft",
    "radius_plateau_lo_ft",
    "radius_plateau_hi_ft",
    "radius_misclassified",
    "radius_misclassified_fiba",
    "radius_misclassified_nba",
    "radius_court",
    "court",
    "shots_x_min_ft",
    "shots_x_max_ft",
    "shots_y_min_ft",
    "shots_y_max_ft",
    "rebounds",
    "rebounds_with_location",
    "rebounds_x_min_ft",
    "rebounds_x_max_ft",
    "rebounds_y_min_ft",
    "rebounds_y_max_ft",
)

GROUP_COLUMNS: tuple[str, ...] = (
    "match_id",
    "period",
    "team_id",
    "left_hoop",
    "attack_sign",
    "possessions",
    "shots_matched",
    "shots_rule_closer",
    "shots_within_0_5m",
    "shots_within_0_5m_flipped",
    "shot_median_ft",
    "verdict",
)

RESIDUAL_COLUMNS: tuple[str, ...] = (
    "match_id",
    "shot_id",
    "period",
    "team_id",
    "start_frame",
    "shooter_id",
    "d_rule_ft",
    "is_detected",
    "pred_error_ft",
    "kind",
    "frame_offset",
    "d_at_offset_ft",
    "touch_id",
    "touch_endloc_to_tracking_ft",
    "touch_endloc_to_location_ft",
)


@dataclass(frozen=True)
class BasketballReports:
    matches: list[Row]
    groups: list[Row]
    residuals: list[Row]
    signs: list[TeamPeriodSign]


def _opt(value: float | None, digits: int = 3) -> object:
    return "" if value is None else _r(value, digits)


def probe_basketball(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_ids: Sequence[int], log: Log
) -> BasketballReports:
    out = BasketballReports([], [], [], [])
    for match_id in match_ids:
        probe = basketball_shot_probe(con, data_dir, match_id)
        geom = basketball_geometry(con, data_dir, match_id)
        fit = geom.fit
        by_group = {(g.period, g.team_id): g for g in probe.groups}
        for sign in basketball_signs(con, data_dir, match_id):
            g = by_group[(sign.period, sign.native_team_id)]
            out.signs.append(
                replace(
                    sign,
                    evidence=(
                        f"{sign.evidence}; shots closer under this rotation "
                        f"{g.rule_closer}/{g.matched}, opposite rotation within 0.5 m "
                        f"{g.within_flipped}"
                    ),
                )
            )
        for g in probe.groups:
            out.groups.append(
                {
                    "match_id": match_id,
                    "period": g.period,
                    "team_id": g.team_id,
                    "left_hoop": str(g.left_hoop).lower(),
                    "attack_sign": g.attack_sign,
                    "possessions": g.possessions,
                    "shots_matched": g.matched,
                    "shots_rule_closer": g.rule_closer,
                    "shots_within_0_5m": g.within,
                    "shots_within_0_5m_flipped": g.within_flipped,
                    "shot_median_ft": _r(g.median_ft, 3),
                    "verdict": g.verdict,
                }
            )
        for res in probe.residuals:
            out.residuals.append(
                {
                    "match_id": match_id,
                    "shot_id": res.shot_id,
                    "period": res.period,
                    "team_id": res.team_id,
                    "start_frame": res.start_frame,
                    "shooter_id": res.shooter_id,
                    "d_rule_ft": _r(res.d_rule_ft, 3),
                    "is_detected": str(res.is_detected).lower(),
                    "pred_error_ft": _r(res.pred_error_ft),
                    "kind": res.kind,
                    "frame_offset": "" if res.frame_offset is None else res.frame_offset,
                    "d_at_offset_ft": _opt(res.d_at_offset_ft),
                    "touch_id": res.touch_id or "",
                    "touch_endloc_to_tracking_ft": _opt(res.touch_endloc_to_tracking_ft),
                    "touch_endloc_to_location_ft": _opt(res.touch_endloc_to_location_ft),
                }
            )
        home, away = _one(
            con,
            "SELECT homeTeamId, awayTeamId FROM read_parquet(?)",
            [_parquet(data_dir, "basketball", "games", match_id)],
        )
        row: Row = {
            "match_id": match_id,
            "home_team_id": int(home),
            "away_team_id": int(away),
            "periods": max(g.period for g in probe.groups),
            "possessions": sum(g.possessions for g in probe.groups),
            "left_hoop_consensus": "ok",
            "groups": len(probe.groups),
            "groups_ok": probe.groups_ok,
            "groups_no_shots": sum(1 for g in probe.groups if g.verdict == "no_shots"),
            "orientation_check": probe.orientation_check,
            "shots": probe.shots,
            "shots_no_location": probe.no_location,
            "shots_no_possession": probe.no_possession,
            "shots_no_tracking": probe.no_tracking,
            "shots_matched": probe.matched,
            "shots_rule_closer": probe.rule_closer,
            "shots_within_0_5m": probe.within,
            "shots_within_0_5m_pct": probe.within_pct,
            "shots_within_0_5m_flipped": probe.within_flipped,
            "shots_within_0_5m_flipped_pct": probe.within_flipped_pct,
            "shot_median_ft": _r(probe.median_ft, 3),
            "shot_p95_ft": _r(probe.p95_ft, 3),
            "shot_max_ft": _r(probe.max_ft, 3),
            "shots_residual": len(probe.residuals),
            "shots_residual_extrapolated": probe.residual_count("extrapolated"),
            "shots_residual_time_offset": probe.residual_count("time_offset"),
            "shots_residual_unexplained": probe.residual_count("unexplained"),
            "shots_with_touch": probe.shots_with_touch,
            "touch_endloc_within_0_5m": probe.touch_within,
            "touch_endloc_within_0_5m_pct": probe.touch_within_pct,
            "shots_with_distance": geom.shots_with_distance,
            "hoop_x_median_ft": _r(geom.hoop_x_median_ft, 3),
            "dist_resid_max_fiba_ft": _r(geom.dist_resid_max_fiba_ft, 3),
            "dist_resid_max_nba_ft": _r(geom.dist_resid_max_nba_ft, 3),
            "hoop_court": geom.hoop_court,
            "radius_n": fit.n,
            "radius_three_min_ft": _opt(fit.three_min_ft),
            "radius_two_max_ft": _opt(fit.two_max_ft),
            "radius_plateau_lo_ft": fit.plateau_lo_ft,
            "radius_plateau_hi_ft": fit.plateau_hi_ft,
            "radius_misclassified": fit.misclassified,
            "radius_misclassified_fiba": fit.misclassified_fiba,
            "radius_misclassified_nba": fit.misclassified_nba,
            "radius_court": fit.court,
            "court": geom.court,
            "shots_x_min_ft": _r(geom.shots_x_min_ft),
            "shots_x_max_ft": _r(geom.shots_x_max_ft),
            "shots_y_min_ft": _r(geom.shots_y_min_ft),
            "shots_y_max_ft": _r(geom.shots_y_max_ft),
            "rebounds": geom.rebounds,
            "rebounds_with_location": geom.rebounds_with_location,
            "rebounds_x_min_ft": _r(geom.rebounds_x_min_ft),
            "rebounds_x_max_ft": _r(geom.rebounds_x_max_ft),
            "rebounds_y_min_ft": _r(geom.rebounds_y_min_ft),
            "rebounds_y_max_ft": _r(geom.rebounds_y_max_ft),
        }
        out.matches.append(row)
        log(
            f"basketball {match_id}: periods={row['periods']} possessions={row['possessions']} "
            f"leftHoop=ok groups={len(probe.groups)} ok={probe.groups_ok} "
            f"no_shots={row['groups_no_shots']} -> {probe.orientation_check}; "
            f"shots={probe.shots} matched={probe.matched} rule_closer={probe.rule_closer} "
            f"within_0.5m={probe.within} ({probe.within_pct}%) "
            f"flipped_within={probe.within_flipped} median={row['shot_median_ft']}ft "
            f"p95={row['shot_p95_ft']}ft max={row['shot_max_ft']}ft "
            f"residual={len(probe.residuals)} (extrapolated="
            f"{row['shots_residual_extrapolated']} time_offset="
            f"{row['shots_residual_time_offset']} unexplained="
            f"{row['shots_residual_unexplained']}) touch_endloc_within="
            f"{probe.touch_within}/{probe.shots_with_touch} ({probe.touch_within_pct}%)"
        )
        for res in probe.residuals:
            log(
                f"  residual {res.shot_id}: p{res.period} frame={res.start_frame} "
                f"shooter={res.shooter_id} d={res.d_rule_ft:.3f}ft "
                f"detected={str(res.is_detected).lower()} predError={res.pred_error_ft:.2f} "
                f"kind={res.kind} offset={res.frame_offset} "
                f"touch_endloc_to_tracking={_opt(res.touch_endloc_to_tracking_ft)}"
            )
        log(
            f"basketball {match_id}: hoop_x={row['hoop_x_median_ft']}ft "
            f"resid_fiba={row['dist_resid_max_fiba_ft']}ft "
            f"resid_nba={row['dist_resid_max_nba_ft']}ft "
            f"radius_plateau=[{fit.plateau_lo_ft},{fit.plateau_hi_ft}]ft "
            f"three_min={row['radius_three_min_ft']} two_max={row['radius_two_max_ft']} "
            f"misclassified fit={fit.misclassified} fiba={fit.misclassified_fiba} "
            f"nba={fit.misclassified_nba} (n={fit.n}) "
            f"shots x=[{row['shots_x_min_ft']},{row['shots_x_max_ft']}] "
            f"y=[{row['shots_y_min_ft']},{row['shots_y_max_ft']}] "
            f"rebounds x=[{row['rebounds_x_min_ft']},{row['rebounds_x_max_ft']}] "
            f"y=[{row['rebounds_y_min_ft']},{row['rebounds_y_max_ft']}] -> {geom.court}"
        )
    return out


def decide_court(rows: Sequence[Row]) -> str:
    """The court every match agrees on, or ``undetermined``."""
    verdicts = {str(r["court"]) for r in rows}
    return verdicts.pop() if len(verdicts) == 1 else "undetermined"


# --- football --------------------------------------------------------------------------


def football_signs(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int
) -> tuple[list[TeamPeriodSign], int, int]:
    """One sign per (period, team) from ``match.home_team_side``, crossed with the
    phases: returns the signs plus (agreeing phases, phases). A team or side value
    outside the match's vocabulary fails naming the file, period and team."""
    match = _parquet(data_dir, "football", "match", match_id)
    periods = _parquet(data_dir, "football", "match_periods", match_id)
    phases = _parquet(data_dir, "football", "phases_of_play", match_id)
    m = _one(con, "SELECT home_team_id, away_team_id, home_team_side FROM read_parquet(?)", [match])
    home, away, sides = int(m[0]), int(m[1]), [str(s) for s in m[2]]
    (n_periods,) = _one(con, "SELECT count(*) FROM read_parquet(?)", [periods])
    if len(sides) != n_periods:
        raise ValueError(
            f"{match}: home_team_side has {len(sides)} entries but match_periods has "
            f"{n_periods} rows"
        )
    for i, side in enumerate(sides, start=1):
        if side not in SIDES:
            raise ValueError(f"{match}: home_team_side[{i}] = {side!r}, expected one of {SIDES}")
    counts: dict[tuple[int, int], dict[str, int]] = {}
    for period, team, side, n in con.execute(
        "SELECT period, team_in_possession_id, attacking_side, count(*) "
        "FROM read_parquet(?) GROUP BY ALL",
        [phases],
    ).fetchall():
        where = f"{phases}: period {period} team {team}"
        if team not in (home, away):
            raise ValueError(
                f"{where}: team_in_possession_id is neither home {home} nor away {away}"
            )
        if side not in SIDES:
            raise ValueError(f"{where}: attacking_side {side!r}, expected one of {SIDES}")
        if not 1 <= period <= n_periods:
            raise ValueError(f"{where}: period outside match_periods (1..{n_periods})")
        counts.setdefault((int(period), int(team)), {})[str(side)] = int(n)
    out: list[TeamPeriodSign] = []
    agree = total = 0
    for period, home_side in enumerate(sides, start=1):
        home_sign = attack_sign_from_side(home_side)
        for label, team, sign in (("home", home, home_sign), ("away", away, -home_sign)):
            expected = side_from_attack_sign(sign)
            c = counts.get((period, team), {})
            n_ok, n_all = c.get(expected, 0), sum(c.values())
            agree += n_ok
            total += n_all
            out.append(
                TeamPeriodSign(
                    "football",
                    match_id,
                    period,
                    team,
                    sign,
                    f"match.home_team_side[{period}]={home_side} ({label}); "
                    f"phases_of_play.attacking_side={expected} in {n_ok}/{n_all} phases",
                )
            )
    return out, agree, total


@dataclass(frozen=True)
class EventProbe:
    events: int
    no_xy: int
    no_tracking: int
    matched: int
    venue_within: int
    attack_within: int
    attack_within_task4: int
    attack_median_m: float
    attack_p95_m: float
    attack_max_m: float

    @property
    def venue_pct(self) -> float:
        return _pct(self.venue_within, self.matched)

    @property
    def attack_pct(self) -> float:
        return _pct(self.attack_within, self.matched)

    @property
    def attack_task4_pct(self) -> float:
        return _pct(self.attack_within_task4, self.matched)

    @property
    def winner(self) -> str:
        if self.attack_within > self.venue_within:
            return "attack"
        if self.venue_within > self.attack_within:
            return "venue"
        return "tie"


def football_event_probe(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_id: int
) -> EventProbe:
    """``player_possession`` (x_start, y_start) against the tracking position of the
    player at ``frame_start``, under the venue and the attack hypotheses; metres."""
    events = _parquet(data_dir, "football", "dynamic_events", match_id)
    tracking = _parquet(data_dir, "football", "tracking_objects", match_id)
    row = _one(
        con,
        f"""
        WITH e AS (
          SELECT player_id, frame_start, x_start, y_start,
                 {_to_venue_sql("attacking_side")} AS f
          FROM read_parquet(?) WHERE event_type = 'player_possession'
        ), j AS (
          SELECT e.*, t.x AS tx, t.y AS ty
          FROM e LEFT JOIN read_parquet(?) t
            ON t.frame = e.frame_start AND t.player_id = e.player_id
        ), d AS (
          SELECT *,
                 sqrt((x_start - tx)^2 + (y_start - ty)^2) AS d_venue,
                 sqrt((f * x_start - tx)^2 + (f * y_start - ty)^2) AS d_attack
          FROM j
        )
        SELECT count(*),
               count(*) FILTER (WHERE f IS NULL),
               count(*) FILTER (WHERE x_start IS NULL OR y_start IS NULL),
               count(*) FILTER (WHERE f IS NOT NULL AND x_start IS NOT NULL
                                  AND y_start IS NOT NULL AND tx IS NULL),
               count(d_attack),
               count(*) FILTER (WHERE d_venue <= ?),
               count(*) FILTER (WHERE d_attack <= ?),
               count(*) FILTER (WHERE d_attack <= ?),
               coalesce(median(d_attack), 0),
               coalesce(quantile_cont(d_attack, 0.95), 0),
               coalesce(max(d_attack), 0)
        FROM d
        """,
        [events, tracking, EVENT_TOL_M, EVENT_TOL_M, EVENT_TOL_TASK4_M],
    )
    n, bad_side, no_xy, no_tracking, matched = (int(v) for v in row[:5])
    if bad_side:
        raise ValueError(
            f"{events}: {bad_side} player_possession rows with attacking_side outside {SIDES}"
        )
    if matched + no_xy + no_tracking != n:
        raise ValueError(
            f"{events}: {n} player_possession rows but {matched} matched + {no_xy} without "
            f"x_start/y_start + {no_tracking} without tracking; a player appears more than "
            f"once in a frame of {tracking} (columns frame, player_id)"
        )
    return EventProbe(
        n, no_xy, no_tracking, matched, *(int(v) for v in row[5:8]), *(float(v) for v in row[8:])
    )


FOOTBALL_COLUMNS: tuple[str, ...] = (
    "match_id",
    "home_team_id",
    "away_team_id",
    "home_team_side",
    "periods",
    "phases",
    "phases_agree",
    "phases_agree_pct",
    "side_check",
    "pp_events",
    "pp_no_xy",
    "pp_no_tracking",
    "pp_matched",
    "venue_within_1m_pct",
    "attack_within_1m_pct",
    "attack_within_2m_pct",
    "attack_median_m",
    "attack_p95_m",
    "attack_max_m",
    "event_frame",
    "players_last_modified",
)


def probe_football(
    con: duckdb.DuckDBPyConnection, data_dir: Path, match_ids: Sequence[int], log: Log
) -> tuple[list[Row], list[TeamPeriodSign]]:
    rows: list[Row] = []
    signs: list[TeamPeriodSign] = []
    for match_id in match_ids:
        match_signs, agree, total = football_signs(con, data_dir, match_id)
        signs.extend(match_signs)
        probe = football_event_probe(con, data_dir, match_id)
        home, away, sides = _one(
            con,
            "SELECT home_team_id, away_team_id, home_team_side FROM read_parquet(?)",
            [_parquet(data_dir, "football", "match", match_id)],
        )
        (n_last_modified,) = _one(
            con,
            "SELECT count(last_modified) FROM read_parquet(?)",
            [_parquet(data_dir, "football", "match_players", match_id)],
        )
        side_check = "ok" if total and agree == total else "FAIL"
        row: Row = {
            "match_id": match_id,
            "home_team_id": int(home),
            "away_team_id": int(away),
            "home_team_side": ";".join(str(s) for s in sides),
            "periods": len(sides),
            "phases": total,
            "phases_agree": agree,
            "phases_agree_pct": _pct(agree, total),
            "side_check": side_check,
            "pp_events": probe.events,
            "pp_no_xy": probe.no_xy,
            "pp_no_tracking": probe.no_tracking,
            "pp_matched": probe.matched,
            "venue_within_1m_pct": probe.venue_pct,
            "attack_within_1m_pct": probe.attack_pct,
            "attack_within_2m_pct": probe.attack_task4_pct,
            "attack_median_m": _r(probe.attack_median_m, 3),
            "attack_p95_m": _r(probe.attack_p95_m, 3),
            "attack_max_m": _r(probe.attack_max_m, 3),
            "event_frame": probe.winner,
            "players_last_modified": "yes" if n_last_modified else "no",
        }
        rows.append(row)
        log(
            f"football {match_id}: home_team_side={row['home_team_side']} "
            f"phases_agree={agree}/{total} ({row['phases_agree_pct']}%) -> {side_check}; "
            f"player_possession={probe.events} matched={probe.matched} "
            f"venue_1m={probe.venue_pct}% attack_1m={probe.attack_pct}% "
            f"attack_2m={probe.attack_task4_pct}% median={row['attack_median_m']}m "
            f"p95={row['attack_p95_m']}m max={row['attack_max_m']}m -> {probe.winner} "
            f"(players.last_modified={row['players_last_modified']})"
        )
    return rows, signs


# --- artefacts -------------------------------------------------------------------------


def report_path(reports_dir: Path, name: str) -> Path:
    return reports_dir / f"orientation_{name}.csv"


def write_report_csv(rows: Sequence[Row], path: Path, columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_report(path: Path) -> list[Row]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def orientation_path(data_dir: Path) -> Path:
    return data_dir / "bronze" / "common" / TABLE / "data.parquet"


def write_orientation_table(
    path: Path, signs: Sequence[TeamPeriodSign], sports: Sequence[str], metadata: dict[str, str]
) -> int:
    """Writes the rows of ``sports`` and keeps the other sports' rows already in the
    file, so ``--sport football`` never drops basketball. Returns the row count."""
    kept: list[TeamPeriodSign] = []
    if path.is_file():
        kept = [
            TeamPeriodSign(**r) for r in pq.read_table(path).to_pylist() if r["sport"] not in sports
        ]
    rows = sorted(
        [*kept, *signs],
        key=lambda s: (s.sport, s.native_match_id, s.period, s.native_team_id),
    )
    columns: dict[str, Any] = {
        name: [getattr(s, name) for s in rows] for name in ORIENTATION_SCHEMA.names
    }
    batch = batch_from_columns(ORIENTATION_SCHEMA, columns, len(rows))
    with ParquetSink(path, ORIENTATION_SCHEMA, metadata) as sink:
        sink.write(batch)
    return sink.rows


def merge_doc(existing: str | None, section: str) -> str:
    """Replaces what lies between ``DOC_BELOW`` and ``DOC_ABOVE`` (or appends the
    section when the markers are absent), never touching the rest of the file. A
    missing file gets a bare title so the doc stands on its own."""
    block = f"{DOC_BELOW}\n\n{section.rstrip(chr(10))}\n\n{DOC_ABOVE}\n"
    if existing is None:
        head = (
            "# Decisions\n\nEach decision of the silver schema with the evidence that "
            "supports it. Sections between `<!-- tracklab:...:generated-below -->` and "
            "`...-above -->` markers are rewritten by the named command on every run; "
            "everything else is hand-written.\n"
        )
        return head + "\n" + block
    start, end = existing.find(DOC_BELOW), existing.find(DOC_ABOVE)
    if start == -1 or end == -1 or end < start:
        return existing.rstrip("\n") + "\n\n" + block
    tail = existing[end + len(DOC_ABOVE) :].lstrip("\n")
    return existing[:start] + block + ("\n" + tail if tail else "")


def _md_table(rows: Sequence[Row], columns: Sequence[str]) -> str:
    head = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(str(r[c]) for c in columns) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def _span(rows: Sequence[Row], column: str) -> str:
    values = [float(str(r[column])) for r in rows if str(r[column]) != ""]
    if not values:
        return "n/a"
    lo, hi = min(values), max(values)
    return f"{lo:g}" if lo == hi else f"{lo:g} to {hi:g}"


def _total(rows: Sequence[Row], column: str) -> int:
    return sum(int(str(r[column])) for r in rows)


def _render_basketball(
    matches: Sequence[Row], groups: Sequence[Row], residuals: Sequence[Row]
) -> str:
    n = len(matches)
    ok = [g for g in groups if g["verdict"] == "ok"]
    no_shots = [g for g in groups if g["verdict"] == "no_shots"]
    failing = [
        f"{g['match_id']} p{g['period']} team {g['team_id']}"
        for g in groups
        if g["verdict"] == "FAIL"
    ]
    matched, closer, flipped = (
        _total(groups, "shots_matched"),
        _total(groups, "shots_rule_closer"),
        _total(groups, "shots_within_0_5m_flipped"),
    )
    court = decide_court(matches)
    extrapolated = [r for r in residuals if r["kind"] == "extrapolated"]
    offsets = sorted(int(str(r["frame_offset"])) for r in residuals if r["kind"] == "time_offset")
    unexplained = [r for r in residuals if r["kind"] == "unexplained"]
    with_touch = [r for r in residuals if str(r["touch_id"]) != ""]
    parts = [
        "### Basketball: `possessions.leftHoop` gives the sign, the shot probe corroborates it "
        "per group\n",
        f"In the {n} matches every (period, team) group shares `leftHoop` across all its "
        "possessions and the two teams of a period hold opposite values (`left_hoop_consensus` "
        "= `ok` in every row; a mixed group fails the run, it is never averaged). "
        "`attack_sign = -1` when `leftHoop` is true (the offence attacks the hoop at negative x "
        "of the venue frame), `+1` otherwise. Periods per match: "
        f"{_span(matches, 'periods')} (overtime is a fifth period).\n",
        "**Shot probe, per (match, period, team).** The shooter's `tracking_objects` position "
        "at `shots.startFrame`, rotated into the attack frame of the events by the "
        "possession's `leftHoop` (`(x, y)` when true, `(-x, -y)` when false), against "
        "`shots.location`, both in feet as delivered. The assertion is binary and has no "
        "threshold: the rotation `leftHoop` predicts must be the closer of the two for every "
        "matched shot of the group (`shots_rule_closer = shots_matched`) and the opposite "
        f"rotation must land within {SHOT_TOL_M} m = {SHOT_TOL_FT:.4f} ft of no shot "
        "(`shots_within_0_5m_flipped = 0`). A wrong rotation cannot pass that. Shots without "
        "a location, without a possession or without a shooter position at that frame are "
        "counted per match below and excluded here.\n",
        _md_table(groups, GROUP_COLUMNS) + "\n",
    ]
    if failing:
        parts.append(
            f"**Orientation NOT consistent: {len(failing)} of {len(groups)} groups fail** "
            f"({', '.join(failing)}); the opposite rotation lands within {SHOT_TOL_M} m of "
            f"{flipped} shots.\n"
        )
    else:
        parts.append(
            f"**Orientation consistent in {len(ok)} of {len(groups)} groups**"
            + (
                f" ({len(no_shots)} groups without a matched shot, listed as `no_shots`)"
                if no_shots
                else ""
            )
            + f": the rotation `leftHoop` predicts is the closer one for {closer} of {matched} "
            f"matched shots, the opposite rotation is within {SHOT_TOL_M} m of {flipped} of "
            "them, and the per-match median residual of the rule is "
            f"{_span(matches, 'shot_median_ft')} ft.\n"
        )
    parts += [
        "### Basketball: the share within 0.5 m, per match, as a number\n",
        f"The share of matched shots whose rotated shooter position lies within {SHOT_TOL_M} m "
        "of `shots.location` is published per match and is **not a bar**: it mixes the "
        "orientation question, answered above, with a second one, whether `shots.location` "
        'is the shooter\'s position exactly at `startFrame`, whose answer is "not always", '
        "for reasons unrelated to orientation (next section). A threshold on the mix would "
        "pass a 99% that hid a wrong rotation in the remaining 1% and fail a perfect rotation "
        "with a clock misalignment, the same reason `docs/formats/football.md` reports "
        "`frame_max - end_frame` as a number and not `frame_max == end_frame` as a boolean.\n",
        _md_table(
            matches,
            (
                "match_id",
                "shots",
                "shots_no_location",
                "shots_no_possession",
                "shots_no_tracking",
                "shots_matched",
                "shots_rule_closer",
                "shots_within_0_5m",
                "shots_within_0_5m_pct",
                "shots_within_0_5m_flipped",
                "shot_median_ft",
                "shot_p95_ft",
                "shot_max_ft",
                "shots_residual",
            ),
        )
        + "\n",
        f"Per match: {_span(matches, 'shots_within_0_5m_pct')}% within {SHOT_TOL_M} m, "
        f"median residual {_span(matches, 'shot_median_ft')} ft, p95 "
        f"{_span(matches, 'shot_p95_ft')} ft, maximum {_span(matches, 'shot_max_ft')} ft.\n",
        f"### Basketball: the {len(residuals)} shots beyond 0.5 m, one by one\n",
        f"{len(residuals)} of {matched} matched shots. For every one, `frame_offset` and "
        "`d_at_offset_ft` locate the shooter's frame of closest approach to the declared "
        f"location, within {RESIDUAL_WINDOW_FRAMES} frames of `startFrame` (offset in frames "
        "at 25 fps, distance in feet). `kind` is `extrapolated` when the shooter's tracking "
        "entry at `startFrame` has `isDetected = false` (an extrapolated position, with its "
        f"`predError`), `time_offset` when that closest approach lies within {SHOT_TOL_M} m, "
        "and `unexplained` when it does not. `touch_endloc_to_tracking_ft` is the distance "
        "from `touches.endLoc` of the shot's `touchId` to the rotated tracking position at "
        "`startFrame`; `touch_endloc_to_location_ft`, to `shots.location`.\n",
        _md_table(residuals, RESIDUAL_COLUMNS) + "\n",
        f"{len(extrapolated)} are extrapolated positions (`predError` "
        f"{_span(extrapolated, 'pred_error_ft') if extrapolated else 'n/a'} ft), "
        f"{len(offsets)} are found at another frame of the tracking, with offsets of "
        f"{', '.join(f'{o:+d}' for o in offsets)} frames at 25 fps"
        + (
            f", and {len(unexplained)} "
            f"{'is' if len(unexplained) == 1 else 'are'} found at no frame within the window "
            f"(closest approach {_span(unexplained, 'd_at_offset_ft')} ft at "
            f"{_span(unexplained, 'frame_offset')} frames)"
            if unexplained
            else ""
        )
        + '. The offsets carry both signs, so "the provider takes the location at the '
        'release rather than at `startFrame`" does not explain them: a release happens '
        "after `startFrame`, never before it. What the data supports is more modest: in these "
        "shots the declared location and the tracking are misaligned in time, between "
        f"{min(offsets, default=0)} and {max(offsets, default=0):+d} frames, with no consistent "
        f"sign. In every one of them that has a touch ({len(with_touch)} of {len(residuals)}), "
        "`touches.endLoc` sits on the rotated tracking position at `startFrame` "
        f"(`touch_endloc_to_tracking_ft` {_span(with_touch, 'touch_endloc_to_tracking_ft')} ft) "
        "and away from `shots.location` (`touch_endloc_to_location_ft` "
        f"{_span(with_touch, 'touch_endloc_to_location_ft')} ft): it is `shots.location` "
        "that departs, not the tracking. Over all matched shots with a touch, "
        "`touches.endLoc` is within 0.5 m of the tracking at `startFrame` in "
        f"{_span(matches, 'touch_endloc_within_0_5m_pct')}% per match "
        "(`touch_endloc_within_0_5m_pct`).\n",
        "**Consequence for tasks 11, 12, 17 and 20: nobody can assume that `shots.location` "
        "is the shooter's position at `startFrame`.** Whoever needs the position of a shot has "
        "to choose a source and say which: `shots.location` (the provider's declared "
        "location, in the attack frame, off by up to "
        f"{_span(matches, 'shot_max_ft')} ft in these matches), the shooter's `tracking_objects` "
        "row at `startFrame` (the venue frame, the physical record), or `touches.endLoc` of "
        "the shot's `touchId`, which coincides with that tracking row.\n",
        "### Basketball: court geometry, FIBA 28 x 15 m against 94 x 50 ft\n",
        "Two measurements per match, both on the attack frame of the events. **Hoop:** "
        "`shots.distance` must equal `hypot(x - hoop_x, y)`; `hoop_x_median_ft` is the median "
        "of `x - sqrt(distance^2 - y^2)` over the shots and `dist_resid_max_*` the largest "
        f"residual against the FIBA hoop ({FIBA.hoop_x_ft:.2f} ft, 1.575 m from the baseline "
        f"of a {FIBA.length_ft:.2f} ft court) and the NBA hoop ({NBA.hoop_x_ft:.2f} ft, 5.25 ft "
        "from the baseline of a 94 ft court). **Three-point radius:** the threshold on "
        "`distance` that best separates the provider's `three` flag from two-point shots, "
        f"outside the corners (|y| <= {CORNER_MAX_ABS_Y_FT:g} ft, under both corner lines), "
        "reported as the plateau of radii sharing the minimum misclassification, with the "
        f"count at the FIBA radius ({FIBA.three_radius_ft:.2f} ft = 6.75 m) and at the NBA "
        f"radius ({NBA.three_radius_ft:.2f} ft) next to it. `court` is the court both "
        "measurements pick in that match.\n",
        _md_table(
            matches,
            (
                "match_id",
                "shots_with_distance",
                "hoop_x_median_ft",
                "dist_resid_max_fiba_ft",
                "dist_resid_max_nba_ft",
                "hoop_court",
                "radius_n",
                "radius_three_min_ft",
                "radius_two_max_ft",
                "radius_plateau_lo_ft",
                "radius_plateau_hi_ft",
                "radius_misclassified",
                "radius_misclassified_fiba",
                "radius_misclassified_nba",
                "radius_court",
                "court",
            ),
        )
        + "\n",
        (
            f"**Court: `{court}`** in {sum(1 for r in matches if r['court'] == court)} of {n} "
            f"matches (hoop x {_span(matches, 'hoop_x_median_ft')} ft, residual against the "
            f"FIBA hoop {_span(matches, 'dist_resid_max_fiba_ft')} ft and against the NBA hoop "
            f"{_span(matches, 'dist_resid_max_nba_ft')} ft; nearest three at "
            f"{_span(matches, 'radius_three_min_ft')} ft, farthest two at "
            f"{_span(matches, 'radius_two_max_ft')} ft; misclassified at the FIBA radius "
            f"{_span(matches, 'radius_misclassified_fiba')}, at the NBA radius "
            f"{_span(matches, 'radius_misclassified_nba')}). The ACB plays on a FIBA court; "
            f"the data {'agrees' if court == FIBA.spec else 'does not agree'} with that "
            f"expectation. `dim_match.surface_*` for basketball is therefore "
            f"{FIBA.length_ft * M_PER_FT:g} x {FIBA.width_ft * M_PER_FT:g} m, "
            "`surface_spec = 'fiba'`."
            if court == FIBA.spec
            else f"**Court: `{court}`** (see the table; `dim_match.surface_*` cannot be fixed "
            "until every match agrees)."
        ),
        "\n**Extents** of `shots.location` and `rebounds.location` (feet, attack frame). "
        f"FIBA half-court: x in [-{FIBA.length_ft / 2:.2f}, {FIBA.length_ft / 2:.2f}], "
        f"|y| <= {FIBA.width_ft / 2:.2f}; 94 x 50: x in [-47, 47], |y| <= 25. Shot locations "
        "are shooter positions from the tracking, so they step past both by the tracking "
        "noise; the extents are reported for completeness and do not decide the court.\n",
        _md_table(
            matches,
            (
                "match_id",
                "shots_x_min_ft",
                "shots_x_max_ft",
                "shots_y_min_ft",
                "shots_y_max_ft",
                "rebounds",
                "rebounds_with_location",
                "rebounds_x_min_ft",
                "rebounds_x_max_ft",
                "rebounds_y_min_ft",
                "rebounds_y_max_ft",
            ),
        )
        + "\n",
    ]
    return "\n".join(parts)


def _render_football(rows: Sequence[Row]) -> str:
    n = len(rows)
    failing = [str(r["match_id"]) for r in rows if r["side_check"] != "ok"]
    winners = sorted({str(r["event_frame"]) for r in rows})
    with_lm = [r for r in rows if r["players_last_modified"] == "yes"]
    without_lm = [r for r in rows if r["players_last_modified"] != "yes"]
    exact = {str(r["match_id"]) for r in rows if float(str(r["attack_median_m"])) == 0}
    same_cut = exact == {str(r["match_id"]) for r in with_lm}
    parts = [
        "### Football: `match.home_team_side` gives the sign, the phases check it\n",
        "`home_team_side[period]` = `left_to_right` means home attacks towards +x in that "
        "period (`attack_sign = +1`), away the opposite. Every `phases_of_play` row of that "
        "team and period must carry the same `attacking_side`; the share is reported and the "
        "bar is 100%.\n",
        _md_table(
            rows,
            (
                "match_id",
                "home_team_id",
                "away_team_id",
                "home_team_side",
                "periods",
                "phases",
                "phases_agree",
                "phases_agree_pct",
                "side_check",
            ),
        )
        + "\n",
        (
            f"**Bar met in {n - len(failing)} of {n} matches; below 100%: {', '.join(failing)}.**\n"
            if failing
            else f"**100% in {n} of {n} matches** ({_span(rows, 'phases')} phases per match).\n"
        ),
        "### Football: the frame of the events\n",
        "`player_possession` (`x_start`, `y_start`) against the `tracking_objects` position "
        "of `player_id` at `frame_start`, metres, under two hypotheses: *venue* (the event "
        "coordinates are already in the tracking frame) and *attack* (`(x, y)` when "
        "`attacking_side` is `left_to_right`, `(-x, -y)` when `right_to_left`, i.e. the "
        f"events are normalised so the attacker goes towards +x). Share within {EVENT_TOL_M:g} m "
        f"of each, plus the share within {EVENT_TOL_TASK4_M:g} m under *attack* (task 4's "
        "tolerance). Rows without coordinates or without a tracking position at that frame are "
        "counted and excluded from the denominator.\n",
        _md_table(
            rows,
            (
                "match_id",
                "pp_events",
                "pp_no_xy",
                "pp_no_tracking",
                "pp_matched",
                "venue_within_1m_pct",
                "attack_within_1m_pct",
                "attack_within_2m_pct",
                "attack_median_m",
                "attack_p95_m",
                "attack_max_m",
                "event_frame",
            ),
        )
        + "\n",
        f"**Winner: `{'`, `'.join(winners)}`** in {n} of {n} matches "
        f"(*attack* {_span(rows, 'attack_within_1m_pct')}% within {EVENT_TOL_M:g} m, *venue* "
        f"{_span(rows, 'venue_within_1m_pct')}%; *attack* within {EVENT_TOL_TASK4_M:g} m "
        f"{_span(rows, 'attack_within_2m_pct')}%, task 4 measured 95.01 to 100% on every event "
        "type). Silver keeps the venue frame and maps the football events with the *attack* "
        "rule; `attacking_side` is the label that says which rotation.\n",
        "### Football: two regimes of the events, and the field that does not exist\n",
        "Two independent signals cut the 20 matches the same way. Task 7 found that "
        "`match.json` comes in two regimes: in 10 matches every `players[]` entry carries "
        "`last_modified` (and `playing_time.sequences`), in the other 10 none does "
        "(`players_last_modified` below, read from `bronze.football.match_players`). The "
        "event probe above finds two regimes too: in some matches every `player_possession` "
        "coordinate equals the tracking exactly (`attack_median_m` = 0, `attack_max_m` = 0), "
        "in the others they differ by a decimetre in median and by tens of metres at the "
        "extreme.\n",
        _md_table(
            rows,
            (
                "match_id",
                "players_last_modified",
                "pp_matched",
                "attack_within_1m_pct",
                "attack_median_m",
                "attack_p95_m",
                "attack_max_m",
            ),
        )
        + "\n",
        f"With `last_modified` ({len(with_lm)} matches): {_span(with_lm, 'attack_within_1m_pct')}% "
        f"within 1 m, median {_span(with_lm, 'attack_median_m')} m, maximum "
        f"{_span(with_lm, 'attack_max_m')} m. Without it ({len(without_lm)} matches): "
        f"{_span(without_lm, 'attack_within_1m_pct')}% within 1 m, median "
        f"{_span(without_lm, 'attack_median_m')} m, maximum {_span(without_lm, 'attack_max_m')} m. "
        + (
            "**The two partitions are exactly the same set of matches.** That is not a "
            "coincidence: it is the signature of two versions of the provider's processor "
            "inside one open bundle, the fourth time this material presents itself as "
            "homogeneous and is not (after the two tracking layouts of task 4, the two "
            "frame-loss regimes of basketball in task 5 and the two `players[]` regimes of "
            "task 7), and the first time two independent signals mark the same cut. "
            "**Nobody can filter by this difference, because no field declares it**: the "
            "only ways to tell the regime of a match are the presence of `last_modified` in "
            "its `players[]` or the residual of its events against its tracking, and neither "
            "is a version number.\n"
            if same_cut
            else "The two partitions differ (see the table); the coincidence found on the "
            "frozen bundle no longer holds and this section needs re-reading.\n"
        ),
    ]
    return "\n".join(parts)


def render_doc(reports: dict[str, list[Row]], table_counts: dict[str, int]) -> str:
    """The orientation section of `docs/decisions.md`, rendered from the report rows on
    disk (one row per match, group or residual shot) and the row counts of the written
    table."""
    parts = [
        "## Orientation and court geometry (task 9)\n",
        "Generated by `tracklab orientation` from the bronze Parquet (never the raw files). "
        "Every figure below is read from `pipeline/reports/orientation_basketball.csv` (one "
        "row per match), `orientation_basketball_groups.csv` (one per match, period and "
        "team), `orientation_basketball_residual_shots.csv` (one per shot beyond 0.5 m) and "
        "`orientation_football.csv` (one per match), and this section is rendered from those "
        "rows. The table `bronze.common.orientation` "
        "(`pipeline/data/bronze/common/orientation/data.parquet`, columns `sport, "
        "native_match_id, period, native_team_id, attack_sign, evidence`) is what "
        "`dim_team_period` (task 10) reads: `attack_sign = +1` when the team attacks towards "
        "+x of the venue frame in that period, `-1` otherwise, and the two teams of a period "
        "always carry opposite signs.\n",
        "### Decision 2 of the silver schema, as measured\n",
        "Silver keeps the **venue frame** of the tracking in both sports (origin at the centre "
        "of the surface, x along the length, as the cameras deliver it) and stores the attack "
        "direction as a **sign per (match, period, team)**, never baked into `frames`. The "
        "events of both sports arrive in an **attack frame** and are mapped to the venue "
        "frame by a 180-degree rotation chosen by a provider field: basketball `(x, y)` when "
        "`possessions.leftHoop` is true, `(-x, -y)` otherwise (attacked hoop at negative x); "
        "football `(x, y)` when `attacking_side` is `left_to_right`, `(-x, -y)` when "
        "`right_to_left` (attacker towards +x). The sections below hold the per-match "
        "evidence.\n",
    ]
    if "basketball" in reports:
        parts.append(
            _render_basketball(
                reports["basketball"],
                reports.get("basketball_groups", []),
                reports.get("basketball_residual_shots", []),
            )
        )
    if "football" in reports:
        parts.append(_render_football(reports["football"]))
    counts = ", ".join(f"{sport} {n}" for sport, n in sorted(table_counts.items()))
    total = sum(table_counts.values())
    parts.append(
        "### The `orientation` table\n\n"
        f"{total} rows ({counts}): one per (sport, match, period, team), with the two teams "
        "of every (sport, match, period) carrying opposite signs (asserted by "
        "`tests/contracts/test_orientation.py`, and the singular dbt test of task 10). The "
        "`evidence` of a basketball row carries its possession count and its shot probe; "
        "that of a football row, its `home_team_side` entry and its phase count."
    )
    return "\n".join(parts) + "\n"


# --- entry point -----------------------------------------------------------------------


def run_orientation(
    *,
    sports: Sequence[str],
    manifest_path: Path,
    data_dir: Path,
    reports_dir: Path,
    docs_dir: Path,
    log: Log = print,
) -> int:
    unknown = [s for s in sports if s not in SPORTS]
    if unknown:
        raise ValueError(f"unknown sport(s) {unknown}, expected {SPORTS}")
    manifest = load_manifest(manifest_path)
    con = duckdb.connect()
    signs: list[TeamPeriodSign] = []
    failed: list[str] = []
    metadata = {"tracklab.table": TABLE, "tracklab.generated_by": "tracklab orientation"}
    for sport in sports:
        source = manifest.source(SOURCE_IDS[sport])
        if source.commit is None:
            raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
        metadata[f"tracklab.{sport}_commit"] = source.commit
        match_ids = match_ids_of(source)
        if not match_ids:
            raise FileNotFoundError(f"no tracking files for {source.source_id} in the manifest")
        log(f"orientation {sport}: {len(match_ids)} matches from {data_dir / 'bronze' / sport}")
        written: list[tuple[str, list[Row], tuple[str, ...]]]
        if sport == "basketball":
            bb = probe_basketball(con, data_dir, match_ids, log)
            failed += [
                f"basketball {g['match_id']} period {g['period']} team {g['team_id']}: "
                f"rotation not consistent (closer {g['shots_rule_closer']}/{g['shots_matched']}, "
                f"opposite within {SHOT_TOL_M} m {g['shots_within_0_5m_flipped']})"
                for g in bb.groups
                if g["verdict"] == "FAIL"
            ]
            court = decide_court(bb.matches)
            log(f"basketball court: {court}")
            if court not in {c.spec for c in COURTS}:
                failed.append(f"basketball: court geometry {court}")
            signs.extend(bb.signs)
            written = [
                ("basketball", bb.matches, BASKETBALL_COLUMNS),
                ("basketball_groups", bb.groups, GROUP_COLUMNS),
                ("basketball_residual_shots", bb.residuals, RESIDUAL_COLUMNS),
            ]
        else:
            rows, sport_signs = probe_football(con, data_dir, match_ids, log)
            failed += [
                f"football {r['match_id']}: phases agree {r['phases_agree_pct']}% < 100%"
                for r in rows
                if r["side_check"] != "ok"
            ]
            signs.extend(sport_signs)
            written = [("football", rows, FOOTBALL_COLUMNS)]
        for name, rows, columns in written:
            path = report_path(reports_dir, name)
            write_report_csv(rows, path, columns)
            log(f"report: {path} ({len(rows)} rows, {len(columns)} columns)")

    table_path = orientation_path(data_dir)
    n_rows = write_orientation_table(table_path, signs, sports, metadata)
    table_counts = {
        str(sport): int(n)
        for sport, n in con.execute(
            "SELECT sport, count(*) FROM read_parquet(?) GROUP BY 1 ORDER BY 1",
            [table_path.as_posix()],
        ).fetchall()
    }
    log(f"table: {table_path} ({n_rows} rows: {table_counts})")

    reports = {
        name: load_report(report_path(reports_dir, name))
        for name in REPORT_NAMES
        if report_path(reports_dir, name).is_file()
    }
    doc_path = docs_dir / DOC_NAME
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    existing = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else None
    doc_path.write_text(
        merge_doc(existing, render_doc(reports, table_counts)), encoding="utf-8", newline="\n"
    )
    log(f"doc: {doc_path}")

    for failure in failed:
        log(f"FAIL {failure}")
    if failed:
        log(f"orientation: {len(failed)} check(s) failed, artefacts written")
        return 1
    log("orientation: every check passed")
    return 0
