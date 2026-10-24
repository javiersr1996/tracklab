"""Probe for lesson 12, "Which way is a player facing?" (task 84). Read-only.

The two published clips (`web/public/data/pose/hook_<match>.json`, 25 fps, positions in cm): for
each player, the frames where the player has its previous and next frame in the clip (so the
central difference of x, y gives a speed) and a skeleton with both shoulders and the nose (so the
shoulder line and its normal can be drawn). A player counts if at least `MIN_FRAMES` such frames
are at over `MIN_SPEED` m/s. Prints per clip and player the qualifying frames.

If the two clips give fewer than `MIN_PLAYERS` players, the probe counts the same in bronze
`bodypose_players` of the two matches (joints in cm from the player's own (x, y, 0), positions in
m; the frame step is the bronze one), and the lesson would need `learn/facing.json` from bronze.

Decided before measuring: the lesson lives on the clips (0 new bytes) if they give at least
`MIN_PLAYERS` players, on bronze if bronze does, and dies otherwise.

    TRACKLAB_DATA_ROOT=... uv run python scripts/probe_learn_facing.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from tracklab.paths import data_root

MIN_FRAMES = 25
MIN_SPEED = 2.0
MIN_PLAYERS = 10
CLIPS = Path(__file__).resolve().parents[2] / "web" / "public" / "data" / "pose"
MATCHES = ("1925299", "1996435")


def clip_players(path: Path) -> dict[int, int]:
    """Player id -> frames at over MIN_SPEED with both shoulders and the nose."""
    clip = json.loads(path.read_text(encoding="utf-8"))
    names = clip["joints"]
    need = [names.index(j) for j in ("nose", "lShoulder", "rShoulder")]
    dt = 1.0 / clip["fps"]
    at = [{p[0]: p for p in fr["p"]} for fr in clip["frames"]]
    counts: dict[int, int] = {}
    for k in range(1, len(at) - 1):
        for i, p in at[k].items():
            a, b = at[k - 1].get(i), at[k + 1].get(i)
            if a is None or b is None or p[4] is None:
                continue
            xyz = p[4][0]
            if any(xyz[j] is None for j in need):
                continue
            speed = math.hypot(b[1] - a[1], b[2] - a[2]) / 100 / (2 * dt)
            if speed > MIN_SPEED:
                pid = clip["players"][i]["player_id"]
                counts[pid] = counts.get(pid, 0) + 1
    return counts


def main() -> int:
    total = 0
    for match in MATCHES:
        path = CLIPS / f"hook_{match}.json"
        counts = clip_players(path)
        good = {pid: n for pid, n in counts.items() if n >= MIN_FRAMES}
        total += len(good)
        print(
            f"probe facing {path.name}: {len(counts)} players with a frame at > {MIN_SPEED} m/s, "
            f"{len(good)} with >= {MIN_FRAMES}: "
            + ", ".join(f"{pid} ({n})" for pid, n in sorted(good.items(), key=lambda kv: -kv[1]))
        )
    if total >= MIN_PLAYERS:
        print(f"probe facing: VIVE on the clips, 0 new bytes ({total} players >= {MIN_PLAYERS})")
        return 0
    print(f"probe facing: the clips give {total} players < {MIN_PLAYERS}; bronze is needed")
    bronze = data_root() / "bronze" / "football" / "bodypose_players"
    print(f"probe facing: bronze is under {bronze}; not measured by this version of the probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
