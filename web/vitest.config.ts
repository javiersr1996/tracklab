import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    // Transformed modules are kept in node_modules/.vitest-cache between runs (P19, task 160).
    fsModuleCache: true,
  },
});
