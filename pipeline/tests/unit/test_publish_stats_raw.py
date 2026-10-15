"""`stats.json`'s raw bytes add every source of a sport (task 64).

P6 gave football a second source (the pose zips): the count was one entry per sport, so the last
source overwrote the first and the football total shrank to the pose zips' bytes.
"""

from __future__ import annotations

from pathlib import Path

from tracklab.ingest.manifest import load_manifest
from tracklab.publish.stats import raw_bytes

MANIFEST = Path(__file__).resolve().parents[2] / "manifest" / "sources.json"


def test_the_raw_bytes_of_a_sport_add_all_its_sources() -> None:
    sources = load_manifest(MANIFEST).sources
    assert len({s.source_id for s in sources if s.sport == "football"}) >= 2, "the case that bit"
    raw = raw_bytes(MANIFEST)
    for sport in ("basketball", "football"):
        assert raw[sport] == sum(f.bytes for s in sources if s.sport == sport for f in s.files)
    assert raw["total"] == sum(f.bytes for s in sources for f in s.files)
    assert raw["total"] == raw["basketball"] + raw["football"]
