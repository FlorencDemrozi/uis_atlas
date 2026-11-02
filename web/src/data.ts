// Loads the licence-safe export (data/public/, copied to public/data/ by sync-data).

export interface Coauthor { scopus_id: string; name: string; n_papers: number }

export interface Researcher {
  scopus_id: string;
  name: string;
  orcid: string | null;
  faculty: string;
  department: string;
  position: { nb: string | null; en: string | null } | null;
  summary: string | null;
  tags: string[];
  /** Publications only (articles, books, chapters, conference papers, reports, PhD theses). */
  n_publications: number;
  /** Of n_publications, with a UiS affiliation (absent in older exports). */
  n_uis?: number;
  /** All research output per category (see CATEGORIES), most frequent first. */
  output_types?: Record<string, number>;
  /** Papers without a UiS affiliation (earlier or other employers). */
  other_paper_ids?: string[];
  /** As shown on the Scopus author page (all years, all affiliations). */
  scopus_metrics?: { documents: number | null; citations: number | null; h_index: number | null } | null;
  citations: number;
  pubs_per_year: Record<string, number>;
  first_year: number;
  last_year: number;
  top_coauthors: Coauthor[];
  collab_departments: Record<string, number>;
  paper_ids: string[];
  links: Record<string, string>;
}

/** As in papers.json, where empty fields are left out and the id is the key. */
type StoredPaper = Partial<Paper> & { title: string; year: string };

export interface Paper {
  eid: string;
  title: string;
  year: string;
  venue: string | null;
  type: string | null;
  doi: string | null;
  /** null: not in Scopus (NVA only), no citation count. */
  citations: number | null;
  keywords: string[];
  uis_author_ids: string[];
  /** Output category (pipeline/config.py OUTPUT_CATEGORIES); absent in older exports. */
  category?: string;
  /** NVA record, for outputs found only in NVA. */
  url?: string | null;
}

/** Output categories in display order (pipeline/config.py OUTPUT_CATEGORIES). */
export const CATEGORIES = ["article", "book", "chapter", "conference", "report", "thesis",
  "artistic", "presentation", "popular", "media", "other"];
const PUBLICATION_CATEGORIES = new Set(["article", "book", "chapter", "conference", "report", "thesis"]);

/** Counted as a publication (unit statistics, papers per year); see config.PUBLICATION_CATEGORIES. */
export function isPublication(p: Paper): boolean {
  return PUBLICATION_CATEGORIES.has(p.category ?? "article");
}

export interface UnitStats {
  units: Record<string, { researchers: number; papers: number; citations: number }>;
  papers_per_year: Record<string, Record<string, number>>;
  collaboration: { a: string; b: string; papers: number }[];
  top_themes: Record<string, [string, number][]>;
}

export interface Stats { departments: UnitStats; faculties: UnitStats }

export interface Rule { min: number; from: number }

export interface Meta {
  generated: string;
  institution: string;
  faculties: { name: string; departments: string[] }[];
  period: { first_year: number; recent_from: number };
  inclusion: { confirmed: Rule; unconfirmed: Rule };
  n_researchers: number;
  n_papers: number;
  has_summaries: boolean;
  has_vectors: boolean;
}

export interface Atlas {
  researchers: Researcher[];
  byId: Map<string, Researcher>;
  papers: Record<string, Paper>;
  stats: Stats;
  meta: Meta;
  /** Per researcher: topic keywords aggregated from their papers, most frequent first. */
  keywords: Map<string, [string, number][]>;
  /** Per researcher: number of papers since meta.period.recent_from. */
  recent: Map<string, number>;
  /** Last complete publication year (the export year is still in progress). */
  lastFullYear: number;
}

async function getJson<T>(name: string): Promise<T> {
  const res = await fetch(`./data/${name}`);
  if (!res.ok) throw new Error(`Could not load ${name} (${res.status})`);
  return res.json() as Promise<T>;
}

/** Key that merges case and simple plural variants ("Wind turbines" ~ "wind turbine"). */
export function kwKey(k: string): string {
  const s = k.toLowerCase().trim();
  return /[a-z]{3}[^siu]s$/.test(s) ? s.slice(0, -1) : s;
}

export function aggregateKeywords(paperIds: string[], papers: Record<string, Paper>, limit = 25) {
  const count = new Map<string, number>();
  const spelling = new Map<string, Map<string, number>>();
  for (const id of paperIds) {
    for (const k of papers[id]?.keywords ?? []) {
      const key = kwKey(k);
      count.set(key, (count.get(key) ?? 0) + 1);
      const s = spelling.get(key) ?? new Map<string, number>();
      s.set(k, (s.get(k) ?? 0) + 1);
      spelling.set(key, s);
    }
  }
  const upper = (s: string) => s.replace(/[^A-Z]/g, "").length;
  return [...count.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([key, n]): [string, number] => {
      const best = [...spelling.get(key)!.entries()].sort((a, b) => b[1] - a[1] || upper(b[0]) - upper(a[0]))[0][0];
      return [best, n];
    });
}

export async function loadAtlas(): Promise<Atlas> {
  const [researchers, stored, stats, meta] = await Promise.all([
    getJson<Researcher[]>("researchers.json"),
    getJson<Record<string, StoredPaper>>("papers.json"),
    getJson<Stats>("stats.json"),
    getJson<Meta>("meta.json"),
  ]);
  const papers: Record<string, Paper> = {};
  for (const [eid, p] of Object.entries(stored)) {
    papers[eid] = {
      venue: null, type: null, doi: null, citations: null, keywords: [], uis_author_ids: [], ...p, eid,
      url: eid.startsWith("nva-") ? `https://nva.sikt.no/registration/${eid.slice(4)}` : null,
    };
  }
  const keywords = new Map<string, [string, number][]>();
  const recent = new Map<string, number>();
  for (const r of researchers) {
    keywords.set(r.scopus_id, aggregateKeywords(r.paper_ids, papers));
    recent.set(r.scopus_id, Object.entries(r.pubs_per_year)
      .filter(([y]) => Number(y) >= meta.period.recent_from)
      .reduce((s, [, n]) => s + n, 0));
  }
  return {
    researchers, papers, stats, meta, keywords, recent,
    byId: new Map(researchers.map((r) => [r.scopus_id, r])),
    lastFullYear: new Date(meta.generated).getFullYear() - 1,
  };
}
