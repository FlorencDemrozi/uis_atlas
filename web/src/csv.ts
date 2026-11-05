// Client-side CSV download (UTF-8 with BOM so Excel opens Norwegian letters correctly).
import type { Atlas, Researcher } from "./data";
import type { I18nValue } from "./i18n";

const cell = (v: unknown) => {
  let s = v == null ? "" : String(v);
  // Text starting like a formula is not run by spreadsheet programs (CSV injection).
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",;\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
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

/** Full address of a researcher's Atlas profile (no faculty filter, so it opens the same for anyone). */
const atlasLink = (id: string) => `${location.origin}${location.pathname}#/r/${encodeURIComponent(id)}`;

/** One row per researcher, with an optional match column. */
export function researcherRows(atlas: Atlas, i18n: I18nValue, people: { r: Researcher; match?: number }[]) {
  const { t, deptName, lang } = i18n;
  const y = String(atlas.meta.period.recent_from);
  const withMatch = people.some((p) => p.match !== undefined);
  const header = [t("net.name"), t("filter.faculty"), t("filter.department"), t("csv.position"), t("csv.email"),
    t("ov.publications"), t("ov.since", { y }), t("ov.citations"), ...(withMatch ? [t("csv.match")] : []),
    t("csv.atlas"), t("p.uis"), "Scopus", "ORCID"];
  return [header, ...people.map(({ r, match }) => [
    r.name, deptName(r.faculty), deptName(r.department), r.position?.[lang] ?? r.position?.nb ?? "", r.email ?? "",
    r.n_publications, atlas.recent.get(r.scopus_id) ?? 0, r.citations,
    ...(withMatch ? [match === undefined ? "" : `${Math.round(match * 100)}%`] : []),
    atlasLink(r.scopus_id), (lang === "en" && r.links.uis_en) || r.links.uis || "", r.links.scopus ?? "", r.links.orcid ?? "",
  ])];
}
