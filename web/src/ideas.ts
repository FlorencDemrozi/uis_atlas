// Project idea -> calls, in the browser. The idea is embedded here with the atlas
// model (search-config.json; the same model and "query:" prefix as the pipeline) and
// never leaves the browser. Call vectors come from funding.ideas.enc.json
// (pipeline/call_vectors.py, export_funding.py); scoring mirrors
// call_vectors.score_calls. A shortlist, not a verdict: the relevant calls are
// usually among the first 15–20, mixed with ones that only share words.
import cfg from "./search-config.json";
import { fetchEncrypted, type Funding } from "./funding";

export type TextKind = "scope" | "aspect" | "direction";

interface IdeaFile {
  model: string;
  query_prefix: string;
  settings: { direction_offset: number; shortlist: number };
  dim: number;
  calls: { id: string; t: [TextKind, string][] }[];
  values: string;   // int8, base64
  scales: string;   // float32 per vector, base64
}

export interface IdeaIndex {
  settings: IdeaFile["settings"];
  dim: number;
  calls: { id: string; t: [TextKind, string][]; start: number }[];
  values: Int8Array;
  scales: Float32Array;
}

export interface IdeaHit { id: string; score: number; closest: [TextKind, string] }

const bytes = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

let indexPromise: Promise<IdeaIndex> | null = null;

export function loadIdeaIndex(data: Funding): Promise<IdeaIndex> {
  indexPromise ??= fetchEncrypted<IdeaFile>(data, "./data/funding.ideas.enc.json").then((f) => {
    if (f.query_prefix !== cfg.queryPrefix) throw new Error("model settings differ");
    let start = 0;
    const calls = f.calls.map((c) => { const out = { ...c, start }; start += c.t.length; return out; });
    return { settings: f.settings, dim: f.dim, calls, values: new Int8Array(bytes(f.values).buffer),
      scales: new Float32Array(bytes(f.scales).buffer) };
  }).catch((e) => { indexPromise = null; throw e; });
  return indexPromise;
}

type Extractor = (text: string, opts: { pooling: "mean"; normalize: boolean }) => Promise<{ data: Float32Array }>;
let modelPromise: Promise<Extractor> | null = null;

/** Loads the embedding model once (about 120 MB the first time, then from the browser cache). */
export function loadModel(onProgress?: (percent: number) => void): Promise<Extractor> {
  modelPromise ??= import("@huggingface/transformers").then(async ({ pipeline, env }) => {
    env.allowLocalModels = false;
    const files = new Map<string, [number, number]>();
    const extractor = await pipeline("feature-extraction", cfg.model, {
      dtype: "q8",
      progress_callback: (p: { status: string; file?: string; loaded?: number; total?: number }) => {
        if (p.status !== "progress" || !p.file || !p.total) return;
        files.set(p.file, [p.loaded ?? 0, p.total]);
        let loaded = 0, total = 0;
        for (const [l, t] of files.values()) { loaded += l; total += t; }
        onProgress?.(Math.round((100 * loaded) / total));
      },
    });
    return extractor as unknown as Extractor;
  }).catch((e) => { modelPromise = null; throw e; });
  return modelPromise;
}

export async function embedIdea(text: string, onProgress?: (percent: number) => void): Promise<Float32Array> {
  const extractor = await loadModel(onProgress);
  const out = await extractor(cfg.queryPrefix + text, { pooling: "mean", normalize: true });
  return out.data;
}

/** Calls best first: max(0.5 scope + 0.5 best aspect, best example direction - offset). */
export function scoreIdea(q: Float32Array, index: IdeaIndex): IdeaHit[] {
  const { dim, values, scales } = index;
  const sim = (row: number) => {
    let s = 0;
    const o = row * dim;
    for (let k = 0; k < dim; k++) s += values[o + k] * q[k];
    return s * scales[row];
  };
  const hits: IdeaHit[] = [];
  for (const c of index.calls) {
    const s = c.t.map((_, k) => sim(c.start + k));
    let bestAspect = -1;
    c.t.forEach(([kind], k) => {
      if (kind === "aspect" && (bestAspect < 0 || s[k] > s[bestAspect])) bestAspect = k;
    });
    let score = bestAspect < 0 ? s[0] : 0.5 * s[0] + 0.5 * s[bestAspect];
    let best = bestAspect < 0 ? 0 : bestAspect;
    c.t.forEach(([kind], k) => {
      if (kind === "direction" && s[k] - index.settings.direction_offset > score) {
        score = s[k] - index.settings.direction_offset;
        best = k;
      }
    });
    hits.push({ id: c.id, score, closest: c.t[best] });
  }
  return hits.sort((a, b) => b.score - a.score);
}
