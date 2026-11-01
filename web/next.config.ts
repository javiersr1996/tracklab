import type { NextConfig } from "next";

// P15, task 121: the six pages that moved under /tracking and /engineering. `permanent: true` is
// Next's 308 (a 301 that keeps the method); a query such as `/replay?p=<file>` is carried over.
const MOVED = [
  { source: "/replay", destination: "/tracking/replay" },
  { source: "/runs", destination: "/tracking/runs" },
  { source: "/pose", destination: "/tracking/pose" },
  { source: "/platform", destination: "/engineering" },
  { source: "/quality", destination: "/engineering/quality" },
  { source: "/bulletin", destination: "/engineering/bulletin" },
];

const nextConfig: NextConfig = {
  async redirects() {
    return MOVED.map((m) => ({ ...m, permanent: true }));
  },
};

export default nextConfig;
