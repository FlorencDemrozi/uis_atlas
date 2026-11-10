// Puts the browser's language model and the ONNX runtime files next to the site, so a
// visitor's browser never contacts huggingface.co or cdn.jsdelivr.net (privacy page,
// docs/DATA_POLICY.md). Run by `npm run dev` and `npm run build`:
//   public/models/<model>/...  downloaded once from the Hugging Face Hub at build time
//                              (about 120 MB, kept between builds; gitignored)
//   public/ort/                copied from node_modules/@huggingface/transformers/dist
// The model and file set must match web/src/ideas.ts (model from search-config.json, dtype q8).
import { copyFileSync, createWriteStream, existsSync, mkdirSync, readFileSync, renameSync, rmSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const { model } = JSON.parse(readFileSync(join(web, "src", "search-config.json"), "utf-8"));
const FILES = ["config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
  "onnx/model_quantized.onnx"];
const OPTIONAL = new Set(["special_tokens_map.json"]);

const modelDir = join(web, "public", "models", ...model.split("/"));
let fetched = 0;
for (const file of FILES) {
  const out = join(modelDir, ...file.split("/"));
  if (existsSync(out) && statSync(out).size > 0) continue;
  mkdirSync(dirname(out), { recursive: true });
  const url = `https://huggingface.co/${model}/resolve/main/${file}`;
  const res = await fetch(url);
  if (!res.ok) {
    if (OPTIONAL.has(file) && res.status === 404) continue;
    console.error(`Could not download ${url} (${res.status})`);
    process.exit(1);
  }
  const tmp = `${out}.part`;
  await pipeline(Readable.fromWeb(res.body), createWriteStream(tmp));
  renameSync(tmp, out);   // a broken download never leaves a file that looks complete
  fetched++;
}

// ONNX runtime (WebAssembly) of the installed transformers.js version.
const dist = join(web, "node_modules", "@huggingface", "transformers", "dist");
const ortDir = join(web, "public", "ort");
rmSync(ortDir, { recursive: true, force: true });
mkdirSync(ortDir, { recursive: true });
for (const f of ["ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.wasm"]) {
  copyFileSync(join(dist, f), join(ortDir, f));
}
console.log(`Model ${model}: ${fetched ? `${fetched} file(s) downloaded` : "already present"}; ONNX runtime copied to public/ort/`);
