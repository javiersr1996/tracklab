import { Playback } from "../replay/engine";
import type { PoseClip, PoseFrame } from "./types";

// Playback of a pose clip with the replay's machine (idle, playing, paused, ended; `tick`,
// `seek`, `setRate`). `frameAt` returns the last native frame at or before `t` and nothing in
// between: a skeleton exists only in the frames the file gives it one (limit 1 of P6), so a
// player who loses his pose in the next frame is a disc there, never a blend of the two.
export class PoseEngine extends Playback {
  private readonly frames: PoseFrame[];

  constructor(clip: Pick<PoseClip, "frames">) {
    super(clip.frames.map((f) => f.t));
    this.frames = clip.frames;
  }

  frameAt(t: number): PoseFrame {
    return this.frames[this.indexAt(t)];
  }
}
