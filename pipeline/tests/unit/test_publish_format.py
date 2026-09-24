"""`fmt` (task 34): the title's byte formatter, on the exact figures the
platform title is built from -- `raw.bytes_pinned` and `disk.publish.bytes`
of the real build record (task 32) -- plus its boundary at 1000.

Mutation checked by hand, not left as prose: base 1024 instead of base 10
turns `fmt(2316182304)` into `"2.2 GB"` (`2316182304 / 1024**3 = 2.157...`),
not the `"2.3 GB"` asserted below, so `test_fmt_matches_the_real_build_
numbers` would fail under that mutation.
"""

from __future__ import annotations

from tracklab.publish.format import fmt


def test_fmt_matches_the_real_build_numbers() -> None:
    assert fmt(2316182304) == "2.3 GB"
    assert fmt(1230786) == "1.2 MB"
    assert fmt(999) == "999 B"


def test_fmt_at_the_1000_boundary() -> None:
    assert fmt(1000) == "1.0 KB"
    assert fmt(0) == "0 B"


def test_fmt_scales_through_every_unit() -> None:
    assert fmt(500) == "500 B"
    assert fmt(500_000) == "500.0 KB"
    assert fmt(500_000_000) == "500.0 MB"
    assert fmt(500_000_000_000) == "500.0 GB"
