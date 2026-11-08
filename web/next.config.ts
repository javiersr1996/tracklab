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

// P19, task 159: the full policy goes out as Report-Only first, so the console of a real browser says
// what it would block before anything is blocked (e2e/csp.spec.ts walks the routes and fails on a
// report). `unsafe-inline` for scripts because Next writes inline ones and a nonce would make every
// page dynamic; `wasm-unsafe-eval` for DuckDB-WASM; `blob:` workers because DuckDB starts its worker
// from a blob; no origin but our own (the pages link out, they fetch nothing from elsewhere).
const CSP_REPORT_ONLY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'",
  "worker-src 'self' blob:",
  "connect-src 'self'",
  "img-src 'self' data: blob:",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
].join("; ");

// P18, task 142: headers on every route; frame-ancestors is the only CSP directive that is enforced.
// `immutable` only where the path itself changes with the content: the warehouse
// Parquet files carry a content hash in their name, and the DuckDB engine and its extensions sit
// under the pinned package version (`/duckdb/1.32.0/`) or engine version (`/duckdb/ext/v1.4.3/`), as
// scripts/copy-engine.mjs writes them, the extensions also checked against a pinned sha256.
const IMMUTABLE = [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "Content-Security-Policy-Report-Only", value: CSP_REPORT_ONLY },
        ],
      },
      { source: "/data/warehouse/:path*", headers: IMMUTABLE },
      { source: "/duckdb/:path*", headers: IMMUTABLE },
    ];
  },
  async redirects() {
    return MOVED.map((m) => ({ ...m, permanent: true }));
  },
};

export default nextConfig;
