import { defineConfig } from "tsup";
import { buildV2Entry } from "./scripts/build-v2-entry.mjs";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    "entry.opencode": "src/entry.opencode.ts",
    "entry.opencode.v2": "src/entry.opencode.v2.ts",
  },
  format: ["esm"],
  dts: true,
  sourcemap: true,
  clean: true,
  external: ["headroom-ai"],
  onSuccess: () => buildV2Entry("dist"),
});
