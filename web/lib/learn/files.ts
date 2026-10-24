import { statSync } from "node:fs";
import { join } from "node:path";
import type { LearnFile } from "./engine";

// A file "Run it here" registers, with its size read at build time from `web/public`.
export const learnFile = (path: string): LearnFile => ({ path, bytes: statSync(join(process.cwd(), "public", path)).size });
