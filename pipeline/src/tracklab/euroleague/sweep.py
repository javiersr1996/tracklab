"""``tracklab euroleague sweep``: no real shot in what the site ships.

After ``next build``, take a fixed sample of real shots from what ``euroleague fetch`` left under
the data root and look for their signatures in ``web/.next``, in ``web/public`` and in every
``*.map`` under ``web/`` (``node_modules`` aside). The signature is the shot's ``UTC``, 14 digits
and one per event of a game (docs/euroleague-probe.md, section 7): it is what any copy of a raw
row carries, whether as text or as a number. One hit fails, and so does
``productionBrowserSourceMaps`` switched on in ``web/next.config.ts``.

It reads the raw files and the built files only, never the code that writes the aggregates.
Without downloaded data (CI) there is nothing to sweep for: it says PARTIAL and exits 0, which
``TRACKLAB_REQUIRE_FULL=1`` turns into a failure. Without ``web/.next`` it sweeps the rest and
says PARTIAL too.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

SAMPLE = 200
SEED = 14
SEASONS = ("E2025", "E2026")
_DIGITS = re.compile(rb"\d{14,}")
_SOURCE_MAPS_ON = re.compile(r"productionBrowserSourceMaps\s*:\s*true")


def signatures(
    raw: Path, seasons: Iterable[str], sample: int = SAMPLE, seed: int = SEED
) -> list[str]:
    """The UTC of ``sample`` field goals drawn with a fixed seed from every downloaded game."""
    rows: list[tuple[str, int, int, str]] = []
    for season in seasons:
        manifest = json.loads((raw / season / "manifest.json").read_text(encoding="utf-8"))
        for game in manifest["games"]:
            points = json.loads(
                (raw / season / game["files"]["Points"]).read_text(encoding="utf-8")
            )
            for row in points["Rows"] or []:
                if str(row["ID_ACTION"]).strip() == "FTM":
                    continue
                utc = str(row["UTC"]).strip()
                if len(utc) != 14 or not utc.isdigit():
                    raise ValueError(f"{season} {game['gamecode']}: UTC {utc!r} is not 14 digits")
                rows.append((season, int(game["gamecode"]), int(row["NUM_ANOT"]), utc))
    rows.sort()
    return [utc for *_key, utc in random.Random(seed).sample(rows, min(sample, len(rows)))]


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


def hits(data: bytes, needles: set[bytes]) -> set[bytes]:
    """The needles found in ``data``, also inside a longer run of digits."""
    found: set[bytes] = set()
    for match in _DIGITS.finditer(data):
        run = match.group()
        for i in range(len(run) - 13):
            if run[i : i + 14] in needles:
                found.add(run[i : i + 14])
    return found


def run_euroleague_sweep(
    data_dir: Path, web: Path, seasons: Iterable[str] = SEASONS, sample: int = SAMPLE
) -> int:
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
    needles = {s.encode("ascii") for s in signatures(raw, seasons, sample)}
    files = 0
    swept = 0
    found: list[str] = []
    for path in swept_files(web):
        data = path.read_bytes()
        files += 1
        swept += len(data)
        for needle in sorted(hits(data, needles)):
            found.append(f"{path.relative_to(web).as_posix()}: {needle.decode()}")
    for line in found:
        print(f"  hit: {line}")
    built = (web / ".next").is_dir()
    verdict = "FULL" if built else "PARTIAL:"
    where = ".next, public and *.map" if built else "public and *.map (no web/.next: build first)"
    print(
        f"euroleague sweep: {verdict} {len(needles)} signatures from {', '.join(seasons)}; "
        f"{files} files, {swept} bytes under {where}; {len(found)} hits"
    )
    return 1 if failed or found else 0
