// Overview statistics for the selected faculties/departments, computed in the
// browser so any mix of units is exact (same logic as pipeline/export_public.py).
import type { Atlas, Researcher } from "./data";
import { isNotStated, orderedDepts, orderedFaculties } from "./org";
import { unitKey, type Level } from "./selection";

export interface UnitTotals { researchers: number; papers: number; citations: number }

export interface ScopedStats {
  level: Level;
  order: string[];                                   // unit keys in display order
  units: Map<string, UnitTotals>;
  perYear: Map<string, Map<string, number>>;
  collab: Map<string, number>;                       // "a|b" (both directions)
  collabMax: number;
  themes: Map<string, [string, number][]>;
  totals: UnitTotals & { crossUnit: number };
  perYearAll: Map<string, number>;
}

export function scopedStats(atlas: Atlas, people: Researcher[], level: Level): ScopedStats {
  const unitOf = new Map(people.map((r) => [r.scopus_id, unitKey(r.department, level)]));
  const units = new Map<string, UnitTotals>();
  const get = (u: string) => units.get(u) ?? units.set(u, { researchers: 0, papers: 0, citations: 0 }).get(u)!;
  for (const r of people) get(unitOf.get(r.scopus_id)!).researchers++;

  const perYear = new Map<string, Map<string, number>>();
  const perYearAll = new Map<string, number>();
  const themeCount = new Map<string, Map<string, number>>();
  const collab = new Map<string, number>();
  const totals = { researchers: people.length, papers: 0, citations: 0, crossUnit: 0 };
  for (const p of Object.values(atlas.papers)) {
    const us = new Set(p.uis_author_ids.map((id) => unitOf.get(id)).filter((u): u is string => !!u));
    if (!us.size) continue;
    totals.papers++;
    totals.citations += p.citations ?? 0;
    perYearAll.set(p.year, (perYearAll.get(p.year) ?? 0) + 1);
    const real = [...us].filter((u) => !isNotStated(u)).sort();
    if (real.length > 1) totals.crossUnit++;
    for (const u of us) {
      const t = get(u);
      t.papers++;
      t.citations += p.citations ?? 0;
      const y = perYear.get(u) ?? perYear.set(u, new Map()).get(u)!;
      y.set(p.year, (y.get(p.year) ?? 0) + 1);
      const th = themeCount.get(u) ?? themeCount.set(u, new Map()).get(u)!;
      for (const k of new Set(p.keywords.map((k) => k.toLowerCase()))) th.set(k, (th.get(k) ?? 0) + 1);
    }
    for (let i = 0; i < real.length; i++) {
      for (let j = i + 1; j < real.length; j++) {
        for (const key of [`${real[i]}|${real[j]}`, `${real[j]}|${real[i]}`]) collab.set(key, (collab.get(key) ?? 0) + 1);
      }
    }
  }
  const themes = new Map([...themeCount].map(([u, m]): [string, [string, number][]] =>
    [u, [...m].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 20)]));
  const order = level === "faculty"
    ? orderedFaculties(units.keys()).map((f) => f.key)
    : orderedDepts(units.keys()).map((d) => d.key);
  return { level, order, units, perYear, perYearAll, collab, collabMax: Math.max(1, ...collab.values()), themes, totals };
}
