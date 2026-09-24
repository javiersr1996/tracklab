// The JSON Schema of a published possession lives in `schema.json`, not here,
// so pytest (task 17) and vitest (task 18+) validate against the exact same
// file with no build step in between. This module only re-exports it for
// TypeScript callers.
import schema from "./schema.json";

export default schema;
