"""``bronze_<sport>_<table>`` and ``bronze_common_orientation``.

One step per table group, because a builder is the unit ``tracklab bronze``
runs (``--tables``); each step materializes every table its builder writes, so
the dbt sources downstream depend on a table and not on a group.
"""

from collections.abc import Iterator
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetsDefinition,
    AssetSpec,
    Failure,
    MaterializeResult,
    multi_asset,
)

from tracklab.bronze.common import raw_root_for
from tracklab.cli import BRONZE_BUILDERS, bronze_source_id
from tracklab.dagster_defs.assets_ingest import MANIFEST, manifest_sources, raw_asset_name
from tracklab.ingest.manifest import load_manifest
from tracklab.paths import data_root
from tracklab.silver.orientation import SPORTS, run_orientation

# The tables each builder writes, as they land under data/bronze/<sport>/.
BRONZE_TABLES: dict[tuple[str, str], tuple[str, ...]] = {
    ("basketball", "tracking"): ("tracking_frames", "tracking_objects"),
    ("basketball", "events"): (
        "events_chance_players",
        "events_chances",
        "events_closeouts",
        "events_dribbles",
        "events_drives",
        "events_fouls",
        "events_free_throws",
        "events_handoffs",
        "events_isolations",
        "events_matchups",
        "events_off_ball_screens",
        "events_passes",
        "events_picks",
        "events_possessions",
        "events_posts",
        "events_rebounds",
        "events_shots",
        "events_timeouts",
        "events_touches",
        "events_turnovers",
    ),
    ("basketball", "meta"): ("games", "game_players", "matches", "player_id_aliases"),
    ("basketball", "aggregates"): ("aggregates_drives", "aggregates_picks", "aggregates_shots"),
    ("football", "tracking"): ("tracking_frames", "tracking_objects"),
    ("football", "events"): ("dynamic_events", "phases_of_play"),
    ("football", "meta"): ("match", "match_periods", "match_players", "matches"),
    ("football", "aggregates"): ("aggregates_obr", "aggregates_passing", "aggregates_physical"),
    ("football", "bodypose"): ("bodypose_frames", "bodypose_players"),
}

# What the orientation probe reads (task 9); it writes bronze.common.orientation and
# the per-match CSV of each sport, and dbt reads the basketball one for the court.
ORIENTATION_READS = (
    ("basketball", "games"),
    ("basketball", "events_possessions"),
    ("basketball", "events_rebounds"),
    ("basketball", "events_shots"),
    ("basketball", "events_touches"),
    ("basketball", "tracking_objects"),
    ("football", "dynamic_events"),
    ("football", "match"),
    ("football", "match_periods"),
    ("football", "match_players"),
    ("football", "phases_of_play"),
    ("football", "tracking_objects"),
)


def bronze_key(sport: str, table: str) -> AssetKey:
    return AssetKey(f"bronze_{sport}_{table}")


def _bronze_asset(sport: str, group: str, tables: tuple[str, ...]) -> AssetsDefinition:
    source_id = bronze_source_id(sport, group)
    raw = raw_asset_name(load_manifest(MANIFEST).source(source_id))
    specs = [
        AssetSpec(bronze_key(sport, table), group_name="bronze", deps=[raw]) for table in tables
    ]

    @multi_asset(name=f"bronze_{sport}_{group}", specs=specs)
    def _build(context: AssetExecutionContext) -> Iterator[MaterializeResult[None]]:
        source = load_manifest(MANIFEST).source(source_id)
        root = data_root()
        BRONZE_BUILDERS[(sport, group)](source, raw_root_for(root, source.source_id), root)
        for table in tables:
            files = len(list((root / "bronze" / sport / table).glob("*.parquet")))
            yield MaterializeResult(asset_key=bronze_key(sport, table), metadata={"files": files})

    return _build


bronze_assets = [
    _bronze_asset(sport, group, tables) for (sport, group), tables in BRONZE_TABLES.items()
]


@multi_asset(
    specs=[
        AssetSpec(
            "bronze_common_orientation",
            group_name="bronze",
            deps=[manifest_sources, *(bronze_key(s, t) for s, t in ORIENTATION_READS)],
        ),
        *(
            AssetSpec(
                f"reports_orientation_{sport}",
                group_name="bronze",
                deps=[bronze_key(s, t) for s, t in ORIENTATION_READS if s == sport],
            )
            for sport in SPORTS
        ),
    ],
)
def orientation(context: AssetExecutionContext) -> Iterator[MaterializeResult[None]]:
    """Task 9's probe: the sign of the attack per (match, period, team) and the court."""
    code = run_orientation(
        sports=SPORTS,
        manifest_path=MANIFEST,
        data_dir=data_root(),
        reports_dir=Path("reports"),
        docs_dir=Path("../docs"),
        log=context.log.info,
    )
    if code != 0:
        raise Failure(f"tracklab orientation exited with {code}")
    yield MaterializeResult(asset_key="bronze_common_orientation")
    for sport in SPORTS:
        yield MaterializeResult(asset_key=f"reports_orientation_{sport}")
