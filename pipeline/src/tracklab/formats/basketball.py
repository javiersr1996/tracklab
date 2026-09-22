"""Freeze the shape of the opendata-basketball bundle: 20 event families plus the
3 season aggregates, `reports/basketball_format.csv` and `docs/formats/basketball.md`.

`tracklab freeze-schema basketball` is the only place bronze events sniffs the raw
JSON: it reads the 10 `dynamic_events.json` whole (the largest raw file of this task
is 3.5 MB, so this stays comfortably in memory) and, per family, infers one type per
key from the union of all 10 matches. Bronze then only IMPOSES the frozen
`*.schema.json`: a key of more, of less, or a value that does not cast fails the run
naming the file and the key, exactly as `bronze/basketball/tracking.py` does for the
tracking frames. The 3 aggregates reuse `formats.csvschema.freeze_csv_family` as is.

Type vocabulary (closed): BIGINT, DOUBLE, BOOLEAN, VARCHAR, LIST<BIGINT>,
LIST<VARCHAR>, POINT2D. Inference rules, applied over the union of the 10 matches:

- ``bool`` -> BOOLEAN, ``int`` -> BIGINT, ``float`` -> DOUBLE, ``str`` -> VARCHAR.
  ``bool`` is measured before ``int``: it is a subclass of it in Python.
- a list of ``int`` -> LIST<BIGINT>; a list of ``str`` -> LIST<VARCHAR>; a list that is
  always exactly 2 floats when present -> POINT2D, later opened into two DOUBLE
  columns ``<key>_x``/``<key>_y`` by ``pa_schema`` below (shared by the bronze builder
  and the contract test): per-axis statistics, predicate pushdown, and silver reads it
  without unnesting, the same reason ``xyz`` was split in tracking.
- a key that is always null, a list that is always empty everywhere in the bundle, or
  a key with two distinct non-null types fails the freeze, naming the family and the
  key. None of the three happens in this bundle; the failure is the safety net for the
  next bundle that does.
- ``nullable`` is observed, never guessed: a key that is never null across the 10
  matches is declared NOT NULL.
- ``closeouts.touchWallClock`` is delivered as a numeric string; it is stored BIGINT,
  and the frozen `.schema.json` records both ``source_type`` (VARCHAR) and ``type``
  (BIGINT) so the cast is documented in the artefact itself, not only in
  ``_CAST_OVERRIDES`` below.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import duckdb
import pyarrow as pa

from tracklab.bronze.common import LINEAGE_FIELDS, raw_root_for
from tracklab.formats.csvschema import FrozenSchema, freeze_csv_family, header_names
from tracklab.ingest.manifest import FileEntry, Source, load_manifest

Row = dict[str, object]
Log = Callable[[str], None]
SPORT = "basketball"
SOURCE_ID = "opendata-basketball"
REPORT_NAME = "basketball_format.csv"
DOC_NAME = "basketball.md"
# Marks where this task's section of the doc starts, so a rerun replaces exactly that
# section and task 5's tracking write-up (above the marker) is never touched.
_DOC_MARKER = "<!-- tracklab:freeze-schema-basketball:generated-below -->"

# The 20 keys of `dynamic_events.json`, in the order the provider delivers them.
# Identical set and order in the 10 matches (checked by `load_events`).
FAMILY_ORDER: tuple[str, ...] = (
    "chances",
    "possessions",
    "shots",
    "rebounds",
    "turnovers",
    "free_throws",
    "fouls",
    "timeouts",
    "passes",
    "touches",
    "dribbles",
    "picks",
    "isolations",
    "handoffs",
    "drives",
    "posts",
    "off_ball_screens",
    "closeouts",
    "chance_players",
    "matchups",
)

AGGREGATE_FAMILIES: tuple[str, ...] = ("shots", "drives", "picks")

# Cast overrides: (family, key) -> stored type. Applied after the raw type is
# inferred, which becomes `source_type` in the frozen column.
_CAST_OVERRIDES: dict[tuple[str, str], str] = {("closeouts", "touchWallClock"): "BIGINT"}

SCALAR_PA_TYPES: dict[str, pa.DataType] = {
    "BIGINT": pa.int64(),
    "DOUBLE": pa.float64(),
    "BOOLEAN": pa.bool_(),
    "VARCHAR": pa.string(),
    "LIST<BIGINT>": pa.list_(pa.int64()),
    "LIST<VARCHAR>": pa.list_(pa.string()),
}


@dataclass(frozen=True)
class FrozenColumn:
    name: str
    type: str
    nullable: bool
    source_type: str | None = None


@dataclass(frozen=True)
class FrozenFamily:
    table: str
    family: str
    sport: str
    source_id: str
    commit: str
    n_keys: int
    keys_sha256: str
    frozen_from: tuple[str, ...]
    rows_read: int
    columns: tuple[FrozenColumn, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    def to_json(self) -> str:
        payload: dict[str, object] = {
            "table": self.table,
            "family": self.family,
            "sport": self.sport,
            "source_id": self.source_id,
            "commit": self.commit,
            "n_keys": self.n_keys,
            "keys_sha256": self.keys_sha256,
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    **({"source_type": c.source_type} if c.source_type else {}),
                }
                for c in self.columns
            ],
            "frozen_from": list(self.frozen_from),
            "rows_read": self.rows_read,
        }
        return json.dumps(payload, indent=2) + "\n"


def load_family(path: Path) -> FrozenFamily:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return FrozenFamily(
        table=raw["table"],
        family=raw["family"],
        sport=raw["sport"],
        source_id=raw["source_id"],
        commit=raw["commit"],
        n_keys=raw["n_keys"],
        keys_sha256=raw["keys_sha256"],
        frozen_from=tuple(raw["frozen_from"]),
        rows_read=raw["rows_read"],
        columns=tuple(
            FrozenColumn(c["name"], c["type"], c["nullable"], c.get("source_type"))
            for c in raw["columns"]
        ),
    )


def pa_schema(frozen: FrozenFamily) -> pa.Schema:
    """The Parquet schema of `events_<family>`: lineage, then the frozen columns in
    provider order, POINT2D opened into `<key>_x`/`<key>_y`. Shared by the bronze
    builder and the contract test so the two never drift apart."""
    fields = list(LINEAGE_FIELDS)
    for column in frozen.columns:
        if column.type == "POINT2D":
            fields.append(pa.field(f"{column.name}_x", pa.float64(), nullable=column.nullable))
            fields.append(pa.field(f"{column.name}_y", pa.float64(), nullable=column.nullable))
        else:
            fields.append(
                pa.field(column.name, SCALAR_PA_TYPES[column.type], nullable=column.nullable)
            )
    return pa.schema(fields)


_SCALAR_STORED_TYPES = {"bool": "BOOLEAN", "int": "BIGINT", "float": "DOUBLE", "str": "VARCHAR"}


def _kind(value: object) -> str:
    # bool before int: bool is a subclass of int in Python.
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    raise ValueError(f"unsupported JSON value type {type(value).__name__}: {value!r}")


def _infer_list(family: str, key: str, non_null: list[Any]) -> str:
    lengths = {len(v) for v in non_null}
    elem_kinds = {_kind(e) for v in non_null for e in v}
    if not elem_kinds:
        raise ValueError(f"{family}.{key}: list is always empty across the bundle")
    if len(elem_kinds) > 1:
        raise ValueError(f"{family}.{key}: list elements have distinct types {sorted(elem_kinds)}")
    elem_kind = elem_kinds.pop()
    if elem_kind == "int":
        return "LIST<BIGINT>"
    if elem_kind == "str":
        return "LIST<VARCHAR>"
    if elem_kind == "float" and lengths - {0} == {2}:
        return "POINT2D"
    if elem_kind == "float":
        raise ValueError(f"{family}.{key}: float list lengths {sorted(lengths)}, POINT2D needs 2")
    raise ValueError(f"{family}.{key}: unsupported list element type {elem_kind}")


def _infer_column(family: str, key: str, values: list[Any]) -> FrozenColumn:
    non_null = [v for v in values if v is not None]
    nullable = len(non_null) != len(values)
    if not non_null:
        raise ValueError(f"{family}.{key}: always null across the bundle")
    kinds = {_kind(v) for v in non_null}
    if len(kinds) > 1:
        raise ValueError(f"{family}.{key}: distinct non-null types {sorted(kinds)}")
    kind = kinds.pop()
    stored = _infer_list(family, key, non_null) if kind == "list" else _SCALAR_STORED_TYPES[kind]
    source_type = None
    override = _CAST_OVERRIDES.get((family, key))
    if override is not None:
        source_type, stored = stored, override
        if override == "BIGINT":
            for v in non_null:
                try:
                    int(v)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{family}.{key}: {v!r} does not cast to BIGINT") from exc
    return FrozenColumn(name=key, type=stored, nullable=nullable, source_type=source_type)


def freeze_family(
    family: str,
    files: Sequence[tuple[str, list[dict[str, Any]]]],
    sport: str,
    source_id: str,
    commit: str,
) -> FrozenFamily:
    """Sniff one family over every match, and fail loudly on the three unsafe cases.

    `files` is `(bundle-relative path, rows)` per match, in match id order: that order
    becomes `frozen_from` and, together with the provider's own key order, the
    `keys_sha256`.
    """
    all_rows = [row for _, rows in files for row in rows]
    if not all_rows:
        raise ValueError(f"{family}: no rows across the bundle")
    key_order = tuple(all_rows[0].keys())
    expected = set(key_order)
    for file_name, rows in files:
        for i, row in enumerate(rows):
            keys = set(row.keys())
            if keys != expected:
                raise ValueError(
                    f"{family}: {file_name} row {i}: missing {sorted(expected - keys)}, "
                    f"extra {sorted(keys - expected)}"
                )
    columns = tuple(_infer_column(family, key, [row[key] for row in all_rows]) for key in key_order)
    keys_sha256 = hashlib.sha256(",".join(key_order).encode("utf-8")).hexdigest()
    return FrozenFamily(
        table=f"events_{family}",
        family=family,
        sport=sport,
        source_id=source_id,
        commit=commit,
        n_keys=len(key_order),
        keys_sha256=keys_sha256,
        frozen_from=tuple(file_name for file_name, _ in files),
        rows_read=len(all_rows),
        columns=columns,
    )


@dataclass(frozen=True)
class MatchBundle:
    match_id: int
    events_path: Path
    events_rel: str
    game_data_path: Path
    game_data_rel: str


def discover(source: Source, raw_root: Path) -> list[MatchBundle]:
    """The `dynamic_events.json` and `game_data.json` of every match, in match id order."""
    events = {f.match_id: f for f in source.files if f.role == "events" and f.match_id is not None}
    game_data = {
        f.match_id: f for f in source.files if f.role == "game_data" and f.match_id is not None
    }
    if events.keys() != game_data.keys():
        raise ValueError(
            f"events and game_data match ids differ: {sorted(events)} vs {sorted(game_data)}"
        )
    return [
        MatchBundle(
            match_id=mid,
            events_path=raw_root / events[mid].path,
            events_rel=events[mid].path,
            game_data_path=raw_root / game_data[mid].path,
            game_data_rel=game_data[mid].path,
        )
        for mid in sorted(events)
    ]


def load_events(bundles: Sequence[MatchBundle]) -> dict[int, dict[str, list[dict[str, Any]]]]:
    """Every `dynamic_events.json`, parsed once, keyed by match id then family."""
    out: dict[int, dict[str, list[dict[str, Any]]]] = {}
    expected = set(FAMILY_ORDER)
    for bundle in bundles:
        data = json.loads(bundle.events_path.read_text(encoding="utf-8"))
        found = set(data.keys())
        if found != expected:
            raise ValueError(
                f"{bundle.events_rel}: families missing {sorted(expected - found)}, "
                f"extra {sorted(found - expected)}"
            )
        out[bundle.match_id] = data
    return out


def probe_match(bundle: MatchBundle, families: dict[str, list[dict[str, Any]]]) -> Row:
    """One report row: the 20 family row counts plus the roster and header of `game_data.json`."""
    game_data = json.loads(bundle.game_data_path.read_text(encoding="utf-8"))
    if game_data["gameId"] != bundle.match_id:
        raise ValueError(
            f"{bundle.game_data_rel}: gameId {game_data['gameId']} != {bundle.match_id}"
        )
    row: Row = {"match_id": bundle.match_id}
    for family in FAMILY_ORDER:
        row[family] = len(families[family])
    row["n_home_players"] = len(game_data["homeTeam"]["players"])
    row["n_away_players"] = len(game_data["awayTeam"]["players"])
    row["home_team_id"] = game_data["homeTeam"]["teamId"]
    row["away_team_id"] = game_data["awayTeam"]["teamId"]
    row["date"] = game_data["date"]
    row["season"] = game_data["seasonName"]
    return row


REPORT_COLUMNS: tuple[str, ...] = (
    "match_id",
    *FAMILY_ORDER,
    "n_home_players",
    "n_away_players",
    "home_team_id",
    "away_team_id",
    "date",
    "season",
)


def write_report_csv(rows: Sequence[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(REPORT_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def text_table(rows: Sequence[Row], columns: Sequence[str] = REPORT_COLUMNS) -> str:
    cells = [[str(r[c]) for c in columns] for r in rows]
    widths = [max(len(c), *(len(line[i]) for line in cells)) for i, c in enumerate(columns)]
    head = "  ".join(c.rjust(w) for c, w in zip(columns, widths, strict=True))
    body = ["  ".join(v.rjust(w) for v, w in zip(line, widths, strict=True)) for line in cells]
    return "\n".join([head, *body])


def aggregate_paths(raw_root: Path) -> list[Path]:
    return sorted((raw_root / "data" / "aggregates").glob("*.csv"))


def _file_for_role(source: Source, role: str) -> FileEntry:
    """The single season-grain manifest entry of `role` (`matches`, `player_aliases`)."""
    matches = [f for f in source.files if f.role == role and f.match_id is None]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one '{role}' file, found {len(matches)}")
    return matches[0]


def aggregate_table(path: Path) -> str:
    """`aggregates_<family>` for a raw aggregate CSV path. Shared with the bronze builder."""
    for family in AGGREGATE_FAMILIES:
        if f"_{family}aggregates_" in path.name:
            return f"aggregates_{family}"
    raise ValueError(f"unrecognised basketball aggregate file: {path.name}")


def freeze_aggregates(
    raw_root: Path, schemas_dir: Path, source: Source, con: duckdb.DuckDBPyConnection
) -> dict[str, FrozenSchema]:
    """`aggregates_{shots,drives,picks}.schema.json`, via the shared CSV freezer."""
    schemas: dict[str, FrozenSchema] = {}
    for path in aggregate_paths(raw_root):
        table = aggregate_table(path)
        schema = freeze_csv_family(table, [path], raw_root, con)
        target = schemas_dir / f"{table}.schema.json"
        target.write_text(
            schema.to_json(sport=SPORT, source_id=SOURCE_ID, commit=source.commit),
            encoding="utf-8",
        )
        schemas[table] = schema
    return schemas


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join(str(v) for v in r) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def render_doc(
    rows: Sequence[Row],
    families: dict[str, FrozenFamily],
    aggregate_schemas: dict[str, FrozenSchema],
    source: Source,
    matches_json: list[dict[str, Any]],
    aliases_rows: int,
    aliases_columns: Sequence[str],
) -> str:
    """The event/meta/aggregate part of `docs/formats/basketball.md` (task 6). No H1
    and no `## Source`: `freeze_basketball` appends this after the tracking section
    task 5 already wrote to the same file (which has both), so this body starts
    straight at its own first heading. Every claim below traces to `rows`, `families`
    or a direct, one-shot read of `matches.json` / `player_id_aliases.csv` done at
    freeze time; nothing here is asserted beyond what those support."""
    match_ids = [str(r["match_id"]) for r in rows]
    parts: list[str] = []
    add = parts.append

    add(
        f"Generated by `tracklab freeze-schema basketball` (task 6), on the same "
        f"{len(rows)} matches and commit `{source.commit}` as the tracking section "
        "above (tracking itself is documented separately, in `tasks/todo.md` task 5, "
        "not repeated here). The per-match rows live in "
        "`pipeline/reports/basketball_format.csv`; the family and aggregate tables "
        "are rendered from the frozen `*.schema.json` files under "
        "`pipeline/src/tracklab/bronze/schemas/basketball/`. "
        f"{len(rows)} matches x (`dynamic_events.json`, `game_data.json`), 3 season "
        "aggregates, `matches.json` and `player_id_aliases.csv`.\n"
    )

    add("## Event families\n")
    add(
        "One Parquet per match and family (`events_<family>`), columns "
        "`sport, match_id, source_file, source_row` (see `bronze.common.LINEAGE_FIELDS`) "
        "plus the family's own columns in provider order. `n_keys` is fixed across the "
        "bundle: the freezer fails loudly the moment a match disagrees.\n"
    )
    header = ["family", "n_keys", *match_ids]
    family_rows = [
        [family, families[family].n_keys, *(r[family] for r in rows)] for family in FAMILY_ORDER
    ]
    add(_md_table(header, family_rows) + "\n")

    add("## Family columns\n")
    for family in FAMILY_ORDER:
        frozen = families[family]
        add(f"### {family}\n")
        add(f"`events_{family}`, {frozen.n_keys} keys, {frozen.rows_read} rows read.\n")
        col_rows = [[c.name, c.type, c.nullable, c.source_type or "-"] for c in frozen.columns]
        add(_md_table(["key", "type", "nullable", "source_type"], col_rows) + "\n")

    add("## Declared casts\n")
    cast_lines = []
    for family, key in _CAST_OVERRIDES:
        column = next(c for c in families[family].columns if c.name == key)
        cast_lines.append(
            f"- `{family}.{key}`: source `{column.source_type}` -> stored `{column.type}`."
        )
    add("\n".join(cast_lines) + "\n")

    add("## game_data.json\n")
    home_counts = [cast(int, r["n_home_players"]) for r in rows]
    away_counts = [cast(int, r["n_away_players"]) for r in rows]
    add(
        "12 header keys per match: `gameId, date, competitionEditionId, competitionId, "
        "competitionName, seasonId, seasonName, dynamicEventsLastProcessingDate, "
        "trackingLastProcessingDate, physicalLastProcessingDate` plus `homeTeam` and "
        "`awayTeam`, each `{teamId, teamName, players[]}`. Every player carries "
        "`{playerId, firstName, lastName, jersey}`, `jersey` delivered as a string in "
        "every roster of the bundle. Roster size per match: "
        f"home {min(home_counts)}-{max(home_counts)}, "
        f"away {min(away_counts)}-{max(away_counts)} "
        "(`n_home_players`/`n_away_players` in the report).\n"
    )

    add("## matches.json\n")
    keysets = {tuple(sorted(m.keys())) for m in matches_json}
    home_keysets = {tuple(sorted(m["home_team"].keys())) for m in matches_json}
    if len(keysets) == 1:
        keys = ", ".join(sorted(matches_json[0].keys()))
        keys_note = f"Every match shares the same {len(matches_json[0])} keys: `{keys}`."
    else:
        keys_note = f"key sets differ across matches: {sorted(keysets)}."
    if len(home_keysets) == 1:
        home_note = (
            f"`home_team`/`away_team` are each `{{{', '.join(sorted(home_keysets.pop()))}}}`."
        )
    else:
        home_note = f"`home_team` keys differ across matches: {sorted(home_keysets)}."
    add(
        f"A list of {len(matches_json)} matches. {keys_note} {home_note} Bronze flattens "
        "them to `home_team_id, home_team_name, away_team_id, away_team_name` and keeps "
        "every other key as delivered.\n"
    )

    add("## player_id_aliases.csv\n")
    add(
        f"{aliases_rows} data rows, columns `{', '.join(aliases_columns)}`. Maps a "
        "provider `player_id` that changed between seasons (a name typo, a mid-season "
        "correction) to a `canonical_player_id` and to the ACB's own id.\n"
    )

    add("## Aggregates\n")
    add(
        "Season grain (player x team x season for `shots`/`drives`, per the CSV's own "
        "key for `picks`), no `match_id`: `SEASON_LINEAGE_FIELDS` "
        "(`sport, source_file, source_row`).\n"
    )
    agg_header = ["table", "n_columns", "header_sha256"]
    agg_rows = [
        [table, len(schema.columns), schema.header_sha256[:12]]
        for table, schema in sorted(aggregate_schemas.items())
    ]
    add(_md_table(agg_header, agg_rows) + "\n")

    return "\n".join(parts) + "\n"


def merge_doc(existing: str | None, body: str) -> str:
    """Keeps whatever precedes `_DOC_MARKER` in `existing` (task 5's tracking
    write-up, if the file already has one) and replaces everything from the marker
    onward with `body`, so freezing twice never duplicates this task's section. A
    missing file falls back to a bare title, so the doc still stands on its own."""
    section = f"{_DOC_MARKER}\n\n{body.rstrip(chr(10))}\n"
    if existing is None:
        head = f"# Basketball bundle format (SkillCorner {SOURCE_ID})\n"
    else:
        cut = existing.find(_DOC_MARKER)
        head = existing[:cut] if cut != -1 else existing
    return head.rstrip("\n") + "\n\n" + section


def freeze_basketball(
    *,
    manifest_path: Path,
    data_dir: Path,
    reports_dir: Path,
    docs_dir: Path,
    schemas_dir: Path,
    log: Log = print,
) -> int:
    source = load_manifest(manifest_path).source(SOURCE_ID)
    if source.commit is None:
        raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
    raw_root = raw_root_for(data_dir, SOURCE_ID)
    bundles = discover(source, raw_root)
    if not bundles:
        raise FileNotFoundError(f"no matches for {SOURCE_ID} in the manifest")
    log(f"probing {len(bundles)} matches...")
    events = load_events(bundles)
    rows = [probe_match(b, events[b.match_id]) for b in bundles]

    schemas_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    families: dict[str, FrozenFamily] = {}
    for family in FAMILY_ORDER:
        files = [(b.events_rel, events[b.match_id][family]) for b in bundles]
        frozen = freeze_family(family, files, SPORT, SOURCE_ID, source.commit)
        target = schemas_dir / f"events_{family}.schema.json"
        if target.exists():
            previous = load_family(target)
            changed |= previous.keys_sha256 != frozen.keys_sha256 or previous.columns != (
                frozen.columns
            )
        target.write_text(frozen.to_json(), encoding="utf-8")
        families[family] = frozen
        log(f"frozen events_{family}: {frozen.n_keys} keys, {frozen.rows_read} rows -> {target}")

    con = duckdb.connect()
    aggregate_schemas = freeze_aggregates(raw_root, schemas_dir, source, con)
    for table, schema in sorted(aggregate_schemas.items()):
        target = schemas_dir / f"{table}.schema.json"
        log(f"frozen {table}: {len(schema.columns)} columns -> {target}")

    matches_path = raw_root / _file_for_role(source, "matches").path
    matches_json = json.loads(matches_path.read_text(encoding="utf-8"))
    aliases_path = raw_root / _file_for_role(source, "player_aliases").path
    aliases_columns = header_names(aliases_path)
    row = con.execute(
        "SELECT count(*) FROM read_csv(?, header=true)", [str(aliases_path)]
    ).fetchone()
    assert row is not None
    aliases_rows = int(row[0])

    report_path = reports_dir / REPORT_NAME
    write_report_csv(rows, report_path)
    doc_path = docs_dir / DOC_NAME
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    existing = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else None
    body = render_doc(
        rows, families, aggregate_schemas, source, matches_json, aliases_rows, aliases_columns
    )
    doc_path.write_text(merge_doc(existing, body), encoding="utf-8")

    log("")
    log(text_table(rows))
    log("")
    log(f"report: {report_path} ({len(rows)} rows, {len(REPORT_COLUMNS)} columns)")
    log(f"doc: {doc_path}")
    return 1 if changed else 0
