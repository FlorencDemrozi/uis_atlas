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

export function search(index: SearchIndex, atlas: Atlas, query: string): Hit[] {
  const q = query.trim();
  if (!q) return [];
  const top = cfg.topPapersPerResearcher;
  const terms = new Map<string, Set<string>>();
  const addTerms = (id: string, ts: string[]) => {
    const s = terms.get(id) ?? new Set<string>();
    ts.forEach((t) => s.add(t));
    terms.set(id, s);
  };

  // Researcher-level match: name, aggregated keywords, tags, summary.
  const direct = new Map<string, number>();
  for (const h of index.people.search(q)) {
    direct.set(String(h.id), h.score);
    addTerms(String(h.id), h.terms);
  }

  // Paper-level match: a person with several relevant papers outranks one lucky hit,
  // so we average over the top N paper scores (missing papers count as zero).
  const perPerson = new Map<string, { eid: string; score: number }[]>();
  for (const h of index.papers.search(q)) {
    const p = atlas.papers[String(h.id)];
    for (const id of p?.uis_author_ids ?? []) {
      const list = perPerson.get(id) ?? [];
      list.push({ eid: p.eid, score: h.score });
      perPerson.set(id, list);
      addTerms(id, h.terms);
    }
  }
  const paperScore = new Map<string, number>();
  for (const [id, list] of perPerson) {
    list.sort((a, b) => b.score - a.score);
    paperScore.set(id, list.slice(0, top).reduce((s, x) => s + x.score, 0) / top);
  }

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
    hits.push({ researcher, score, papers: best.map((b) => b.eid), terms: [...(terms.get(id) ?? [])] });
  }
  hits.sort((a, b) => b.score - a.score);
  const max = hits[0]?.score || 1;
  hits.forEach((h) => (h.score /= max));
  return hits;
}
