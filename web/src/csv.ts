// Client-side CSV download (UTF-8 with BOM so Excel opens Norwegian letters correctly).
import type { Atlas, Researcher } from "./data";
import type { I18nValue } from "./i18n";

const cell = (v: unknown) => {
  const s = v == null ? "" : String(v);
  return /[",;\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function downloadCsv(filename: string, rows: unknown[][]) {
  const text = "﻿" + rows.map((r) => r.map(cell).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** One row per researcher, with an optional match column. */
export function researcherRows(atlas: Atlas, i18n: I18nValue, people: { r: Researcher; match?: number }[]) {
  const { t, deptName, lang } = i18n;
  const y = String(atlas.meta.period.recent_from);
  const withMatch = people.some((p) => p.match !== undefined);
  const header = [t("net.name"), t("filter.faculty"), t("filter.department"), t("csv.position"),
    t("ov.publications"), t("ov.since", { y }), t("ov.citations"), ...(withMatch ? [t("csv.match")] : []),
    t("p.uis"), "Scopus", "ORCID"];
  return [header, ...people.map(({ r, match }) => [
    r.name, deptName(r.faculty), deptName(r.department), r.position?.[lang] ?? r.position?.nb ?? "",
    r.n_publications, atlas.recent.get(r.scopus_id) ?? 0, r.citations,
    ...(withMatch ? [match === undefined ? "" : `${Math.round(match * 100)}%`] : []),
    (lang === "en" && r.links.uis_en) || r.links.uis || "", r.links.scopus ?? "", r.links.orcid ?? "",
  ])];
}
