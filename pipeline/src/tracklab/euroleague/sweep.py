"""``tracklab euroleague sweep``: no real shot in what the site ships.

After ``next build``, take the signatures of every real shot ``euroleague fetch`` left under the
data root and look for them in ``web/.next``, in ``web/public`` and in every ``*.map`` under
``web/`` (``node_modules`` aside). Two signatures, both read from the raw ``Points`` files:

* the ``UTC``, 14 digits and one per event of a game: the
  ``UTC`` of every row, found as any 14-digit window of any digit run, as text or as a number;
* the triple (``COORD_X``, ``COORD_Y``, ``NUM_ANOT``) of every field goal, which a copy that
  dropped the ``UTC`` still carries (a pair (x, y) alone is not unique; a shot with a coordinate
  under 100 is left out, small integers are a count as often as a shot). Looked for in the two
  shapes a copy takes: three integers in a row, in any order (an array, a CSV line), and the
  integers of one ``{...}`` object, whatever its keys (x and y with that ``NUM_ANOT``).

One hit fails, and so does ``productionBrowserSourceMaps`` switched on in ``web/next.config.ts``.

It reads the raw files and the built files only, never the code that writes the aggregates.
Without downloaded data (CI) there is nothing to sweep for: it says PARTIAL and exits 0, which
``TRACKLAB_REQUIRE_FULL=1`` turns into a failure. Without ``web/.next`` it sweeps the rest and
says PARTIAL too.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

# Below it a shot is by the hoop, and three small integers are a count as often as a shot.
MIN_COORD = 100
SEASONS = ("E2025", "E2026")
_DIGITS = re.compile(rb"\d{14,}")
_INTS_IN_A_ROW = re.compile(rb"-?\d+(?:[ 	,;|]+-?\d+){2,}")
_OBJECT = re.compile(rb"\{[^{}]{0,4000}\}")
_INT = re.compile(rb"-?\d+")
_PROP_INT = re.compile(rb"[:=]\s*(-?\d+)(?![\d.])")
_MAX_OBJECT_INTS = 64
_MAX_ROW_INTS = 6
_SOURCE_MAPS_ON = re.compile(r"productionBrowserSourceMaps\s*:\s*true")

Triple = tuple[int, int, int]


class Signatures(NamedTuple):
    utcs: frozenset[bytes]  # every UTC of every row
    orderings: frozenset[Triple]  # (x, y, NUM_ANOT) of each shot, x and y in either order
    by_xy: dict[tuple[int, int], frozenset[int]]  # (x, y) -> the NUM_ANOT of the shots there

    @property
    def shots(self) -> int:
        return len(self.orderings) // 4 if self.orderings else 0


def signatures(raw: Path, seasons: Iterable[str]) -> Signatures:
    """Every UTC and the (x, y, NUM_ANOT) of every field goal of every downloaded game."""
    utcs: set[bytes] = set()
    triples: set[Triple] = set()
    for season in seasons:
        manifest = json.loads((raw / season / "manifest.json").read_text(encoding="utf-8"))
        for game in manifest["games"]:
            points = json.loads(
                (raw / season / game["files"]["Points"]).read_text(encoding="utf-8")
            )
            for row in points["Rows"] or []:
                utc = str(row["UTC"]).strip()
                if len(utc) != 14 or not utc.isdigit():
                    raise ValueError(f"{season} {game['gamecode']}: UTC {utc!r} is not 14 digits")
                utcs.add(utc.encode("ascii"))
                x, y = int(row["COORD_X"]), int(row["COORD_Y"])
                if str(row["ID_ACTION"]).strip() != "FTM" and min(abs(x), abs(y)) >= MIN_COORD:
                    triples.add((x, y, int(row["NUM_ANOT"])))
    by_xy: dict[tuple[int, int], set[int]] = {}
    for x, y, anot in triples:
        by_xy.setdefault((x, y), set()).add(anot)
    return Signatures(
        frozenset(utcs),
        frozenset(p for x, y, a in triples for p in ((x, y, a), (y, x, a), (a, x, y), (a, y, x))),
        {k: frozenset(v) for k, v in by_xy.items()},
    )


def swept_files(web: Path) -> Iterator[Path]:
    """Every file under .next and public, then every *.map elsewhere under web/."""
    seen: set[Path] = set()
    for root in (web / ".next", web / "public"):
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    seen.add(path)
                    yield path
    for path in sorted(web.rglob("*.map")):
        if path.is_file() and "node_modules" not in path.parts and path not in seen:
            yield path


def utc_hits(data: bytes, utcs: frozenset[bytes]) -> set[str]:
    """The UTC found in ``data``, also inside a longer run of digits."""
    found: set[str] = set()
    for match in _DIGITS.finditer(data):
        run = match.group()
        for i in range(len(run) - 13):
            if run[i : i + 14] in utcs:
                found.add(run[i : i + 14].decode())
    return found


def triple_hits(data: bytes, sig: Signatures) -> set[str]:
    """The (x, y, NUM_ANOT) of a shot in ``data``, as three integers in a row or in one object."""
    found: set[str] = set()
    if (
        b"\0" in data[:8192]
    ):  # a wasm, an image, a font: integers by chance, and no row is text there
        return found
    for match in _INTS_IN_A_ROW.finditer(data):
        ints = [int(n) for n in _INT.findall(match.group())]
        if len(ints) > _MAX_ROW_INTS:  # a series of samples, not a record
            continue
        for i in range(len(ints) - 2):
            window = (ints[i], ints[i + 1], ints[i + 2])
            if window in sig.orderings:
                found.add(f"shot ({window[0]}, {window[1]}, {window[2]}) in a row")
    for match in _OBJECT.finditer(data):
        ints = [int(n) for n in _PROP_INT.findall(match.group())]
        if not 3 <= len(ints) <= _MAX_OBJECT_INTS:
            continue
        values = set(ints)
        for a, b in zip(
            ints, ints[1:], strict=False
        ):  # the pair of coordinates side by side, either way
            for x, y in ((a, b), (b, a)):
                for anot in sig.by_xy.get((x, y), ()):
                    if anot in values:
                        found.add(f"shot ({x}, {y}, {anot}) in an object")
    return found


def run_euroleague_sweep(data_dir: Path, web: Path, seasons: Iterable[str] = SEASONS) -> int:
    seasons = list(seasons)
    raw = data_dir / "euroleague" / "raw"
    failed = False
    config = web / "next.config.ts"
    if config.is_file() and _SOURCE_MAPS_ON.search(config.read_text(encoding="utf-8")):
        print("euroleague sweep: productionBrowserSourceMaps is on in web/next.config.ts")
        failed = True
    missing = [s for s in seasons if not (raw / s / "manifest.json").is_file()]
    if missing:
        print(
            f"euroleague sweep: PARTIAL: no downloaded data for {', '.join(missing)} under "
            f"{raw}, no signature to look for (TRACKLAB_REQUIRE_FULL=1 fails here)"
        )
        return 1 if failed else 0
    sig = signatures(raw, seasons)
    files = 0
    swept = 0
    found: list[str] = []
    for path in swept_files(web):
        data = path.read_bytes()
        files += 1
        swept += len(data)
        for needle in sorted(utc_hits(data, sig.utcs) | triple_hits(data, sig)):
            found.append(f"{path.relative_to(web).as_posix()}: {needle}")
    for line in found:
        print(f"  hit: {line}")
    built = (web / ".next").is_dir()
    verdict = "FULL" if built else "PARTIAL:"
    where = ".next, public and *.map" if built else "public and *.map (no web/.next: build first)"
    print(
        f"euroleague sweep: {verdict} {len(sig.utcs)} UTC and {sig.shots} shot triples from "
        f"{', '.join(seasons)}; "
        f"{files} files, {swept} bytes under {where}; {len(found)} hits"
    )
    return 1 if failed or found else 0
