// Side-by-side comparison of shortlisted researchers. A shared link
// (#/shortlist?ids=…) shows that list and offers to save it as your own.
import type { ComponentChildren } from "preact";
import { useState } from "preact/hooks";
import type { Atlas, Researcher } from "../data";
import { downloadCsv, researcherRows } from "../csv";
import { useI18n } from "../i18n";
import { links, type Route } from "../router";
import { useShortlist } from "../shortlist";
import { DeptLabel, Position } from "../components/common";

export function ShortlistView({ atlas, route }: { atlas: Atlas; route: Route }) {
  const i18n = useI18n();
  const { t, num, lang } = i18n;
  const mine = useShortlist();
  const shared = (route.params.get("ids") ?? "").split(",").filter((id) => atlas.byId.has(id));
  const isShared = shared.length > 0 && shared.join(",") !== mine.ids.join(",");
  const ids = isShared ? shared : mine.ids.filter((id) => atlas.byId.has(id));
  const people = ids.map((id) => atlas.byId.get(id)!) as Researcher[];
  const [copied, setCopied] = useState(false);
  const [manual, setManual] = useState(false);

  const shareUrl = `${location.origin}${location.pathname}${links.shortlist(ids)}`;
  const copy = async () => {
    try { await navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 2500); }
    catch { setManual(true); }
  };
  const y = String(atlas.meta.period.recent_from);

  const rows: [string, (r: Researcher) => ComponentChildren][] = [
    [t("csv.position"), (r) => <Position r={r} />],
    [t("filter.department"), (r) => <DeptLabel name={r.department} short={false} withFaculty />],
    [t("ov.publications"), (r) => num(r.n_publications)],
    [t("ov.since", { y }), (r) => num(atlas.recent.get(r.scopus_id) ?? 0)],
    [t("ov.citations"), (r) => num(r.citations)],
    [t("sl.active"), (r) => `${r.first_year}–${r.last_year}`],
    [t("p.topics"), (r) => (
      <div class="tags">{(r.tags.length ? r.tags : (atlas.keywords.get(r.scopus_id) ?? []).slice(0, 6).map(([k]) => k))
        .map((k) => <a class="tag" key={k} href={links.search(k)}>{k}</a>)}</div>)],
    [t("p.uisCoauthors"), (r) => r.top_coauthors.slice(0, 3).map((c, i) => (
      <span key={c.scopus_id}>{i > 0 && ", "}<a href={links.profile(c.scopus_id)}>{c.name}</a></span>))],
    [t("sl.together"), (r) => {
      const others = people.filter((o) => o !== r).map((o) => ({ o, n: r.top_coauthors.find((c) => c.scopus_id === o.scopus_id)?.n_papers ?? 0 }))
        .filter((x) => x.n > 0);
      return others.length ? others.map(({ o, n }) => `${o.name} (${n})`).join(", ") : <span class="muted">—</span>;
    }],
    [t("sl.links"), (r) => (
      <span class="links">
        <a href={links.profile(r.scopus_id)}>{t("r.profile")}</a>
        {r.links.uis && <a href={(lang === "en" && r.links.uis_en) || r.links.uis}>UiS</a>}
        {r.links.scopus && <a href={r.links.scopus}>Scopus</a>}
        {r.links.orcid && <a href={r.links.orcid}>ORCID</a>}
      </span>)],
  ];

  return (
    <>
      <div class="page-head">
        <h1>{t("sl.title")}</h1>
        <p>{t("sl.lede")}</p>
      </div>

      {isShared && (
        <div class="notice" role="status">
          {t("sl.shared", { n: people.length })}
          <button type="button" class="btn primary" onClick={() => mine.set(shared)}>{t("sl.saveShared")}</button>
        </div>
      )}

      {people.length === 0 ? (
        <p class="muted">{t("sl.empty")} <a href={links.search()}>{t("nav.search")}</a></p>
      ) : (<>
        <div class="table-tools">
          <button type="button" class="btn primary" onClick={copy}>{t(copied ? "sl.copied" : "sl.copy")}</button>
          <button type="button" class="btn" onClick={() => downloadCsv("uis-shortlist.csv",
            researcherRows(atlas, i18n, people.map((r) => ({ r }))))}>{t("sl.csv")}</button>
          {!isShared && <button type="button" class="btn" onClick={() => mine.set([])}>{t("sl.clear")}</button>}
        </div>
        {manual && (
          <label class="field share-field">{t("sl.copyManual")}
            <input type="text" readOnly value={shareUrl} onFocus={(e) => (e.target as HTMLInputElement).select()} />
          </label>
        )}
        <div class="scroll-x panel compare-wrap">
          <table class="compare">
            <thead><tr>
              <td />
              {people.map((r) => (
                <th key={r.scopus_id} scope="col">
                  <a href={links.profile(r.scopus_id)}>{r.name}</a>
                  {!isShared && <button type="button" class="link-btn small remove"
                    aria-label={`${t("sl.remove")}: ${r.name}`} onClick={() => mine.remove(r.scopus_id)}>×</button>}
                </th>
              ))}
            </tr></thead>
            <tbody>
              {rows.map(([label, render]) => (
                <tr key={label}><th scope="row">{label}</th>{people.map((r) => <td key={r.scopus_id}>{render(r)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </>)}
    </>
  );
}
