// Build a team: the matching method, mirrored line by line from pipeline/team.py.
// tests/test_team.py runs both on the same inputs and checks that they agree, so
// change both together. No imports: the test runs this file directly with Node.

export interface TeamSettings {
  top_papers: number;
  covers: number;
  per_aspect: number;
  evidence_papers: number;
  team_size: number;
  min_gain: number;
  coauthor_bonus: number;
  new_department_bonus: number;
  context_floor: number;
  context_full: number;
  max_aspects: number;
  max_item_words: number;
}

// Sentence ends: . ! ? before a capital, digit or quote ("e.g. dementia" stays whole); ; and : always.
const SENTENCE_END = /(?<=[.!?])\s+(?=[A-Z0-9"'(ÆØÅ])|(?<=[;:])\s+/;
const CUE = /\b(?:such as|for example|for instance|e\.g\.|including|for eksempel|slik som|f\.eks\.|blant annet|bl\.a\.|inkludert)\s+/i;
const CONJ = /\s+(?:and|or|as well as|og|eller|samt)\s+/i;
const LEADING_CONJ = /^(?:and|or|og|eller|samt)\s+/i;
const ARTICLE = /^(?:the|a|an)\s+/i;
const LAST_PREP = /^.*\b(?:from|with|of|on|in|using|via|by|for|to|fra|med|av|på|ved|gjennom|om)\s+/i;
const RELATIVE = /^(?:which|that|who|where|som|der|hvor)\b/i;
const TRIM = /^[\s"'(\[]+|[\s"')\].,;:!?]+$/g;
const STOP = new Set(("a an and are as at be by for from in into is of on or the to with without using via based this that " +
  "these those we our its it would could will can may og i på av for med til en et den det som om fra ved " +
  "under mellom vi vår").split(" "));

const words = (s: string) => s.split(" ").filter(Boolean);
const clean = (s: string) => words(s).join(" ").replace(TRIM, "");

function usable(item: string, maxWords: number): boolean {
  const w = words(item);
  return w.length > 0 && w.length <= maxWords && item.length >= 3 && !RELATIVE.test(item)
    && w.some((x) => !STOP.has(x.toLowerCase()));
}

/** Python's re.split for a pattern without groups: every match splits. */
const splitAll = (s: string, re: RegExp) => s.split(new RegExp(re.source, re.flags.replace("g", "") + "g"));

function splitOnce(s: string, re: RegExp): string[] {
  const m = re.exec(s);
  return m ? [s.slice(0, m.index), s.slice(m.index + m[0].length)] : [s];
}

/** One listed thing: without a leading "and"/"the"; a longer phrase is cut to the words
 *  after its last preposition ("analyse consequences for equity" -> "equity"). */
function item(part: string): string {
  const p = clean(clean(part).replace(LEADING_CONJ, "").replace(ARTICLE, ""));
  return words(p).length > 3 ? clean(p.replace(LAST_PREP, "")) : p;
}

/** The listed things in one sentence: after "such as" and the like, or in a list of
 *  three or more comma-separated parts. */
export function listItems(sentence: string, maxWords: number): string[] {
  const cue = CUE.exec(sentence);
  if (cue) {
    const parts: string[] = [];
    for (const p of sentence.slice(cue.index + cue[0].length).split(",")) {
      parts.push(...splitAll(clean(p).replace(LEADING_CONJ, ""), CONJ));
    }
    return parts.map(item).filter((p) => usable(p, maxWords));
  }
  const parts = sentence.split(",").map(clean);
  if (parts.length < 3) return [];
  const first = parts[0].replace(LAST_PREP, "");
  const last = splitOnce(parts[parts.length - 1].replace(LEADING_CONJ, ""), CONJ);
  return [first, ...parts.slice(1, -1), ...last].map(item).filter((p) => usable(p, maxWords));
}

/** [aspect, context]: the whole description first, then each sentence (three words or
 *  more) followed by the things it lists. The context of a listed thing is the sentence
 *  it comes from (or the whole description when that is the same sentence); "" for the
 *  rest. Duplicates are dropped. */
export function splitAspectsWithContext(text: string, maxAspects: number, maxWords: number): [string, string][] {
  const whole = clean(text.replace(/\s+/g, " "));
  const out: [string, string][] = [];
  const seen = new Set<string>();
  const add = (s: string, ctx: string) => {
    const key = s.toLowerCase();
    if (s && !seen.has(key) && out.length < maxAspects) { seen.add(key); out.push([s, ctx]); }
  };
  add(whole, "");
  for (const raw of splitAll(whole, SENTENCE_END)) {
    const s = clean(raw);
    if (words(s).length >= 3) add(s, "");
    const ctx = seen.has(s.toLowerCase()) ? out.find(([a]) => a.toLowerCase() === s.toLowerCase())![0] : "";
    for (const x of listItems(s, maxWords)) add(x, ctx);
  }
  return out;
}

export const splitAspects = (text: string, maxAspects: number, maxWords: number) =>
  splitAspectsWithContext(text, maxAspects, maxWords).map(([a]) => a);

/** A listed thing counts in the context of its sentence, as team.apply_context: a
 *  person's score for it is multiplied by context_floor + (1 - context_floor) x
 *  min(1, their score for that sentence / context_full). Aspects whose context is not
 *  among the aspects (removed, or added by hand) are left as they are. */
export function applyContext(score: Float64Array[], aspects: string[], contexts: string[], cfg: TeamSettings): Float64Array[] {
  const index = new Map(aspects.map((a, k) => [a, k]));
  return score.map((s, j) => {
    const k = contexts[j] ? index.get(contexts[j]) : undefined;
    if (k === undefined || k === j) return s;
    return s.map((x, r) => x * (cfg.context_floor + (1 - cfg.context_floor) * Math.min(1, score[k][r] / cfg.context_full)));
  });
}

export interface Similarity { min: number; percentile: number; width: number }

/** The similarity at which a paper starts to count for one aspect: the value at rank
 *  floor(percentile x (n - 1)) of the sorted similarities, at least sim.min. */
export function floor(sims: Float64Array, sim: Similarity): number {
  if (!sims.length) return sim.min;
  const s = Float64Array.from(sims).sort();
  return Math.max(sim.min, s[Math.floor(sim.percentile * (s.length - 1))]);
}

/** Relevance of every paper for one aspect, 0 at the floor, 1 at floor + width. */
export function relevance(sims: Float64Array, sim: Similarity): Float64Array {
  const lo = floor(sims, sim);
  return sims.map((x) => Math.min(1, Math.max(0, (x - lo) / sim.width)));
}

export type Evidence = [number, number][];   // [relevance, paper row], best first

/** rel[j][i]: relevance of paper row i for aspect j. score[j][r] is the mean relevance of
 *  person r's `top` best papers; evidence[j] maps a person to their best papers. */
export function aspectScores(rel: Float64Array[], authors: number[][], nPeople: number, top: number, nEvidence: number):
  { score: Float64Array[]; evidence: Map<number, Evidence>[] } {
  const score: Float64Array[] = [];
  const evidence: Map<number, Evidence>[] = [];
  for (const col of rel) {
    const per = new Map<number, Evidence>();
    for (let i = 0; i < col.length; i++) {
      if (!(col[i] > 0)) continue;
      for (const a of authors[i]) {
        const list = per.get(a);
        if (list) list.push([col[i], i]); else per.set(a, [[col[i], i]]);
      }
    }
    const s = new Float64Array(nPeople);
    const ev = new Map<number, Evidence>();
    for (const [a, list] of per) {
      list.sort((x, y) => y[0] - x[0] || x[1] - y[1]);
      s[a] = list.slice(0, top).reduce((t, x) => t + x[0], 0) / top;
      ev.set(a, list.slice(0, Math.max(top, nEvidence)));
    }
    score.push(s);
    evidence.push(ev);
  }
  return { score, evidence };
}

export interface Member { person: number; gain: number; adds: [number, number][] }

/** Greedy coverage, as team.build_team: each round adds the eligible person whose scores
 *  add most above what the team already covers (at least min_gain); co-authors of the
 *  team and new departments are preferred when gains are close. */
export function buildTeam(score: Float64Array[], eligible: boolean[], dept: string[], coauthors: Set<number>[],
  cfg: TeamSettings): Member[] {
  const m = score.length;
  const n = eligible.length;
  const covered = new Array<number>(m).fill(0);
  const team: Member[] = [];
  const chosen = new Set<number>();
  const depts = new Set<string>();
  while (team.length < cfg.team_size) {
    let best = -1, bestVal = 0, bestGain = 0;
    for (let r = 0; r < n; r++) {
      if (!eligible[r] || chosen.has(r)) continue;
      let gain = 0;
      for (let j = 0; j < m; j++) {
        const d = score[j][r] - covered[j];
        if (d > 0) gain += d;
      }
      if (gain < cfg.min_gain) continue;
      let val = gain;
      if ([...chosen].some((t) => coauthors[r].has(t))) val *= 1 + cfg.coauthor_bonus;
      if (team.length && !depts.has(dept[r])) val *= 1 + cfg.new_department_bonus;
      if (val > bestVal) { best = r; bestVal = val; bestGain = gain; }
    }
    if (best < 0) break;
    const adds: [number, number][] = [];
    for (let j = 0; j < m; j++) if (score[j][best] > covered[j]) adds.push([j, score[j][best] - covered[j]]);
    adds.sort((x, y) => y[1] - x[1] || x[0] - y[0]);
    for (let j = 0; j < m; j++) covered[j] = Math.max(covered[j], score[j][best]);
    team.push({ person: best, gain: bestGain, adds });
    chosen.add(best);
    depts.add(dept[best]);
  }
  return team;
}

/** Per aspect the k eligible people with the highest score (above 0), ties by order. */
export function topPerAspect(score: Float64Array[], eligible: boolean[], k: number): number[][] {
  return score.map((s) => {
    const people: number[] = [];
    for (let r = 0; r < eligible.length; r++) if (eligible[r] && s[r] > 0) people.push(r);
    people.sort((a, b) => s[b] - s[a] || a - b);
    return people.slice(0, k);
  });
}

/** Aspects nobody eligible covers (best score below `covers`). */
export function gaps(score: Float64Array[], eligible: boolean[], covers: number): number[] {
  const out: number[] = [];
  score.forEach((s, j) => {
    let best = 0;
    for (let r = 0; r < eligible.length; r++) if (eligible[r] && s[r] > best) best = s[r];
    if (best < covers) out.push(j);
  });
  return out;
}

/** For each person, everyone who shares at least one paper with them. */
export function coauthorSets(paperAuthors: number[][], nPeople: number): Set<number>[] {
  const out = Array.from({ length: nPeople }, () => new Set<number>());
  for (const authors of paperAuthors) for (const a of authors) for (const b of authors) if (a !== b) out[a].add(b);
  return out;
}
