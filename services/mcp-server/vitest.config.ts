import { defineConfig } from "vitest/config";

// Vitest 4 no longer excludes build output by default; without this it also
// runs the compiled copies in dist/ and every test is counted twice.
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts"],
  },
});
