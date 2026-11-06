// Build a team, in the browser. The description and its aspects are embedded here with
// the atlas model ("query:" prefix, search-config.json) and never leave the browser.
// Paper vectors come from data/team.json + team.vectors.bin (pipeline/team_vectors.py:
// titles and keywords only). The method is in team-core.ts (mirrors pipeline/team.py).
import cfg from "./search-config.json";
import type { Atlas } from "./data";
import { loadModel } from "./ideas";
import { applyContext, aspectScores, buildTeam, coauthorSets, gaps, relevance, topPerAspect,
  type Evidence, type Member, type Similarity, type TeamSettings } from "./team-core";

interface TeamFile {
  model: string;
  passage_prefix: string;
  query_prefix: string;
  from_year: number;
  similarity: Similarity;
  settings: TeamSettings;
  dim: number;
  ids: string[];
  scales: string;   // float32 per row, base64
  sha1: string;     // of team.vectors.bin
}

export interface TeamIndex {
  settings: TeamSettings;
  similarity: Similarity;
  fromYear: number;
  dim: number;
  paperIds: string[];
  values: Int8Array;
  scales: Float32Array;
  /** Per vector row: the authors as indices into atlas.researchers. */
  authors: number[][];
  coauthors: Set<number>[];
}

const modelName = (m: string) => m.split("/").pop()!.toLowerCase();
const bytes = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
const hex = (buf: ArrayBuffer) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

let indexPromise: Promise<TeamIndex> | null = null;

/** Loads the paper vectors once (about 7 MB). Rejects when they are missing, were made
 *  with another model, or the two files come from different runs. */
export function loadTeamIndex(atlas: Atlas): Promise<TeamIndex> {
  indexPromise ??= (async () => {
    const [metaRes, binRes] = await Promise.all([fetch("./data/team.json"), fetch("./data/team.vectors.bin")]);
    if (!metaRes.ok || !binRes.ok) throw new Error("no team data");
    const f = (await metaRes.json()) as TeamFile;
    const buf = await binRes.arrayBuffer();
    if (f.query_prefix !== cfg.queryPrefix || modelName(f.model) !== modelName(cfg.model)) {
      throw new Error("model settings differ");
    }
    if (typeof f.similarity?.width !== "number" || typeof f.settings?.context_floor !== "number") {
      throw new Error("team data is from an older version");
    }
    if (crypto.subtle && hex(await crypto.subtle.digest("SHA-1", buf)) !== f.sha1) throw new Error("data files do not match");
    if (buf.byteLength !== f.ids.length * f.dim) throw new Error("data files do not match");
    const idx = new Map(atlas.researchers.map((r, i) => [r.scopus_id, i]));
    const toIdx = (ids: string[]) => ids.map((a) => idx.get(a)).filter((i): i is number => i !== undefined);
    return {
      settings: f.settings, similarity: f.similarity, fromYear: f.from_year, dim: f.dim, paperIds: f.ids,
      values: new Int8Array(buf), scales: new Float32Array(bytes(f.scales).buffer),
      authors: f.ids.map((id) => toIdx(atlas.papers[id]?.uis_author_ids ?? [])),
      coauthors: coauthorSets(Object.values(atlas.papers).map((p) => toIdx(p.uis_author_ids)), atlas.researchers.length),
    };
  })().catch((e) => { indexPromise = null; throw e; });
  return indexPromise;
}

const relCache = new Map<string, Float64Array>();

/** Relevance of every paper for each text; texts already seen are not embedded again. */
export async function relevanceFor(index: TeamIndex, texts: string[], onProgress?: (percent: number) => void):
  Promise<Float64Array[]> {
  const todo = texts.filter((t) => !relCache.has(t));
  if (todo.length) {
    const extractor = await loadModel(onProgress);
    const { dim, values, scales, similarity } = index;
    const n = scales.length;
    for (const text of todo) {
      const q = (await extractor(cfg.queryPrefix + text, { pooling: "mean", normalize: true })).data;
      const sims = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        let s = 0;
        const o = i * dim;
        for (let k = 0; k < dim; k++) s += values[o + k] * q[k];
        sims[i] = s * scales[i];
      }
      relCache.set(text, relevance(sims, similarity));
    }
  }
  return texts.map((t) => relCache.get(t)!);
}

export interface TeamResult {
  aspects: string[];
  team: Member[];
  top: number[][];
  gaps: number[];
  score: Float64Array[];
  evidence: Map<number, Evidence>[];
}

/** contexts[j]: the sentence aspect j was listed in ("" for none), see applyContext. */
export function matchTeam(index: TeamIndex, aspects: string[], contexts: string[], rel: Float64Array[],
  eligible: boolean[], dept: string[]): TeamResult {
  const s = index.settings;
  const raw = aspectScores(rel, index.authors, eligible.length, s.top_papers, s.evidence_papers);
  const score = applyContext(raw.score, aspects, contexts, s);
  const evidence = raw.evidence;
  return {
    aspects, score, evidence,
    team: buildTeam(score, eligible, dept, index.coauthors, s),
    top: topPerAspect(score, eligible, s.per_aspect),
    gaps: gaps(score, eligible, s.covers),
  };
}

