import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

// OpenCode V2 requires a package directory. Both builds use one wrapper owner.
export async function buildV2Entry(outDir) {
  const { version } = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  const directory = join(outDir, "v2");
  await mkdir(directory, { recursive: true });
  await writeFile(join(directory, "package.json"), JSON.stringify({
    name: "headroom-opencode-native-v2", version, private: true, type: "module", exports: "./index.js",
  }) + "\n");
  await writeFile(join(directory, "index.js"),
    '// OpenCode V2 loads plugin directories. The implementation remains one bundle.\n' +
    'export { default } from "../entry.opencode.v2.js";\n');
}
