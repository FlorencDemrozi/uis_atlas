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
  n_publications: number;
  citations: number;
  pubs_per_year: Record<string, number>;
  first_year: number;
  last_year: number;
  top_coauthors: Coauthor[];
  collab_departments: Record<string, number>;
  paper_ids: string[];
  links: Record<string, string>;
}

export interface Paper {
  eid: string;
  title: string;
  year: string;
  venue: string | null;
  type: string | null;
  doi: string | null;
  citations: number;
  keywords: string[];
  uis_author_ids: string[];
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

export function aggregateKeywords(paperIds: string[], papers: Record<string, Paper>, limit = 25) {
  const count = new Map<string, number>();
  const spelling = new Map<string, Map<string, number>>();
  for (const id of paperIds) {
    for (const k of papers[id]?.keywords ?? []) {
      const key = k.toLowerCase();
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
  const [researchers, papers, stats, meta] = await Promise.all([
    getJson<Researcher[]>("researchers.json"),
    getJson<Record<string, Paper>>("papers.json"),
    getJson<Stats>("stats.json"),
    getJson<Meta>("meta.json"),
  ]);
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
