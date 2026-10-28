// Affinity ranking (docs/SPEC.md §4). For now keyword-only (BM25 via MiniSearch);
// the semantic score from multilingual-e5-small is added once vectors.bin exists.
import MiniSearch from "minisearch";
import type { Atlas, Researcher } from "./data";
import cfg from "./search-config.json";

export interface Hit {
  researcher: Researcher;
  score: number;          // 0–1, relative to the best hit
  papers: string[];       // papers that contributed most ("why this match")
  terms: string[];        // matched query terms, for highlighting
}

export interface SearchIndex { people: MiniSearch; papers: MiniSearch }

const fuzzy = (term: string) => (term.length > 4 ? 0.2 : false);
// Common English and Norwegian filler words: never matched or highlighted.
export const STOPWORDS = new Set(("a an and are as at be by for from in into is of on or the to with without using via based " +
  "og i på av for med til en et den det som om fra ved under mellom").split(" "));
const processTerm = (term: string) => {
  const t = term.toLowerCase();
  return STOPWORDS.has(t) ? null : t;
};

export function buildIndex(atlas: Atlas): SearchIndex {
  const people = new MiniSearch({
    fields: ["name", "keywords", "tags", "summary"],
    processTerm,
    searchOptions: { boost: { name: 3, tags: 2, keywords: 1.5 }, prefix: true, fuzzy },
  });
  people.addAll(atlas.researchers.map((r) => ({
    id: r.scopus_id,
    name: r.name,
    keywords: (atlas.keywords.get(r.scopus_id) ?? []).map(([k]) => k).join(" ; "),
    tags: r.tags.join(" ; "),
    summary: r.summary ?? "",
  })));
  const papers = new MiniSearch({
    fields: ["title", "keywords"],
    processTerm,
    searchOptions: { boost: { keywords: 1.5 }, prefix: true, fuzzy },
  });
  papers.addAll(Object.values(atlas.papers).map((p) => ({
    id: p.eid, title: p.title, keywords: p.keywords.join(" ; "),
  })));
  return { people, papers };
}

// Query syntax: "exact phrase", AND, OR (operators in capitals, so an ordinary
// "and" in a sentence stays a word). AND binds tighter than OR:
// a AND b OR c = (a AND b) OR c. Plain words next to each other form one group
// in which any word may match (more matches rank higher), as before; a phrase
// next to other terms without an operator counts as OR.
export interface Term { phrase: boolean; text: string }

export function parseQuery(query: string): Term[][] {
  const clauses: Term[][] = [[]];
  let words: string[] = [];
  let joined = true;              // the next term joins the current clause (start or after AND)
  const push = (term: Term) => {
    if (!joined) clauses.push([]);
    clauses[clauses.length - 1].push(term);
    joined = false;
  };
  const flush = () => {
    if (words.length) push({ phrase: false, text: words.join(" ") });
    words = [];
  };
  for (const m of query.matchAll(/"([^"]*)"?|(\S+)/g)) {
    if (m[1] !== undefined) {
      flush();
      if (m[1].trim()) push({ phrase: true, text: m[1].trim() });
    } else if (m[2] === "AND" || m[2] === "OR") {
      flush();
      if (m[2] === "AND" && clauses[clauses.length - 1].length) joined = true;
      if (m[2] === "OR") joined = false;
    } else {
      words.push(m[2]);
    }
  }
  flush();
  return clauses.filter((c) => c.length);
}

// Lower case, punctuation and hyphens as spaces: "Computer-Science" matches "computer science".
const normalise = (s: string) => ` ${s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim()} `;

interface TermResult {
  direct: Map<string, number>;                   // researcher-level score
  papers: Map<string, Map<string, number>>;      // researcher -> paper -> score
  terms: Map<string, Set<string>>;               // researcher -> matched terms, for highlighting
}

function searchTerm(index: SearchIndex, atlas: Atlas, term: Term): TermResult {
  const res: TermResult = { direct: new Map(), papers: new Map(), terms: new Map() };
  const addTerms = (id: string, ts: string[]) => {
    const s = res.terms.get(id) ?? new Set<string>();
    ts.forEach((t) => s.add(t));
    res.terms.set(id, s);
  };
  // A phrase: every word must occur (exact, no prefix or spelling tolerance) and the
  // words must stand next to each other, in order, within one field.
  const phrase = term.phrase ? normalise(term.text) : "";
  const opts = term.phrase ? { combineWith: "AND" as const, prefix: false, fuzzy: false } : {};
  const has = (...texts: (string | undefined)[]) => texts.some((t) => t && normalise(t).includes(phrase));
  if (term.phrase && !term.text.split(/\s+/).some((w) => processTerm(w))) return res;  // only filler words

  for (const h of index.people.search(term.text, opts)) {
    const id = String(h.id);
    const r = atlas.byId.get(id);
    if (term.phrase && !(r && has(r.name, r.summary ?? undefined, ...r.tags,
      ...(atlas.keywords.get(id) ?? []).map(([k]) => k)))) continue;
    res.direct.set(id, h.score);
    addTerms(id, term.phrase ? [term.text] : h.terms);
  }
  for (const h of index.papers.search(term.text, opts)) {
    const p = atlas.papers[String(h.id)];
    if (!p || (term.phrase && !has(p.title, ...p.keywords))) continue;
    for (const id of p.uis_author_ids ?? []) {
      const list = res.papers.get(id) ?? new Map<string, number>();
      list.set(p.eid, h.score);
      res.papers.set(id, list);
      addTerms(id, term.phrase ? [term.text] : h.terms);
    }
  }
  return res;
}

/** Adds b into a: scores of the same researcher or paper are summed. */
function merge(a: TermResult, b: TermResult, only?: Set<string>): void {
  const keep = (id: string) => !only || only.has(id);
  for (const [id, s] of b.direct) if (keep(id)) a.direct.set(id, (a.direct.get(id) ?? 0) + s);
  for (const [id, list] of b.papers) {
    if (!keep(id)) continue;
    const into = a.papers.get(id) ?? new Map<string, number>();
    for (const [eid, s] of list) into.set(eid, (into.get(eid) ?? 0) + s);
    a.papers.set(id, into);
  }
  for (const [id, ts] of b.terms) {
    if (!keep(id)) continue;
    const into = a.terms.get(id) ?? new Set<string>();
    ts.forEach((t) => into.add(t));
    a.terms.set(id, into);
  }
}

export function search(index: SearchIndex, atlas: Atlas, query: string): Hit[] {
  const top = cfg.topPapersPerResearcher;
  const all: TermResult = { direct: new Map(), papers: new Map(), terms: new Map() };
  for (const clause of parseQuery(query.trim())) {
    // AND: only researchers matched by every term of the clause.
    const parts = clause.map((term) => searchTerm(index, atlas, term));
    const ids = parts.map((r) => new Set([...r.direct.keys(), ...r.papers.keys()]));
    const both = new Set([...ids[0]].filter((id) => ids.every((s) => s.has(id))));
    for (const r of parts) merge(all, r, both);   // OR: clauses add up
  }

  // Paper-level match: a person with several relevant papers outranks one lucky hit,
  // so we average over the top N paper scores (missing papers count as zero).
  const perPerson = new Map<string, { eid: string; score: number }[]>();
  const paperScore = new Map<string, number>();
  for (const [id, list] of all.papers) {
    const sorted = [...list].map(([eid, score]) => ({ eid, score })).sort((a, b) => b.score - a.score);
    perPerson.set(id, sorted);
    paperScore.set(id, sorted.slice(0, top).reduce((s, x) => s + x.score, 0) / top);
  }
  const direct = all.direct;

  const maxDirect = Math.max(1e-9, ...direct.values());
  const maxPaper = Math.max(1e-9, ...paperScore.values());
  const recentFrom = atlas.meta.period.recent_from;
  const hits: Hit[] = [];
  for (const id of new Set([...direct.keys(), ...paperScore.keys()])) {
    const researcher = atlas.byId.get(id);
    if (!researcher) continue;
    const best = (perPerson.get(id) ?? []).slice(0, top);
    const recentShare = best.length
      ? best.filter((b) => Number(atlas.papers[b.eid].year) >= recentFrom).length / best.length : 0;
    const score = 0.4 * ((direct.get(id) ?? 0) / maxDirect)
      + 0.6 * ((paperScore.get(id) ?? 0) / maxPaper)
      + cfg.recencyBoost * recentShare;
    hits.push({ researcher, score, papers: best.map((b) => b.eid), terms: [...(all.terms.get(id) ?? [])] });
  }
  hits.sort((a, b) => b.score - a.score);
  const max = hits[0]?.score || 1;
  hits.forEach((h) => (h.score /= max));
  return hits;
}
