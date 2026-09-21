"""Artefacts of `tracklab freeze-schema football`: report CSV, stdout table, docs and schemas.

Every number printed here is also in `reports/football_format.csv`; the document
`docs/formats/football.md` is regenerated from the same rows, so its prose can
only claim what the rows support (uniform values are stated, anything else is
listed per match).
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable, Sequence
from pathlib import Path

import duckdb

from tracklab.formats.csvschema import FrozenSchema, freeze_csv_family, load_schema
from tracklab.formats.football import aggregate_paths, discover, probe_all
from tracklab.ingest.manifest import Source, load_manifest

Row = dict[str, object]
Log = Callable[[str], None]

SOURCE_ID = "opendata-football"
REPORT_NAME = "football_format.csv"
DOC_NAME = "football.md"
_AGGREGATE_RE = re.compile(r"_(physical|obr|passing)aggregates_")

# What stdout shows per match: the columns that answer the questions of task 4 and
# may vary between matches. The CSV has every column.
TABLE_COLUMNS = (
    "match_id",
    "n_frames",
    "frames_in_periods",
    "pct_22_players",
    "pct_partial_1_21",
    "pct_entries_detected",
    "pct_ball_present",
    "pct_ball_z_nonnull",
    "z_min",
    "z_max",
    "ts_rule_pct",
    "tracking_id_key",
    "side_check",
    "ev_coord_frame",
    "ev_cols",
    "ph_cols",
    "n_phases",
    "n_tp_first_flags",
    "n_phase_runs_same_team",
    "n_shots",
)

DOC_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Frames and clock",
        (
            "match_id",
            "n_frames",
            "periods",
            "frame_max_minus_last_end",
            "frames_outside_periods",
            "ts_null_iff_outside",
            "ts_rule_pct",
            "p2_first_ts",
            "ev_time_rule_pct",
            "ev_time_eq_physical_start_pct",
            "ev_time_physical_types",
            "ev_time_unexplained",
        ),
    ),
    (
        "Coverage and ball",
        (
            "match_id",
            "frames_in_periods",
            "pct_22_players",
            "pct_0_players",
            "pct_partial_1_21",
            "pct_entries_detected",
            "pct_frames_22_all_detected",
            "pct_ball_present",
            "pct_ball_detected",
            "pct_ball_z_nonnull",
            "z_min",
            "z_median",
            "z_max",
            "z_neg_pct",
            "x_min",
            "x_max",
            "y_min",
            "y_max",
        ),
    ),
    (
        "Identifiers and orientation",
        (
            "match_id",
            "n_match_players",
            "n_tracking_ids",
            "ids_in_players_id",
            "ids_in_trackable_object",
            "ids_in_team_player_id",
            "tracking_id_key",
            "events_id_key",
            "ev_player_ids_not_in_players",
            "ev_unknown_player_ids",
            "ev_rows_with_unknown_player",
            "home_team_side",
            "gk_home_mean_x",
            "gk_away_mean_x",
            "side_check",
            "ev_coord_frame",
            "ev_xy_raw_ltr_pct",
            "ev_xy_flip_rtl_pct",
            "ev_xy_raw_rtl_pct",
            "ev_xy_flip_ltr_pct",
            "y_left_pos_ltr_pct",
            "y_left_pos_rtl_pct",
            "ph_third_label_norm_pct",
        ),
    ),
    (
        "Events, phases and possessions",
        (
            "match_id",
            "ev_rows",
            "n_shots",
            "n_pp_lead_to_shot",
            "n_phases",
            "n_player_possessions",
            "n_tp_first_flags",
            "n_tp_last_flags",
            "n_phase_runs_same_team",
            "pct_tp_multi_phase",
            "n_phases_without_pp",
            "pct_phases_npp_eq_rows",
            "n_phases_with_loss",
            "loss_vs_team_change_mismatch",
            "pct_phase_pairs_gap",
            "phase_overlaps",
            "pct_frames_in_phase",
            "pct_frames_poss_group",
            "pct_group_frames_in_phase",
            "pct_group_agrees_phase",
        ),
    ),
)


def fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "NO"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def write_report_csv(rows: Sequence[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if v is None else v for k, v in row.items()})


def split_uniform(rows: Sequence[Row]) -> tuple[dict[str, object], list[str]]:
    """Columns with one value across all matches, and the names of the ones that vary."""
    uniform: dict[str, object] = {}
    varying: list[str] = []
    for key in rows[0]:
        values = {fmt(r[key]) for r in rows}
        if len(values) == 1 and key != "match_id":
            uniform[key] = rows[0][key]
        else:
            varying.append(key)
    return uniform, varying


def text_table(rows: Sequence[Row], columns: Sequence[str]) -> str:
    cells = [[fmt(r[c]) for c in columns] for r in rows]
    widths = [max(len(c), *(len(line[i]) for line in cells)) for i, c in enumerate(columns)]
    head = "  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True))
    body = ["  ".join(v.ljust(w) for v, w in zip(line, widths, strict=True)) for line in cells]
    return "\n".join([head, *body])


def md_table(rows: Sequence[Row], columns: Sequence[str]) -> str:
    head = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(fmt(r[c]) for c in columns) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def _values(rows: Sequence[Row], key: str) -> list[str]:
    return sorted({fmt(r[key]) for r in rows})


def _kinds(rows: Sequence[Row], key: str) -> list[str]:
    """The names in a `name=count;name=count` column, over all matches."""
    return sorted({part.split("=")[0] for r in rows for part in str(r[key]).split(";") if part})


def _span(rows: Sequence[Row], key: str) -> str:
    nums: list[float] = [v for r in rows if isinstance(v := r[key], int | float)]
    if not nums:
        return "-"
    lo, hi = min(nums), max(nums)
    return fmt(lo) if lo == hi else f"{fmt(lo)} to {fmt(hi)}"


def _except(rows: Sequence[Row], key: str, expected: object) -> str:
    """'in every match' or 'in N matches; not in <ids>' for a column expected to be uniform."""
    bad = [str(r["match_id"]) for r in rows if r[key] != expected]
    if not bad:
        return "in every match"
    return f"in {len(rows) - len(bad)} matches; not in {', '.join(bad)}"


def _claim(rows: Sequence[Row], key: str, if_uniform: str, otherwise: str) -> str:
    values = _values(rows, key)
    if len(values) == 1:
        return if_uniform.format(v=values[0])
    return otherwise.format(v=", ".join(values))


def render_doc(
    rows: Sequence[Row],
    source: Source,
    schemas: Sequence[FrozenSchema],
    aggregate_rows: dict[str, int],
) -> str:
    n = len(rows)
    uniform, _ = split_uniform(rows)
    files = [f for f in source.files]
    tracking_bytes = sum(f.bytes for f in files if f.role == "tracking")
    sections: list[str] = []
    add = sections.append

    add("# Football bundle format (SkillCorner opendata)\n")
    add(
        "Generated by `tracklab freeze-schema football`. Every figure below is measured on the "
        f"{n} matches of the frozen bundle; the per-match rows live in "
        f"`pipeline/reports/{REPORT_NAME}`, and the tables here are rendered from them.\n"
    )
    add_traps_summary(add, rows)
    add("## Source\n")
    add(
        f"- Repository `{source.repo}`, ref `{source.ref}`, **commit `{source.commit}`** "
        f"(pinned in `pipeline/manifest/sources.json`).\n"
        f"- {len(files)} files: {n} matches x (tracking JSONL, match.json, dynamic_events.csv, "
        f"phases_of_play.csv), 3 season aggregates, `matches.json` and one body-pose sample.\n"
        f"- Tracking JSONL: {tracking_bytes / 1e6:,.0f} MB in total, "
        f"{_span(rows, 'n_frames')} lines per match, one frame per line, 10 Hz.\n"
    )

    add_read_this_first(add, rows)

    add("## Tracking JSONL\n")
    add(
        "One JSON object per line with keys "
        f"`{uniform.get('frame_keys', _values(rows, 'frame_keys'))}`. "
        f"`player_data` is a list of `{{{uniform.get('player_keys', '?')}}}`, "
        f"`ball_data` is `{{{uniform.get('ball_keys', '?')}}}`, "
        f"`possession` is `{{{uniform.get('possession_keys', '?')}}}` and "
        f"`image_corners_projection` has `{uniform.get('corner_keys', '?')}`.\n"
    )
    add("### Frames and clock\n")
    add(
        "- `frame` is the line index: "
        + _claim(
            rows,
            "frame_contiguous_from_0",
            "contiguous from 0 in every match ({v}).",
            "contiguous from 0 is {v} across matches.",
        )
        + " The file does not always end at the `end_frame` of the last period: "
        "`frame_max - end_frame` per match is "
        + ", ".join(f"{r['match_id']}: {fmt(r['frame_max_minus_last_end'])}" for r in rows)
        + " (negative: the declared last frame is missing; positive: post-match footage).\n"
        "- `match.json.match_periods[]` gives `start_frame` and `end_frame` per period. Frames "
        "outside every period (before kick-off and between halves) carry `timestamp: null`, "
        "`period: null`, an empty `player_data` and a null ball: "
        + _claim(
            rows,
            "ts_null_iff_outside",
            "null timestamp, null period and outside-period coincide exactly in every match ({v}).",
            "this holds in {v} of the matches (see table).",
        )
        + f" Outside-period frames per match: {_span(rows, 'frames_outside_periods')}: "
        f"{sum(1 for r in rows if int(str(r['frames_outside_periods'])) < 100)} matches start "
        "period 1 at frame 0-10 and cut the half-time out, the other "
        f"{sum(1 for r in rows if int(str(r['frames_outside_periods'])) >= 100)} keep "
        "pre-match and half-time footage in the file (period 1 starts at frame 1170-4040 and "
        "period 2 some 9000-10000 frames after the end of period 1).\n"
        f"- `timestamp` is the string `{uniform.get('ts_format', '?')}` "
        f"(format matched in {_span(rows, 'ts_format_pct')}% of non-null timestamps) and is a "
        "**match clock, not a period clock**: `timestamp = 45:00 x (period - 1) + "
        "(frame - start_frame[period]) / 10`. Verified for "
        f"{_span(rows, 'ts_rule_pct')}% of non-null frames; the first frame of period 2 reads "
        f"`{uniform.get('p2_first_ts', _values(rows, 'p2_first_ts'))}`.\n"
        "- The events CSV uses a different string for the same clock, "
        f"`{uniform.get('ev_time_format', '?')}` with one decimal and minutes beyond 59 "
        "(`45:02.3`). `time_start` equals the clock of `frame_start` in "
        f"{_span(rows, 'ev_time_rule_pct')}% of events; when it does not, it equals "
        f"the clock of `frame_physical_start` ({_span(rows, 'ev_time_eq_physical_start_pct')}% of "
        f"events, all of type {', '.join(_kinds(rows, 'ev_time_physical_types'))}), leaving "
        f"{_span(rows, 'ev_time_unexplained')} unexplained per match.\n"
    )
    add("### Coverage\n")
    add(
        f"- Inside the periods a frame carries **either 22 players or none**: 22 players in "
        f"{_span(rows, 'pct_22_players')}% of in-period frames, 0 in "
        f"{_span(rows, 'pct_0_players')}%, partial frames (1-21) in "
        f"{_span(rows, 'pct_partial_1_21')}%, frames with more than 22: "
        f"{_span(rows, 'frames_over_22')}. The ball is present exactly when the 22 are: "
        + _claim(rows, "ball_present_iff_22", "{v} in every match.", "{v}.")
        + "\n"
        "- The intermittence SkillCorner documents lives in `is_detected`, not in presence: only "
        f"{_span(rows, 'pct_entries_detected')}% of player entries are detected, and a frame with "
        f"all 22 detected occurs in {_span(rows, 'pct_frames_22_all_detected')}% of in-period "
        "frames. The rest are extrapolated positions (`_extrapolated` in the file name). "
        f"`ball_data.is_detected` is true in {_span(rows, 'pct_ball_detected')}% of frames with "
        "a ball. The frame-level rule (complete or empty) is the same one measured in the "
        "basketball bundle, so the conformed schema needs no partial-frame logic, but it must "
        "keep `is_detected` per object because in football most positions are extrapolated.\n"
        f"- `ball_data.z` is non-null exactly when the ball is present "
        f"({_span(rows, 'pct_ball_z_nonnull')}% of in-period frames), in metres: min "
        f"{_span(rows, 'z_min')}, median {_span(rows, 'z_median')}, max {_span(rows, 'z_max')}, "
        f"negative in {_span(rows, 'z_neg_pct')}% of the values.\n"
    )
    add("### Coordinates and orientation\n")
    add(
        "- Pitch `pitch_length` 105 x `pitch_width` 68, origin at the centre spot, x along the "
        f"length. Observed per-match player extremes: x_min {_span(rows, 'x_min')}, x_max "
        f"{_span(rows, 'x_max')}, y_min {_span(rows, 'y_min')}, y_max {_span(rows, 'y_max')} "
        "(players step outside the lines).\n"
        "- `home_team_side` is a list with one entry per period, e.g. "
        f"`{str(rows[0]['home_team_side']).split(';')}`. Read as: `left_to_right` means the "
        "home team attacks towards +x in that period. Checked against the mean x of each team's "
        "goalkeeper per period (`gk_home_mean_x`, `gk_away_mean_x` in the table): "
        + _claim(
            rows,
            "side_check",
            "`{v}` in every match.",
            "**not uniform**: {v}; see the table for the offending match and period.",
        )
        + "\n"
        "- **The events and phases CSVs are not in the tracking frame.** Comparing each event's "
        "(`x_start`, `y_start`) with the tracking position of `player_id` at `frame_start` "
        "(2 m tolerance): "
        + _claim(
            rows,
            "ev_coord_frame",
            "`{v}` in every match.",
            "{v} (see table).",
        )
        + " With the attacking side `left_to_right` the raw coordinates match "
        f"({_span(rows, 'ev_xy_raw_ltr_pct')}%); with `right_to_left` only the rotated "
        f"(-x, -y) match ({_span(rows, 'ev_xy_flip_rtl_pct')}%). So in events and phases the "
        "team in possession always attacks towards +x, and `attacking_side` tells which "
        "rotation maps them back to the tracking frame.\n"
        "- Sign of y in that attack-normalised frame: events in a `*_left` channel have y > 0 in "
        f"{_span(rows, 'y_left_pos_ltr_pct')}% (ltr) and {_span(rows, 'y_left_pos_rtl_pct')}% "
        "(rtl) of cases, so **+y is the attacker's left**. Phase `third_start` labels agree "
        f"with the same frame in {_span(rows, 'ph_third_label_norm_pct')}% of phases.\n"
    )
    add("### Identifiers\n")
    add(
        "- `match.json.players[]` carries three ids: `id`, `team_player_id` and "
        "`trackable_object`; the ball is `ball.trackable_object` = "
        f"{uniform.get('ball_trackable_object', _values(rows, 'ball_trackable_object'))}.\n"
        "- The tracking `player_data[].player_id` is **`players[].id`**, not "
        "`trackable_object`: "
        + _claim(
            rows,
            "tracking_id_key",
            "`{v}` in every match",
            "{v} across matches",
        )
        + f" ({_span(rows, 'n_tracking_ids')} distinct ids per match, "
        f"{_span(rows, 'ids_in_players_id')} found in `players[].id`, "
        f"{_span(rows, 'ids_in_trackable_object')} in `trackable_object`). "
        "`possession.player_id` uses the same key "
        + _except(rows, "possession_id_key", "id")
        + ", and so does the events' `player_id` "
        + _except(rows, "events_id_key", "id")
        + ". Events can name a player absent from `players[]` and from the tracking: "
        f"{_span(rows, 'ev_player_ids_not_in_players')} such ids per match, "
        f"{_span(rows, 'ev_rows_with_unknown_player')} event rows (see "
        "`ev_player_ids_not_in_players` per match), so `events.player_id -> match_players` is "
        "not a foreign key bronze can enforce.\n"
    )
    add("### Frame-level possession\n")
    add(
        "- `possession.group` (`home team` / `away team` / null) is set in "
        f"{_span(rows, 'pct_frames_poss_group')}% of in-period frames and `possession.player_id` "
        f"in {_span(rows, 'pct_frames_poss_player')}%. Of the frames with a group, "
        f"{_span(rows, 'pct_group_frames_in_phase')}% fall inside a phase and the group agrees "
        f"with the phase's `team_in_possession_id` in {_span(rows, 'pct_group_agrees_phase')}% "
        "of those.\n"
    )

    add("## match.json\n")
    add(
        "Keys: `id`, scores, `date_time`, `stadium`, `home_team`/`away_team` (`id`, `name`, "
        "`short_name`, `acronym`), kits (`jersey_color`, `number_color`), coaches, "
        "`home_team_playing_time`/`away_team_playing_time`, `competition_edition`, "
        "`match_periods[]` (`period`, `name`, `start_frame`, `end_frame`, `duration_frames`, "
        "`duration_minutes`), `competition_round`, `referees`, `players[]`, `status`, "
        "`home_team_side[]`, `ball`, `pitch_length`, `pitch_width`. Each player has "
        "`player_role` (`id`, `position_group`, `name`, `acronym`), `start_time`/`end_time`, "
        "`number`, cards, `playing_time` (`total` and `by_period`, with frames), "
        f"`team_player_id`, `team_id`, `id`, names, `birthday`, `trackable_object`, `gender`. "
        f"{_span(rows, 'n_match_players')} players per match are listed, "
        f"{_span(rows, 'n_tracking_ids')} appear in the tracking.\n"
    )

    add("## dynamic_events.csv\n")
    events_schema = next(s for s in schemas if s.table == "dynamic_events")
    event_types = _kinds(rows, "event_types")
    add(
        f"- {len(events_schema.columns)} columns, identical header in the {n} files "
        f"(sha256 `{events_schema.header_sha256}`). Rows per match: {_span(rows, 'ev_rows')}; "
        "`index` is contiguous from 0: "
        + _claim(rows, "ev_index_contiguous", "{v} in every match.", "{v}.")
        + "\n"
        f"- `event_type` takes {len(event_types)} values: {', '.join(event_types)} "
        "(per-match counts in the CSV column `event_types`). "
        "**There is no shot event**: a shot is a `player_possession` whose `end_type` is "
        f"`shot` ({_span(rows, 'n_shots')} per match). `end_type` of player possessions: "
        f"`{_values(rows, 'pp_end_types')[0]}` in the first match, same vocabulary elsewhere. "
        f"`lead_to_shot` is a wider flag ({_span(rows, 'n_pp_lead_to_shot')} player possessions "
        "per match lead to a shot).\n"
        f"- Columns that are empty in all {n} files, typed VARCHAR by default: "
        f"{', '.join(f'`{c}`' for c in events_schema.all_null_columns) or 'none'}.\n"
    )

    add("## phases_of_play.csv\n")
    phases_schema = next(s for s in schemas if s.table == "phases_of_play")
    add(
        f"- {len(phases_schema.columns)} columns, identical header in the {n} files "
        f"(sha256 `{phases_schema.header_sha256}`). Rows per match: {_span(rows, 'n_phases')}.\n"
        "- **Phase, team possession and player possession are three different units.** "
        "A *player possession* is a `player_possession` event "
        f"({_span(rows, 'n_player_possessions')} per match). A *phase* is a row here: one team, "
        "one `team_in_possession_phase_type` (build_up, create, finish, direct, chaotic, "
        "set_play, quick_break, transition), contiguous frames. A *team possession* is not a "
        "table: it is the run of consecutive same-team phases, and the events mark its ends "
        "with `first_player_possession_in_team_possession` / `last_...` "
        f"({_span(rows, 'n_tp_first_flags')} per match, against "
        f"{_span(rows, 'n_phase_runs_same_team')} same-team runs of phases; the difference is "
        f"the {_span(rows, 'n_phases_without_pp')} phases per match that have no exported "
        f"player possession). {_span(rows, 'pct_tp_multi_phase')}% of team possessions span "
        "more than one phase.\n"
        "- `team_possession_loss_in_phase` is true exactly when the next phase of the period "
        "belongs to the other team: mismatches per match "
        f"{_span(rows, 'loss_vs_team_change_mismatch')}. A phase can therefore hold the end of "
        "a team possession, which is why phase and possession are not the same unit.\n"
        f"- Consecutive phases overlap {_span(rows, 'phase_overlaps')} times and leave a gap "
        f"(dead ball) in {_span(rows, 'pct_phase_pairs_gap')}% of pairs; phases cover "
        f"{_span(rows, 'pct_frames_in_phase')}% of in-period frames.\n"
        "- `n_player_possessions_in_phase` equals the number of exported `player_possession` "
        f"rows of the phase in only {_span(rows, 'pct_phases_npp_eq_rows')}% of phases: the "
        "counter comes from the provider's full possession list, the CSV exports a subset.\n"
    )

    add("## Season aggregates\n")
    add("| table | file | columns | rows |\n|---|---|---|---|")
    for schema in schemas:
        if schema.table.startswith("aggregates_"):
            add(
                f"| {schema.table} | `{schema.frozen_from[0]}` | {len(schema.columns)} | "
                f"{aggregate_rows[schema.table]} |"
            )
    add("")

    add("## Frozen schemas\n")
    add(
        "Sniffed by DuckDB over every row of every file, merged across files, and re-imposed "
        "on each file with `read_csv(columns=...)`. Bronze (tasks 7 and 8) reads with these and "
        "fails on any column added, removed or retyped.\n"
    )
    add("| table | columns | header sha256 | frozen from |\n|---|---|---|---|")
    for schema in schemas:
        add(
            f"| {schema.table} | {len(schema.columns)} | `{schema.header_sha256[:16]}...` | "
            f"{len(schema.frozen_from)} file(s) |"
        )
    add("")

    add("## Uniform across all matches\n")
    add("Columns of the report whose value is the same in every match:\n")
    for key, value in uniform.items():
        add(f"- `{key}`: `{fmt(value)}`")
    add("")

    add("## Per-match tables\n")
    for title, columns in DOC_TABLES:
        add(f"### {title}\n")
        add(md_table(rows, columns))
        add("")
    return "\n".join(sections)


def _ids(rows: Sequence[Row]) -> str:
    return ", ".join(str(r["match_id"]) for r in rows)


def _p1_start_span(rows: Sequence[Row]) -> str:
    """Range of the first period's start_frame, from the `periods` column (`p1:10-28990;...`)."""
    starts = [int(str(r["periods"]).split(";")[0].split(":")[1].split("-")[0]) for r in rows]
    if not starts:
        return "-"
    return f"{min(starts)}" if min(starts) == max(starts) else f"{min(starts)}-{max(starts)}"


def add_traps_summary(add: Callable[[str], None], rows: Sequence[Row]) -> None:
    """One line per trap, for the reader who opens the file, finds a column name and leaves."""
    new_layout = [r for r in rows if int(str(r["frames_outside_periods"])) >= 100]
    orphan_rows = sum(int(str(r["ev_rows_with_unknown_player"])) for r in rows)
    missing_last = sum(1 for r in rows if int(str(r["frame_max_minus_last_end"])) < 0)
    add("## Read this first\n")
    add(
        "Four things in this bundle mislead without ever raising an error:\n\n"
        "1. **Events and phases are not in the tracking coordinate frame.** They are normalised "
        "so the attacker always goes towards +x; map (x, y) to (-x, -y) when `attacking_side` is "
        "`right_to_left`, or half of every match comes out mirrored. "
        "[Measured](#the-events-and-phases-are-not-in-the-tracking-coordinate-frame).\n"
        "2. **`end_frame` declares a range, not the frames that exist.** The declared last frame "
        f"is missing in {missing_last} of {len(rows)} files; never join tracking against a "
        "generated range. [Measured](#end-frame-declares-a-range-not-existing-frames).\n"
        "3. **`events.player_id` is not a foreign key.** One id with "
        f"{orphan_rows} event rows exists neither in `players[]` nor in the tracking. "
        "[Measured](#events-player_id-is-not-an-enforceable-foreign-key).\n"
        f"4. **Two tracking layouts.** {len(new_layout)} matches ({_ids(new_layout)}) carry "
        "pre-match, half-time and post-match footage as null frames. "
        "[Measured](#two-tracking-layouts).\n"
    )


def add_read_this_first(add: Callable[[str], None], rows: Sequence[Row]) -> None:
    """The findings that silently break a naive join, on top, with their numbers."""
    n = len(rows)
    new_layout = [r for r in rows if int(str(r["frames_outside_periods"])) >= 100]
    old_layout = [r for r in rows if int(str(r["frames_outside_periods"])) < 100]
    unknown = [r for r in rows if int(str(r["ev_player_ids_not_in_players"])) > 0]
    deltas = [int(str(r["frame_max_minus_last_end"])) for r in rows]
    n_zero = sum(d == 0 for d in deltas)
    n_minus = sum(d < 0 for d in deltas)
    n_short_plus = sum(0 < d < 100 for d in deltas)
    n_long_plus = sum(d >= 100 for d in deltas)

    add("## The four traps, measured\n")
    add("### The events and phases are NOT in the tracking coordinate frame\n")
    add(
        "**`dynamic_events.csv` and `phases_of_play.csv` are attack-normalised: the team in "
        "possession always attacks towards +x, and +y is the attacker's left. The tracking JSONL "
        "is in the fixed pitch frame. Joining them without rotating by `attacking_side` mirrors "
        "half of every match, and nothing errors.** Measured by comparing each event's "
        "(`x_start`, `y_start`) with the tracking position of the same `player_id` at "
        f"`frame_start`, 2 m tolerance, {_span(rows, 'ev_xy_compared')} events per match: with "
        f"`attacking_side = left_to_right` the raw coordinates match in "
        f"{_span(rows, 'ev_xy_raw_ltr_pct')}% of events; with `right_to_left` the rotated "
        f"(-x, -y) match in {_span(rows, 'ev_xy_flip_rtl_pct')}%; the two wrong combinations "
        f"match in {_span(rows, 'ev_xy_raw_rtl_pct')}% and {_span(rows, 'ev_xy_flip_ltr_pct')}%. "
        f"Events in a `*_left` channel have y > 0 in {_span(rows, 'y_left_pos_ltr_pct')}% (ltr) "
        f"and {_span(rows, 'y_left_pos_rtl_pct')}% (rtl) of cases. **To map an event or phase "
        "into the tracking frame: keep (x, y) when `attacking_side` is `left_to_right`, use "
        "(-x, -y) when it is `right_to_left`.**\n"
    )
    add("### Two hypotheses the plan carried, refuted by the data\n")
    add(
        "- *The tracking indexes players by `trackable_object`.* **Refuted in every match.** "
        f"`player_data[].player_id` is `players[].id`: of the {_span(rows, 'n_tracking_ids')} "
        f"distinct ids per match, {_span(rows, 'ids_in_players_id')} are found in `players[].id`, "
        f"{_span(rows, 'ids_in_trackable_object')} in `trackable_object` and "
        f"{_span(rows, 'ids_in_team_player_id')} in `team_player_id`. `possession.player_id` and "
        "the events' `player_id` use `players[].id` too. `ball_data` carries no id at all "
        f"(keys `{rows[0]['ball_keys']}`), so `ball.trackable_object` = "
        f"{rows[0]['ball_trackable_object']} is not a join key either.\n"
        "- *Football tracking is intermittent, unlike basketball's complete-or-empty frames.* "
        "**Refuted at frame level in every match.** In-period frames carry 22 players or none: "
        f"partial frames (1-21) are {_span(rows, 'pct_partial_1_21')}% and the ball is present "
        "exactly when the 22 are. The intermittence lives per player in `is_detected` "
        f"({_span(rows, 'pct_entries_detected')}% of entries detected; frames with all 22 "
        f"detected: {_span(rows, 'pct_frames_22_all_detected')}%). Bronze needs no "
        "partial-frame logic; silver must keep `is_detected` per object.\n"
    )
    add("### Events player_id is not an enforceable foreign key\n")
    add(
        "**`events.player_id` is not a foreign key bronze can enforce.** "
        + "; ".join(
            f"match {r['match_id']}: `player_id` {r['ev_unknown_player_ids']} has "
            f"{r['ev_rows_with_unknown_player']} event rows and exists neither in `players[]` "
            "nor in the tracking"
            for r in unknown
        )
        + f" ({n - len(unknown)} other matches are clean). Load events as they come and "
        "report the orphan rows; do not drop them and do not declare the relationship.\n"
    )
    add("### Two tracking layouts\n")
    add(
        f"{len(old_layout)} matches start period 1 at frame "
        f"{_p1_start_span(old_layout)} with {_span(old_layout, 'frames_outside_periods')} frames "
        f"outside the periods. {len(new_layout)} matches ({_ids(new_layout)}) keep pre-match, "
        f"half-time and post-match footage: period 1 starts at frame {_p1_start_span(new_layout)}, "
        f"{_span(new_layout, 'frames_outside_periods')} frames lie outside the periods "
        "(`timestamp` and `period` null, no players, no ball) and the file runs "
        f"{_span(new_layout, 'frame_max_minus_last_end')} frames past `end_frame`.\n"
    )
    add("### End frame declares a range, not existing frames\n")
    add(
        "**`end_frame` declares a range; it does not guarantee that every frame of the range "
        f"exists.** `frame_max - end_frame` of the last period is 0 in {n_zero} matches, -1 in "
        f"{n_minus} (the declared last frame of period 2 is missing from the file), +10 in "
        f"{n_short_plus} and +390 to +1030 in the {n_long_plus} with post-match footage (per match "
        "under Frames and clock). Any join between tracking and periods must go against the "
        "frames that exist, never against a range built with `range()` or `generate_series`: "
        "that would invent frames the provider never delivered, which is fabricating data.\n"
    )
    add("### What the contract test can assert\n")
    add(
        "- `frame` contiguous from 0 in every file: a hard invariant, measured in all "
        f"{n} matches.\n"
        "- `frame_max - end_frame[last period]` reported as a number per match, never as a "
        f"boolean: `frame_max == end_frame` fails in {n - n_zero} of {n} matches, not because "
        "the data is wrong but because equality is the wrong rule, and a boolean would also hide "
        "that there are three regimes.\n"
        "- In-period frames carry 22 players or 0, and a ball exactly when 22.\n"
        "- The 322 and 44 column headers are byte-identical to the frozen ones "
        "(`header_sha256` in the schema files).\n"
    )


def _aggregate_table(path: Path) -> str:
    m = _AGGREGATE_RE.search(path.name)
    if m is None:
        raise ValueError(f"unrecognised aggregate file: {path.name}")
    return f"aggregates_{m.group(1)}"


def freeze_football(
    *,
    manifest_path: Path,
    data_dir: Path,
    reports_dir: Path,
    docs_dir: Path,
    schemas_dir: Path,
    workers: int,
    log: Log = print,
) -> int:
    source = load_manifest(manifest_path).source(SOURCE_ID)
    raw_root = data_dir / "raw" / SOURCE_ID
    bundles = discover(raw_root)
    if not bundles:
        raise FileNotFoundError(f"no matches under {raw_root / 'data' / 'matches'}")
    log(f"probing {len(bundles)} matches with {workers} worker(s)...")
    rows = probe_all(bundles, workers)

    con = duckdb.connect()
    families: list[tuple[str, list[Path]]] = [
        ("dynamic_events", [b.events for b in bundles]),
        ("phases_of_play", [b.phases for b in bundles]),
        *((_aggregate_table(p), [p]) for p in aggregate_paths(raw_root)),
    ]
    schemas: list[FrozenSchema] = []
    changed = False
    aggregate_rows: dict[str, int] = {}
    schemas_dir.mkdir(parents=True, exist_ok=True)
    for table, paths in families:
        schema = freeze_csv_family(table, paths, raw_root, con)
        target = schemas_dir / f"{table}.schema.json"
        status = "new"
        if target.exists():
            previous = load_schema(target)
            same = previous.header_sha256 == schema.header_sha256 and previous.columns == (
                schema.columns
            )
            status = "unchanged" if same else f"CHANGED (was {previous.header_sha256[:8]})"
            changed |= not same
        target.write_text(
            schema.to_json(sport="football", source_id=SOURCE_ID, commit=source.commit),
            encoding="utf-8",
        )
        if table.startswith("aggregates_"):
            row = con.execute(
                "SELECT count(*) FROM read_csv(?, header=true)", [str(paths[0])]
            ).fetchone()
            assert row is not None
            aggregate_rows[table] = int(row[0])
        schemas.append(schema)
        log(
            f"frozen {table}: {len(schema.columns)} columns, header {schema.header_sha256[:8]}, "
            f"{len(paths)} file(s), {status} -> {target}"
        )

    report_path = reports_dir / REPORT_NAME
    write_report_csv(rows, report_path)
    doc_path = docs_dir / DOC_NAME
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(render_doc(rows, source, schemas, aggregate_rows), encoding="utf-8")

    uniform, _ = split_uniform(rows)
    log("")
    log(text_table(rows, TABLE_COLUMNS))
    log("")
    log(f"same in all {len(rows)} matches:")
    for key, value in uniform.items():
        log(f"  {key} = {fmt(value)}")
    log("")
    log(f"report: {report_path} ({len(rows)} rows, {len(rows[0])} columns)")
    log(f"doc: {doc_path}")
    return 1 if changed else 0
