import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  // rolldown-vite(oxc)对 tsx 需显式 JSX runtime(工程 tsconfig 为 preserve)
  oxc: {
    jsx: { runtime: "automatic" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname) },
  },
});
