// Copies the licence-safe export (data/public/) into web/public/data/ for the dev
// server and the build. web/public/data/ is gitignored: data/public/ stays the
// single source, written only by pipeline/export_public.py.
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "data", "public");
const dst = join(here, "..", "public", "data");
const files = existsSync(src) ? readdirSync(src).filter((f) => /\.(json|bin)$/.test(f)) : [];
if (!files.includes("researchers.json")) {
  console.error("No data/public/researchers.json – run: python pipeline/export_public.py");
  process.exit(1);
}
mkdirSync(dst, { recursive: true });
for (const f of files) copyFileSync(join(src, f), join(dst, f));
console.log(`Synced ${files.length} data files to web/public/data/`);
