// Copies the licence-safe export (data/public/) into web/public/data/ for the dev
// server and the build. web/public/data/ is gitignored: data/public/ stays the
// single source, written only by pipeline/export_public.py.
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "data", "public");
const dst = join(here, "..", "public", "data");
const managed = (f) => /\.(json|bin)$/.test(f);
const files = existsSync(src) ? readdirSync(src).filter(managed) : [];
if (!files.includes("researchers.json")) {
  console.error("No data/public/researchers.json – run: python pipeline/export_public.py");
  process.exit(1);
}
mkdirSync(dst, { recursive: true });
// Data files no longer in data/public/ (e.g. a removed detail shard) are deleted.
const keep = new Set(files);
const stale = readdirSync(dst).filter((f) => managed(f) && !keep.has(f));
for (const f of stale) rmSync(join(dst, f));
for (const f of files) copyFileSync(join(src, f), join(dst, f));
console.log(`Synced ${files.length} data files to web/public/data/` + (stale.length ? ` (removed ${stale.length} old)` : ""));
