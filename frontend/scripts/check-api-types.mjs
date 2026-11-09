// CI drift check: regenerate the API types from docs/api/openapi.json and fail if the committed file differs.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const spec = join(root, "..", "docs", "api", "openapi.json");
const committed = join(root, "src", "api", "schema.d.ts");
const dir = mkdtempSync(join(tmpdir(), "ragassist-api-"));
const fresh = join(dir, "schema.d.ts");

try {
  const bin = join(root, "node_modules", "openapi-typescript", "bin", "cli.js");
  execFileSync(process.execPath, [bin, spec, "-o", fresh], { stdio: "inherit", cwd: root });
  const norm = (p) => readFileSync(p, "utf8").replace(/\r\n/g, "\n");
  if (norm(fresh) !== norm(committed)) {
    console.error(
      "src/api/schema.d.ts is out of date with docs/api/openapi.json. Run `npm run api:types` in frontend/ and commit the result.",
    );
    process.exitCode = 1;
  } else {
    console.log("API types are in sync with docs/api/openapi.json.");
  }
} finally {
  rmSync(dir, { recursive: true, force: true });
}
