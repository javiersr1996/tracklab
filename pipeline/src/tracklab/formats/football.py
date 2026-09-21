"""Probe of the opendata-football bundle: one row of measured facts per match.

Everything here is measured, never assumed. Per match it walks the tracking JSONL
line by line (never whole in memory), reads `match.json`, `dynamic_events.csv` and
`phases_of_play.csv`, and answers the questions of task 4 in tasks/todo.md:

- exact `timestamp` format and its rule against `frame` and `match_periods`;
- frame coverage (22 players, ball, `is_detected`), ball z and coordinate ranges;
- whether the data agrees with `home_team_side` (mean goalkeeper x per period);
- which id of `match.json` the tracking `player_id` is;
- which coordinate frame the events use, checked against the tracking itself;
- how a phase, a team possession and a player possession relate.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import NamedTuple

FPS = 10
HALF_CS = 45 * 60 * 100  # period 2 of the tracking clock restarts at 45:00.00
HALF_DS = 45 * 60 * 10  # same for the events clock, in tenths
THIRD_M = 105 / 6  # a third of the pitch from the centre line
GK_MIN_ABS_X = 20.0  # a goalkeeper averages ~45 m from centre; below this the sign is noise
XY_TOL_M = 2.0  # events keep 2 decimals; 2 m absorbs the extrapolated frames

TS_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d{2})$")
EV_TIME_RE = re.compile(r"^(\d{2}):(\d{2})\.(\d)$")
LEFT_CHANNELS = {"wide_left", "half_space_left"}
RIGHT_CHANNELS = {"wide_right", "half_space_right"}

EVENT_COLUMNS = (
    "index",
    "event_type",
    "end_type",
    "frame_start",
    "frame_end",
    "frame_physical_start",
    "time_start",
    "period",
    "attacking_side",
    "player_id",
    "team_id",
    "x_start",
    "y_start",
    "channel_start",
    "phase_index",
    "n_player_possessions_in_phase",
    "first_player_possession_in_team_possession",
    "last_player_possession_in_team_possession",
    "lead_to_shot",
)
PHASE_COLUMNS = (
    "index",
    "period",
    "frame_start",
    "frame_end",
    "team_in_possession_id",
    "n_player_possessions_in_phase",
    "team_possession_loss_in_phase",
    "attacking_side",
    "x_start",
    "third_start",
)


@dataclass(frozen=True)
class MatchBundle:
    match_id: int
    match_json: Path
    tracking: Path
    events: Path
    phases: Path


def discover(raw_root: Path) -> list[MatchBundle]:
    """The 4 files of every match under `<raw_root>/data/matches/<id>/`."""
    bundles = []
    for match_dir in sorted((raw_root / "data" / "matches").iterdir()):
        if not match_dir.is_dir() or not match_dir.name.isdigit():
            continue
        mid = int(match_dir.name)
        bundles.append(
            MatchBundle(
                match_id=mid,
                match_json=match_dir / f"{mid}_match.json",
                tracking=match_dir / f"{mid}_tracking_extrapolated.jsonl",
                events=match_dir / f"{mid}_dynamic_events.csv",
                phases=match_dir / f"{mid}_phases_of_play.csv",
            )
        )
    return bundles


def aggregate_paths(raw_root: Path) -> list[Path]:
    return sorted((raw_root / "data" / "aggregates").glob("*.csv"))


class Event(NamedTuple):
    idx: int
    event_type: str
    end_type: str
    frame_start: int
    frame_end: int
    frame_physical_start: int | None
    time_start: str
    period: int
    attacking_side: str
    player_id: int | None
    team_id: int | None
    x_start: float | None
    y_start: float | None
    channel_start: str
    phase_index: int | None
    n_pp_in_phase: int | None
    first_in_tp: bool
    last_in_tp: bool
    lead_to_shot: bool


class Phase(NamedTuple):
    idx: int
    period: int
    frame_start: int
    frame_end: int
    team_id: int
    n_pp_in_phase: int
    loss: bool
    attacking_side: str
    x_start: float | None
    third_start: str


def _read_projected(path: Path, wanted: tuple[str, ...]) -> tuple[int, list[list[str]]]:
    """Rows of a wide CSV reduced to `wanted`, in `wanted` order, plus the column count."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        positions = [header.index(name) for name in wanted]
        rows = [[row[i] for i in positions] for row in reader]
    return len(header), rows


def _int(s: str) -> int:
    return int(s)


def _opt_int(s: str) -> int | None:
    return int(s) if s else None


def _opt_float(s: str) -> float | None:
    return float(s) if s else None


def _bool(s: str) -> bool:
    return s == "True"


def read_events(path: Path) -> tuple[int, list[Event]]:
    n_cols, rows = _read_projected(path, EVENT_COLUMNS)
    events = [
        Event(
            idx=_int(r[0]),
            event_type=r[1],
            end_type=r[2],
            frame_start=_int(r[3]),
            frame_end=_int(r[4]),
            frame_physical_start=_opt_int(r[5]),
            time_start=r[6],
            period=_int(r[7]),
            attacking_side=r[8],
            player_id=_opt_int(r[9]),
            team_id=_opt_int(r[10]),
            x_start=_opt_float(r[11]),
            y_start=_opt_float(r[12]),
            channel_start=r[13],
            phase_index=_opt_int(r[14]),
            n_pp_in_phase=_opt_int(r[15]),
            first_in_tp=_bool(r[16]),
            last_in_tp=_bool(r[17]),
            lead_to_shot=_bool(r[18]),
        )
        for r in rows
    ]
    return n_cols, events


def read_phases(path: Path) -> tuple[int, list[Phase]]:
    n_cols, rows = _read_projected(path, PHASE_COLUMNS)
    phases = [
        Phase(
            idx=_int(r[0]),
            period=_int(r[1]),
            frame_start=_int(r[2]),
            frame_end=_int(r[3]),
            team_id=_int(r[4]),
            n_pp_in_phase=_int(r[5]),
            loss=_bool(r[6]),
            attacking_side=r[7],
            x_start=_opt_float(r[8]),
            third_start=r[9],
        )
        for r in rows
    ]
    return n_cols, phases


@dataclass
class TrackingScan:
    """Counters filled by one pass over the tracking JSONL."""

    n_lines: int = 0
    frame_max: int = -1
    contiguous: bool = True
    frame_keys: set[str] = field(default_factory=set)
    player_keys: set[str] = field(default_factory=set)
    ball_keys: set[str] = field(default_factory=set)
    possession_keys: set[str] = field(default_factory=set)
    corner_keys: set[str] = field(default_factory=set)
    ts_null: int = 0
    period_null: int = 0
    outside: int = 0
    ts_null_and_outside: int = 0
    ts_nonnull: int = 0
    ts_format_ok: int = 0
    ts_rule_ok: int = 0
    p2_first_ts: str = ""
    n_in: int = 0
    players_hist: Counter[int] = field(default_factory=Counter)
    ball_present: int = 0
    ball_xor_22: int = 0
    entries: int = 0
    entries_detected: int = 0
    entries_detected_null: int = 0
    frames_all_detected: int = 0
    ball_detected: Counter[str] = field(default_factory=Counter)
    z_values: list[float] = field(default_factory=list)
    x_min: float = math.inf
    x_max: float = -math.inf
    y_min: float = math.inf
    y_max: float = -math.inf
    gk_x: dict[tuple[int, int], list[float]] = field(default_factory=lambda: defaultdict(list))
    ids: set[int] = field(default_factory=set)
    poss_ids: set[int] = field(default_factory=set)
    poss_group: Counter[str] = field(default_factory=Counter)
    poss_player: int = 0
    covered: int = 0
    group_set: int = 0
    group_and_covered: int = 0
    group_agrees: int = 0
    captured: dict[tuple[int, int], tuple[float, float]] = field(default_factory=dict)


def _parse_ts_cs(ts: str) -> int | None:
    m = TS_RE.match(ts)
    if not m:
        return None
    h, mi, s, cs = (int(g) for g in m.groups())
    return ((h * 60 + mi) * 60 + s) * 100 + cs


def scan_tracking(
    path: Path,
    periods: dict[int, tuple[int, int]],
    gk_team: dict[int, int],
    phase_team: dict[int, int],
    team_of_group: dict[str, int],
    need: dict[int, set[int]],
) -> TrackingScan:
    t = TrackingScan()
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            d = json.loads(line)
            frame: int = d["frame"]
            t.n_lines += 1
            t.frame_max = max(t.frame_max, frame)
            if frame != i:
                t.contiguous = False
            t.frame_keys.update(d.keys())
            ball = d["ball_data"]
            poss = d["possession"]
            t.ball_keys.update(ball.keys())
            t.possession_keys.update(poss.keys())
            t.corner_keys.update(d["image_corners_projection"].keys())

            period = d["period"]
            in_period = next((p for p, (a, b) in periods.items() if a <= frame <= b), None)
            ts = d["timestamp"]
            if ts is None:
                t.ts_null += 1
                if in_period is None:
                    t.ts_null_and_outside += 1
            else:
                t.ts_nonnull += 1
                cs = _parse_ts_cs(ts)
                if cs is not None:
                    t.ts_format_ok += 1
                    if period is not None and period in periods:
                        start = periods[period][0]
                        if cs == HALF_CS * (period - 1) + (frame - start) * (100 // FPS):
                            t.ts_rule_ok += 1
                if period == 2 and not t.p2_first_ts:
                    t.p2_first_ts = ts
            if period is None:
                t.period_null += 1
            if in_period is None:
                t.outside += 1

            players = d["player_data"]
            n = len(players)
            for p in players:
                t.player_keys.update(p.keys())
                t.ids.add(p["player_id"])
            if in_period is None:
                continue

            t.n_in += 1
            t.players_hist[n] += 1
            has_ball = ball["x"] is not None
            t.ball_present += has_ball
            if has_ball != (n == 22):
                t.ball_xor_22 += 1
            if has_ball:
                t.ball_detected[str(ball["is_detected"])] += 1
                if ball["z"] is not None:
                    t.z_values.append(ball["z"])
            all_detected = n > 0
            wanted = need.get(frame)
            for p in players:
                t.entries += 1
                det = p["is_detected"]
                if det is None:
                    t.entries_detected_null += 1
                    all_detected = False
                elif det:
                    t.entries_detected += 1
                else:
                    all_detected = False
                x, y, pid = p["x"], p["y"], p["player_id"]
                t.x_min, t.x_max = min(t.x_min, x), max(t.x_max, x)
                t.y_min, t.y_max = min(t.y_min, y), max(t.y_max, y)
                if pid in gk_team:
                    t.gk_x[(gk_team[pid], in_period)].append(x)
                if wanted is not None and pid in wanted:
                    t.captured[(frame, pid)] = (x, y)
            if all_detected:
                t.frames_all_detected += 1

            if poss["player_id"] is not None:
                t.poss_player += 1
                t.poss_ids.add(poss["player_id"])
            group = poss["group"]
            t.poss_group[str(group)] += 1
            phase_owner = phase_team.get(frame)
            if phase_owner is not None:
                t.covered += 1
            if group is not None:
                t.group_set += 1
                if phase_owner is not None:
                    t.group_and_covered += 1
                    if team_of_group.get(group) == phase_owner:
                        t.group_agrees += 1
    return t


def pct(num: int | float, den: int | float) -> float | None:
    return round(100.0 * num / den, 2) if den else None


def _counts(counter: Counter[str]) -> str:
    return ";".join(f"{k}={v}" for k, v in sorted(counter.items(), key=lambda kv: -kv[1]))


def _key_of_ids(ids: set[int], players: list[dict[str, object]]) -> tuple[str, int, int, int]:
    in_id = len(ids & {int(str(p["id"])) for p in players})
    in_to = len(ids & {int(str(p["trackable_object"])) for p in players})
    in_tp = len(ids & {int(str(p["team_player_id"])) for p in players})
    n = len(ids)
    if n == 0:
        key = "none"
    elif in_id == n and in_to < n:
        key = "id"
    elif in_to == n and in_id < n:
        key = "trackable_object"
    elif in_id == n and in_to == n:
        key = "ambiguous"
    else:
        key = "unmatched"
    return key, in_id, in_to, in_tp


def _side_check(
    gk_x: dict[tuple[int, int], list[float]],
    sides: list[str],
    home_id: int,
    away_id: int,
) -> tuple[str, str, str]:
    """Mean goalkeeper x per period vs `home_team_side`, under 'left_to_right' == towards +x."""
    home_parts: list[str] = []
    away_parts: list[str] = []
    bad: list[str] = []
    for p, side in enumerate(sides, start=1):
        expected_home = -1 if side == "left_to_right" else 1
        for team, parts, expected in (
            (home_id, home_parts, expected_home),
            (away_id, away_parts, -expected_home),
        ):
            xs = gk_x.get((team, p), [])
            if not xs:
                parts.append(f"p{p}:none")
                bad.append(f"p{p}:no_gk")
                continue
            mean = sum(xs) / len(xs)
            parts.append(f"p{p}:{mean:+.1f}")
            if abs(mean) < GK_MIN_ABS_X or math.copysign(1, mean) != expected:
                bad.append(f"p{p}:{'home' if team == home_id else 'away'}")
    verdict = "ok" if not bad else "MISMATCH " + ",".join(bad)
    return ";".join(home_parts), ";".join(away_parts), verdict


def _team_possessions(pps: list[Event]) -> tuple[int, int, int]:
    """(n first flags, n last flags, n team possessions spanning more than one phase)."""
    n_first = n_last = multi = 0
    phases_seen: set[int] | None = None
    for e in pps:
        if e.first_in_tp:
            n_first += 1
            phases_seen = set()
        if phases_seen is not None and e.phase_index is not None:
            phases_seen.add(e.phase_index)
        if e.last_in_tp:
            n_last += 1
            if phases_seen is not None and len(phases_seen) > 1:
                multi += 1
            phases_seen = None
    return n_first, n_last, multi


def _phase_runs(phases: list[Phase]) -> tuple[int, int, int, int, int]:
    """(same-team runs, gaps, overlaps, loss-vs-team-change mismatches, pairs compared)."""
    runs = gaps = overlaps = mismatches = pairs = 0
    ordered = sorted(phases, key=lambda p: (p.period, p.frame_start))
    prev: Phase | None = None
    for ph in ordered:
        if prev is None or prev.period != ph.period:
            runs += 1
        else:
            pairs += 1
            if ph.frame_start > prev.frame_end:
                gaps += 1
            elif ph.frame_start < prev.frame_end:
                overlaps += 1
            changed = ph.team_id != prev.team_id
            runs += changed
            if prev.loss != changed:
                mismatches += 1
        prev = ph
    return runs, gaps, overlaps, mismatches, pairs


def _ev_time_checks(
    events: list[Event], periods: dict[int, tuple[int, int]]
) -> tuple[int, int, Counter[str], int]:
    """(format ok, time == clock(frame_start), event types where it is instead the clock of
    frame_physical_start, rest)."""
    fmt_ok = rule_ok = other = 0
    physical: Counter[str] = Counter()
    for e in events:
        m = EV_TIME_RE.match(e.time_start)
        if not m:
            continue
        fmt_ok += 1
        mi, s, ds = (int(g) for g in m.groups())
        start = periods.get(e.period)
        if start is None:
            other += 1
            continue
        got = (mi * 60 + s) * 10 + ds
        base = HALF_DS * (e.period - 1) - start[0]
        if got == base + e.frame_start:
            rule_ok += 1
        elif e.frame_physical_start is not None and got == base + e.frame_physical_start:
            physical[e.event_type] += 1
        else:
            other += 1
    return fmt_ok, rule_ok, physical, other


def _xy_frame(
    events: list[Event], captured: dict[tuple[int, int], tuple[float, float]]
) -> dict[str, object]:
    """Compare event (x_start, y_start) with the tracking position of the same player and frame.

    raw: same coordinates as the tracking. flip: (-x, -y), i.e. the event frame is rotated
    so that the attacking team always attacks towards +x.
    """
    counts: dict[str, Counter[str]] = {"left_to_right": Counter(), "right_to_left": Counter()}
    missing = 0
    for e in events:
        if e.player_id is None or e.x_start is None or e.y_start is None:
            continue
        pos = captured.get((e.frame_start, e.player_id))
        if pos is None:
            missing += 1
            continue
        c = counts.setdefault(e.attacking_side, Counter())
        c["n"] += 1
        tx, ty = pos
        c["raw"] += math.hypot(e.x_start - tx, e.y_start - ty) <= XY_TOL_M
        c["flip"] += math.hypot(-e.x_start - tx, -e.y_start - ty) <= XY_TOL_M
    ltr, rtl = counts["left_to_right"], counts["right_to_left"]
    raw_ltr, raw_rtl = pct(ltr["raw"], ltr["n"]), pct(rtl["raw"], rtl["n"])
    flip_ltr, flip_rtl = pct(ltr["flip"], ltr["n"]), pct(rtl["flip"], rtl["n"])
    # A missing side compares as NaN: every test below is false and the frame stays undetermined.
    measured = (raw_ltr, raw_rtl, flip_ltr, flip_rtl)
    r_l, r_r, f_l, f_r = (math.nan if v is None else v for v in measured)
    frame = "undetermined"
    if r_l >= 90 and f_r >= 90 and r_r <= 10 and f_l <= 10:
        frame = "attack_normalized"
    elif r_l >= 90 and r_r >= 90 and f_l <= 10 and f_r <= 10:
        frame = "raw_pitch"
    return {
        "ev_coord_frame": frame,
        "ev_xy_compared": ltr["n"] + rtl["n"],
        "ev_xy_missing_in_tracking": missing,
        "ev_xy_raw_ltr_pct": raw_ltr,
        "ev_xy_raw_rtl_pct": raw_rtl,
        "ev_xy_flip_ltr_pct": flip_ltr,
        "ev_xy_flip_rtl_pct": flip_rtl,
    }


def _y_sign(events: list[Event]) -> dict[str, object]:
    """Of events in a *_left channel, share with y_start > 0, per attacking side."""
    c: dict[str, Counter[str]] = defaultdict(Counter)
    for e in events:
        if e.y_start is None:
            continue
        if e.channel_start in LEFT_CHANNELS:
            c[e.attacking_side]["left_n"] += 1
            c[e.attacking_side]["left_pos"] += e.y_start > 0
        elif e.channel_start in RIGHT_CHANNELS:
            c[e.attacking_side]["right_n"] += 1
            c[e.attacking_side]["right_pos"] += e.y_start > 0
    ltr, rtl = c["left_to_right"], c["right_to_left"]
    return {
        "y_left_pos_ltr_pct": pct(ltr["left_pos"], ltr["left_n"]),
        "y_left_pos_rtl_pct": pct(rtl["left_pos"], rtl["left_n"]),
        "y_right_pos_ltr_pct": pct(ltr["right_pos"], ltr["right_n"]),
        "y_right_pos_rtl_pct": pct(rtl["right_pos"], rtl["right_n"]),
    }


def _phase_thirds(phases: list[Phase]) -> float | None:
    """Share of phases whose third_start label matches x_start under the attack-towards-+x frame."""
    n = ok = 0
    for ph in phases:
        if ph.x_start is None or ph.third_start not in ("attacking_third", "defensive_third"):
            continue
        n += 1
        attacking = ph.x_start > THIRD_M
        defensive = ph.x_start < -THIRD_M
        ok += attacking if ph.third_start == "attacking_third" else defensive
    return pct(ok, n)


def probe_match(bundle: MatchBundle) -> dict[str, object]:
    meta = json.loads(bundle.match_json.read_text(encoding="utf-8"))
    periods: dict[int, tuple[int, int]] = {
        p["period"]: (p["start_frame"], p["end_frame"]) for p in meta["match_periods"]
    }
    home_id, away_id = meta["home_team"]["id"], meta["away_team"]["id"]
    sides: list[str] = meta["home_team_side"]
    players: list[dict[str, object]] = meta["players"]
    gk_team = {
        int(str(p["id"])): int(str(p["team_id"]))
        for p in players
        if isinstance(p["player_role"], dict) and p["player_role"].get("acronym") == "GK"
    }
    team_of_group = {"home team": home_id, "away team": away_id}

    ev_cols, events = read_events(bundle.events)
    ph_cols, phases = read_phases(bundle.phases)
    pps = [e for e in events if e.event_type == "player_possession"]

    phase_team: dict[int, int] = {}
    for ph in phases:
        for f in range(ph.frame_start, ph.frame_end + 1):
            phase_team[f] = ph.team_id
    need: dict[int, set[int]] = defaultdict(set)
    for e in events:
        if e.player_id is not None and e.x_start is not None:
            need[e.frame_start].add(e.player_id)

    t = scan_tracking(bundle.tracking, periods, gk_team, phase_team, team_of_group, need)

    id_key, in_id, in_to, in_tp = _key_of_ids(t.ids, players)
    poss_key = _key_of_ids(t.poss_ids, players)[0]
    ev_ids = {e.player_id for e in events if e.player_id is not None}
    ev_key = _key_of_ids(ev_ids, players)[0]
    gk_home, gk_away, side_check = _side_check(t.gk_x, sides, home_id, away_id)

    n_partial = sum(v for k, v in t.players_hist.items() if 0 < k < 22)
    n_over = sum(v for k, v in t.players_hist.items() if k > 22)
    zs = sorted(t.z_values)
    z_neg = sum(1 for z in zs if z < 0)

    pp_rows_by_phase: Counter[int | None] = Counter(e.phase_index for e in pps)
    n_first, n_last, multi = _team_possessions(pps)
    runs, gaps, overlaps, loss_mismatch, pairs = _phase_runs(phases)
    fmt_ok, rule_ok, physical, time_other = _ev_time_checks(events, periods)
    known_ids = {int(str(p["id"])) for p in players}
    unknown = Counter(e.player_id for e in events if e.player_id not in known_ids | {None})
    end_types = Counter(e.end_type for e in pps)

    row: dict[str, object] = {
        "match_id": bundle.match_id,
        "home": meta["home_team"]["short_name"],
        "away": meta["away_team"]["short_name"],
        "date": meta["date_time"],
        # tracking: frames and clock
        "n_frames": t.n_lines,
        "frame_contiguous_from_0": t.contiguous and t.frame_max == t.n_lines - 1,
        "frame_max": t.frame_max,
        "periods": ";".join(f"p{p}:{a}-{b}" for p, (a, b) in sorted(periods.items())),
        "frame_max_minus_last_end": t.frame_max - max(b for _, b in periods.values()),
        "frames_outside_periods": t.outside,
        "ts_null": t.ts_null,
        "period_null": t.period_null,
        "ts_null_iff_outside": t.ts_null == t.outside == t.ts_null_and_outside
        and t.period_null == t.ts_null,
        "ts_format": "HH:MM:SS.ff",
        "ts_format_pct": pct(t.ts_format_ok, t.ts_nonnull),
        "ts_rule_pct": pct(t.ts_rule_ok, t.ts_nonnull),
        "p2_first_ts": t.p2_first_ts,
        # tracking: coverage
        "frames_in_periods": t.n_in,
        "pct_22_players": pct(t.players_hist[22], t.n_in),
        "pct_0_players": pct(t.players_hist[0], t.n_in),
        "pct_partial_1_21": pct(n_partial, t.n_in),
        "frames_over_22": n_over,
        "n_players_max": max(t.players_hist) if t.players_hist else 0,
        "pct_ball_present": pct(t.ball_present, t.n_in),
        "ball_present_iff_22": t.ball_xor_22 == 0,
        "pct_entries_detected": pct(t.entries_detected, t.entries),
        "entries_detected_null": t.entries_detected_null,
        "pct_frames_22_all_detected": pct(t.frames_all_detected, t.n_in),
        "pct_ball_detected": pct(t.ball_detected["True"], t.ball_present),
        "ball_is_detected_values": _counts(t.ball_detected),
        # tracking: ball z and ranges
        "pct_ball_z_nonnull": pct(len(zs), t.n_in),
        "z_min": zs[0] if zs else None,
        "z_median": round(median(zs), 2) if zs else None,
        "z_max": zs[-1] if zs else None,
        "z_neg_pct": pct(z_neg, len(zs)),
        "x_min": t.x_min,
        "x_max": t.x_max,
        "y_min": t.y_min,
        "y_max": t.y_max,
        # tracking: keys
        "frame_keys": ",".join(sorted(t.frame_keys)),
        "player_keys": ",".join(sorted(t.player_keys)),
        "ball_keys": ",".join(sorted(t.ball_keys)),
        "possession_keys": ",".join(sorted(t.possession_keys)),
        "corner_keys": ",".join(sorted(t.corner_keys)),
        # ids
        "n_match_players": len(players),
        "n_tracking_ids": len(t.ids),
        "ids_in_players_id": in_id,
        "ids_in_trackable_object": in_to,
        "ids_in_team_player_id": in_tp,
        "tracking_id_key": id_key,
        "possession_id_key": poss_key,
        "events_id_key": ev_key,
        "ev_player_ids_not_in_players": len(unknown),
        "ev_unknown_player_ids": ";".join(str(k) for k in sorted(unknown, key=str)),
        "ev_rows_with_unknown_player": unknown.total(),
        "ball_trackable_object": meta["ball"]["trackable_object"],
        # orientation
        "home_team_side": ";".join(sides),
        "gk_home_mean_x": gk_home,
        "gk_away_mean_x": gk_away,
        "side_check": side_check,
        **_y_sign(events),
        **_xy_frame(events, t.captured),
        "ph_third_label_norm_pct": _phase_thirds(phases),
        # frame-level possession
        "pct_frames_poss_group": pct(t.group_set, t.n_in),
        "pct_frames_poss_player": pct(t.poss_player, t.n_in),
        "poss_group_values": _counts(t.poss_group),
        # events
        "ev_cols": ev_cols,
        "ev_rows": len(events),
        "ev_index_contiguous": [e.idx for e in events] == list(range(len(events))),
        "event_types": _counts(Counter(e.event_type for e in events)),
        "pp_end_types": _counts(end_types),
        "n_shots": end_types["shot"],
        "n_pp_lead_to_shot": sum(e.lead_to_shot for e in pps),
        "ev_time_format": "MM:SS.f",
        "ev_time_format_pct": pct(fmt_ok, len(events)),
        "ev_time_rule_pct": pct(rule_ok, len(events)),
        "ev_time_eq_physical_start_pct": pct(physical.total(), len(events)),
        "ev_time_physical_types": _counts(physical),
        "ev_time_unexplained": time_other,
        # phases vs possessions
        "ph_cols": ph_cols,
        "n_phases": len(phases),
        "n_player_possessions": len(pps),
        "n_phases_without_pp": sum(1 for ph in phases if pp_rows_by_phase[ph.idx] == 0),
        "pct_phases_npp_eq_rows": pct(
            sum(1 for ph in phases if ph.n_pp_in_phase == pp_rows_by_phase[ph.idx]),
            len(phases),
        ),
        "n_tp_first_flags": n_first,
        "n_tp_last_flags": n_last,
        "pct_tp_multi_phase": pct(multi, n_first),
        "n_phase_runs_same_team": runs,
        "n_phases_with_loss": sum(ph.loss for ph in phases),
        "pct_phase_pairs_gap": pct(gaps, pairs),
        "phase_overlaps": overlaps,
        "loss_vs_team_change_mismatch": loss_mismatch,
        "pct_frames_in_phase": pct(t.covered, t.n_in),
        "pct_group_frames_in_phase": pct(t.group_and_covered, t.group_set),
        "pct_group_agrees_phase": pct(t.group_agrees, t.group_and_covered),
    }
    return row


def probe_all(bundles: list[MatchBundle], workers: int) -> list[dict[str, object]]:
    if workers <= 1:
        return [probe_match(b) for b in bundles]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(probe_match, bundles))
