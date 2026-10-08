import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Task 45: `DATABASE_URL` is a server variable. Only the route reads it, no client file names it,
// and nothing of it or of the driver is in what the browser downloads.
const root = path.resolve(__dirname, "..");

function files(dir: string, keep: (f: string) => boolean): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === "node_modules" || e.name === ".next" ? [] : files(p, keep);
    return keep(p) ? [p] : [];
  });
}

const source = ["app", "components", "lib"].flatMap((d) => files(path.join(root, d), (f) => /\.(ts|tsx)$/.test(f)));
const rel = (f: string) => path.relative(root, f).replaceAll("\\", "/");

describe("DATABASE_URL", () => {
  it("is read by the route alone, and never as a NEXT_PUBLIC_ variable", () => {
    const mentions = source.filter((f) => /DATABASE_URL/.test(readFileSync(f, "utf8"))).map(rel);
    expect(mentions).toEqual(["app/api/warehouse/pg/route.ts"]);
  });

  it("is named by no file that runs in the browser", () => {
    const client = source.filter((f) => /^\s*["']use client["']/m.test(readFileSync(f, "utf8")));
    expect(client.length).toBeGreaterThan(0);
    for (const f of client) expect(readFileSync(f, "utf8"), rel(f)).not.toMatch(/DATABASE_URL|from "pg"|pg-run/);
  });

  // Needs a build (`.next/static`); it skips until there is one.
  const chunks = path.join(root, ".next", "static");
  (existsSync(chunks) ? it : it.skip)("is not in the client bundle, nor are the driver or a connection string", () => {
    const js = files(chunks, (f) => f.endsWith(".js") && statSync(f).isFile());
    expect(js.length).toBeGreaterThan(0);
    for (const f of js) {
      const text = readFileSync(f, "utf8");
      expect(text, rel(f)).not.toContain("DATABASE_URL");
      expect(text, rel(f)).not.toMatch(/postgres(ql)?:\/\/[^\s"']*@/);
      expect(text, rel(f)).not.toContain("node-postgres");
    }
  });
});

describe("the repository", () => {
  // Review V of P4, B6: the acceptance grep of task 44 (`[^ ]*` around the colon) missed the URL
  // in ci.yml, whose password held spaces. A user, a colon and an @ after the scheme, on one line.
  it("holds no connection string with a password in any file git tracks", () => {
    const repo = path.resolve(root, "..");
    const tracked = execFileSync("git", ["ls-files", "-z"], { cwd: repo, encoding: "utf8" }).split("\0").filter(Boolean);
    expect(tracked.length).toBeGreaterThan(100);
    const found: string[] = [];
    for (const file of tracked) {
      const bytes = readFileSync(path.join(repo, file));
      if (bytes.includes(0)) continue;
      bytes
        .toString("utf8")
        .split("\n")
        .forEach((line, i) => {
          if (/postgres(ql)?:\/\/[^@\s]*:[^@]*@/.test(line)) found.push(`${file}:${i + 1}`);
        });
    }
    expect(found).toEqual([]);
  });
});
