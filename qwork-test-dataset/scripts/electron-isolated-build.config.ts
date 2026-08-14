import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";

const repo = resolve(process.env.QWORK_E2E_REPO_ROOT || process.cwd());
const output = resolve(
  process.env.QWORK_E2E_BUILD_ROOT ||
    ".agents/skills/qwork-test-dataset/data/runs/isolated-build",
);
const shared = resolve(repo, "src/shared");

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    resolve: { alias: { "@shared": shared } },
    build: {
      outDir: resolve(output, "main"),
      rollupOptions: { input: { index: resolve(repo, "src/main/index.ts") } },
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    resolve: { alias: { "@shared": shared } },
    build: {
      outDir: resolve(output, "preload"),
      rollupOptions: {
        input: { index: resolve(repo, "src/preload/index.ts") },
        output: { format: "cjs", entryFileNames: "index.cjs" },
      },
    },
  },
  renderer: {
    root: resolve(repo, "src/renderer"),
    resolve: {
      alias: {
        "@": resolve(repo, "src/renderer/src"),
        "@shared": shared,
      },
    },
    plugins: [react()],
    build: {
      outDir: resolve(output, "renderer"),
      target: "es2022",
      sourcemap: true,
      rollupOptions: {
        input: { index: resolve(repo, "src/renderer/index.html") },
      },
    },
  },
});
