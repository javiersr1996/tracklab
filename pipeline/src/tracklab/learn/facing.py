"""Which way a player faces, frame by frame, from one published pose clip.

Lesson 11 of /learn ("Which way is a player facing?") shows this file as "Reproduce it". It
needs Python 3 and nothing else: it reads the clip Track Lab publishes, takes the player the
clip's window names (or the player index given as a second argument), and for every frame where
that player has both shoulders and the nose, a position in the frame before and the frame after,
and a speed over MIN_SPEED, it prints three angles in degrees:

- facing: the normal to the line from the right shoulder to the left one, on the side of the
  nose, so where the chest points;
- heading: the direction of travel, from the central difference of the player's x, y between the
  frame before and the frame after;
- relative: facing minus heading, brought into (-180, 180].

Then the summary the lesson prints: the median of |relative|, the circular mean of relative
(the argument of the mean resultant vector), the mean resultant length, the circular variance
(one minus that length) and the share of frames side on or further (|relative| over SIDE_DEG)
and with the back to the travel (over BACK_DEG).

    python facing.py                          # the clip on the site, the window's player
    python facing.py hook_1925299.json        # the same file, saved
    python facing.py hook_1925299.json 5      # another player of the clip, by index
"""

import json
import math
import statistics
import sys
import urllib.request
from typing import Any

URL = "https://tracklab-sable.vercel.app/data/pose/hook_1925299.json"
MIN_SPEED = 2.0  # m/s, over the central difference
SIDE_DEG = 45.0
BACK_DEG = 135.0


def load(source: str) -> Any:
    if source.startswith("https://"):
        with urllib.request.urlopen(source) as response:
            return json.load(response)
    with open(source, encoding="utf-8") as f:
        return json.load(f)


def wrap(deg: float) -> float:
    """An angle brought into (-180, 180]."""
    return 180 - ((180 - deg) % 360)


def facing_deg(left: list[float], right: list[float], nose: list[float]) -> float | None:
    """The normal to the shoulder line on the nose's side, in degrees from the x axis and in
    (-180, 180] (a shoulder line along y gives -sx = -0.0, and atan2 would answer -180 for 180);
    None when the shoulders coincide or the nose lies on their line."""
    sx, sy = left[0] - right[0], left[1] - right[1]
    nx, ny = nose[0] - (left[0] + right[0]) / 2, nose[1] - (left[1] + right[1]) / 2
    side = sy * nx - sx * ny  # the normal (sy, -sx) against the nose
    if side == 0:
        return None
    return wrap(math.degrees(math.atan2(-sx, sy) if side > 0 else math.atan2(sx, -sy)))


def heading_deg(before: list[float], after: list[float]) -> float:
    return math.degrees(math.atan2(after[1] - before[1], after[0] - before[0]))


def frames_of(clip: Any, player: int) -> list[dict[str, float]]:
    """The player's qualifying frames: f, speed (m/s), facing, heading and relative (degrees)."""
    names = clip["joints"]
    nose_i, l_i, r_i = (names.index(j) for j in ("nose", "lShoulder", "rShoulder"))
    dt = 1 / clip["fps"]
    # A row: [player, x cm, y cm, flag, [joints as [dx, dy, dz] cm, predicted errors in mm]]
    rows = {fr["f"]: p for fr in clip["frames"] for p in fr["p"] if p[0] == player}
    out = []
    for f, p in sorted(rows.items()):
        before, after = rows.get(f - 1), rows.get(f + 1)
        if before is None or after is None or p[4] is None:
            continue
        xyz = p[4][0]
        if xyz[nose_i] is None or xyz[l_i] is None or xyz[r_i] is None:
            continue
        facing = facing_deg(xyz[l_i], xyz[r_i], xyz[nose_i])
        if facing is None:
            continue
        speed = math.hypot(after[1] - before[1], after[2] - before[2]) / 100 / (2 * dt)
        if speed <= MIN_SPEED:
            continue
        heading = heading_deg(before[1:3], after[1:3])
        out.append(
            {
                "f": f,
                "speed": speed,
                "facing": facing,
                "heading": heading,
                "relative": wrap(facing - heading),
            }
        )
    return out


def circular(degrees: list[float]) -> tuple[float, float]:
    """The circular mean (degrees) and the mean resultant length of angles."""
    c = sum(math.cos(math.radians(a)) for a in degrees) / len(degrees)
    s = sum(math.sin(math.radians(a)) for a in degrees) / len(degrees)
    return math.degrees(math.atan2(s, c)), math.hypot(s, c)


def summary(frames: list[dict[str, float]]) -> dict[str, float | int]:
    rel = [fr["relative"] for fr in frames]
    mean, length = circular(rel)
    n = len(rel)
    return {
        "frames": n,
        "median_abs": statistics.median(abs(a) for a in rel),
        "circ_mean": mean,
        "resultant": length,
        "circ_var": 1 - length,
        "off_pct": 100 * sum(abs(a) > SIDE_DEG for a in rel) / n,
        "back_pct": 100 * sum(abs(a) > BACK_DEG for a in rel) / n,
    }


def main(source: str = URL, player: str | None = None) -> dict[str, float | int]:
    clip = load(source)
    index = clip["windows"][0]["player"] if player is None else int(player)
    who = clip["players"][index]
    frames = frames_of(clip, index)
    print(
        f"player index {index}, id {who['player_id']}, team {who['team_id']}, "
        f"number {who['number']}"
    )
    print(
        f"{len(frames)} frames of {len(clip['frames'])} at over {MIN_SPEED} m/s "
        "with both shoulders, the nose and a position either side"
    )
    print("frame speed facing heading relative")
    for fr in frames:
        angles = " ".join(f"{fr[k]:.3f}" for k in ("speed", "facing", "heading", "relative"))
        print(f"{fr['f']} {angles}")
    s = summary(frames)
    print(f"median |relative| {s['median_abs']:.3f}")
    print(
        f"circular mean {s['circ_mean']:.3f}, mean resultant length {s['resultant']:.3f}, "
        f"circular variance {s['circ_var']:.3f}"
    )
    print(
        f"side on or further (|relative| > {SIDE_DEG:g}): {s['off_pct']:.1f} %; "
        f"back to the travel (> {BACK_DEG:g}): {s['back_pct']:.1f} %"
    )
    return s


if __name__ == "__main__":
    main(*sys.argv[1:])
