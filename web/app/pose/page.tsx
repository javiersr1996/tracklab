"use client";

import { useEffect, useState } from "react";
import { Pose } from "../../components/pose/Pose";
import type { PoseClip } from "../../lib/pose/types";

// `/pose` (task 56): the Body Pose sample in a viewer with its own projection. The clip is
// fetched, like the possessions the replay plays. Every figure is an element `data-fig="path"`
// whose text is `String(value at path)` in the clip; the e2e reads the same path and compares.
const CLIP = "/data/pose/1925299_phase406.json";

const at = (root: unknown, path: string): unknown =>
  path.split(".").reduce<unknown>((node, key) => (node as Record<string, unknown> | undefined)?.[key], root);

function F({ clip, p }: { clip: PoseClip; p: string }) {
  return <span data-fig={p}>{String(at(clip, p))}</span>;
}

// What the viewer does about each limit, by the limit's id in the clip.
const IN_THIS_VIEWER: Record<string, string> = {
  detected_only:
    "A player with no pose in a frame is drawn as the replay's disc. No skeleton is interpolated between frames or carried over from an earlier one.",
  z_relative:
    "Each body is drawn in its own frame, about the player's position; the pitch stays a flat map seen from above, with no floor and no vertical scale. Yaw and tilt turn the bodies, never the pitch.",
  separate_generation:
    "Positions are the pose file's own x and y, not the tracking's, and frames are matched by number, never by timestamp.",
};

function View({ clip }: { clip: PoseClip }) {
  const mae = "coverage.p90_mae_cm";
  return (
    <>
      <h1>
        <F clip={clip} p="joints.length" /> joints
      </h1>
      <p>
        SkillCorner&apos;s Body Pose sample: match <F clip={clip} p="match_id" />, period{" "}
        <F clip={clip} p="period" />, frames <F clip={clip} p="frame_lo" /> to{" "}
        <F clip={clip} p="frame_hi" /> at <F clip={clip} p="fps" /> fps. Orange is the home
        team, blue the away team. Bodies are drawn to the pitch&apos;s scale; follow a player to
        see one enlarged.
      </p>
      <div className="pose-layout">
        <Pose clip={clip} />
        <aside className="pose-limits" data-section="limits">
          <h2>What the data does not say</h2>
          {clip.limits.map((limit, j) => (
            <div key={limit.id} data-limit={limit.id}>
              <blockquote data-fig={`limits.${j}.text`}>{limit.text}</blockquote>
              <p>
                SkillCorner, <cite data-fig={`limits.${j}.readme`}>{limit.readme}</cite>.
                {limit.id in IN_THIS_VIEWER ? ` In this viewer: ${IN_THIS_VIEWER[limit.id]}` : null}
              </p>
            </div>
          ))}
        </aside>
      </div>
      <section data-section="error">
        <h2>The predicted error travels with each joint</h2>
        <p>
          Every joint comes with SkillCorner&apos;s predicted error, <code>p90_mae_cm</code>. The
          viewer draws a joint and its bones solid up to the clip&apos;s median,{" "}
          <F clip={clip} p={`${mae}.median`} /> cm, fainter up to its <code>p90</code>,{" "}
          <F clip={clip} p={`${mae}.p90`} /> cm, and faintest beyond, up to{" "}
          <F clip={clip} p={`${mae}.max`} /> cm (the smallest is <F clip={clip} p={`${mae}.min`} />{" "}
          cm).
        </p>
      </section>
      <section data-section="coverage">
        <h2>What this clip holds</h2>
        <p>
          <F clip={clip} p="coverage.frames" /> frames and <F clip={clip} p="coverage.player_frames" />{" "}
          player-frames, of which <F clip={clip} p="coverage.with_joints" /> have a pose (a share of{" "}
          <F clip={clip} p="coverage.with_joints_share" />), from{" "}
          <F clip={clip} p="coverage.skeletons_per_frame.min" /> to{" "}
          <F clip={clip} p="coverage.skeletons_per_frame.max" /> skeletons per frame and{" "}
          <F clip={clip} p="coverage.joint_observations" /> joint observations. This is the
          provider&apos;s sample of one phase; a whole match has long stretches without pose and is
          not read here yet.
        </p>
      </section>
    </>
  );
}

export default function PosePage() {
  const [clip, setClip] = useState<PoseClip | "failed" | null>(null);

  useEffect(() => {
    let live = true;
    fetch(CLIP)
      .then((r) => r.json() as Promise<PoseClip>)
      .then((data) => live && setClip(data))
      .catch(() => live && setClip("failed"));
    return () => {
      live = false;
    };
  }, []);

  return (
    <main className="page pose" data-loaded={clip === null ? "false" : "true"}>
      {clip === null || clip === "failed" ? (
        <>
          <h1>Body pose</h1>
          {clip === "failed" ? <p role="alert">The pose clip could not be loaded.</p> : null}
        </>
      ) : (
        <View clip={clip} />
      )}
    </main>
  );
}
