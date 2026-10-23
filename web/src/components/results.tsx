// Result presentations besides the default list: split view (compact list +
// detail pane), sortable table with CSV export, and the shortlist toggle.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Atlas, Researcher } from "../data";
import { downloadCsv, researcherRows } from "../csv";
import { useI18n } from "../i18n";
import { links } from "../router";
import type { Hit } from "../search";
import { useShortlist } from "../shortlist";
import { DeptLabel, Highlight, Position, doiUrl } from "./common";

export function ShortlistButton({ r, compact = false }: { r: Researcher; compact?: boolean }) {
  const { t } = useI18n();
  const { has, toggle } = useShortlist();
  const on = has(r.scopus_id);
  return (
    <button type="button" class={`shortlist-btn${on ? " on" : ""}${compact ? " compact" : ""}`} aria-pressed={on}
      title={t(on ? "sl.remove" : "sl.add")} aria-label={`${t(on ? "sl.remove" : "sl.add")}: ${r.name}`}
      onClick={(e) => { e.stopPropagation(); toggle(r.scopus_id); }}>
      <span aria-hidden="true">{on ? "✓" : "+"}</span>
      {!compact && <span>{t(on ? "sl.added" : "sl.addShort")}</span>}
    </button>
  );
}

export function Affinity({ score }: { score: number }) {
  const { t } = useI18n();
  return (
    <span class="affinity" title={t("search.affinity")}>
      <span class="track" aria-hidden="true"><span class="fill" style={{ display: "block", width: `${Math.round(score * 100)}%` }} /></span>
      {t("search.affinityPct", { n: Math.round(score * 100) })}
    </span>
  );
}

// ------------------------------------------------------------------ split view
export function SplitView({ hits, atlas, ranked, selected, onSelect }: {
  hits: Hit[]; atlas: Atlas; ranked: boolean; selected: string | null; onSelect: (id: string) => void;
}) {
  const { t } = useI18n();
  const current = hits.find((h) => h.researcher.scopus_id === selected) ?? hits[0];
  const listRef = useRef<HTMLOListElement>(null);
  const move = (e: KeyboardEvent, i: number) => {
    const next = e.key === "ArrowDown" ? i + 1 : e.key === "ArrowUp" ? i - 1 : -1;
    if (next < 0 || next >= hits.length) return;
    e.preventDefault();
    onSelect(hits[next].researcher.scopus_id);
    (listRef.current?.querySelectorAll<HTMLButtonElement>(".split-item")[next])?.focus();
  };
  if (!current) return null;
  return (
    <div class="split">
      <ol class="split-list" ref={listRef} aria-label={t("view.resultsList")}>
        {hits.map((h, i) => {
          const r = h.researcher;
          const on = r.scopus_id === current.researcher.scopus_id;
          return (
            <li key={r.scopus_id} class={on ? "on" : ""}>
              <button type="button" class="split-item" aria-current={on ? "true" : undefined}
                onClick={() => onSelect(r.scopus_id)} onKeyDown={(e) => move(e, i)}>
                <span class="rank">{ranked ? i + 1 : ""}</span>
                <span class="split-main">
                  <strong>{r.name}</strong>
                  <DeptLabel name={r.department} />
                </span>
                {ranked && <span class="split-score num">{Math.round(h.score * 100)}%</span>}
              </button>
              <ShortlistButton r={r} compact />
            </li>
          );
        })}
      </ol>
      <ResultDetail hit={current} atlas={atlas} ranked={ranked} />
    </div>
  );
}

function ResultDetail({ hit, atlas, ranked }: { hit: Hit; atlas: Atlas; ranked: boolean }) {
  const { t, num, lang } = useI18n();
  const r = hit.researcher;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const paneRef = useRef<HTMLElement>(null);
  useEffect(() => { if (paneRef.current) paneRef.current.scrollTop = 0; }, [r.scopus_id]);
  const topics = r.tags.length ? r.tags : (atlas.keywords.get(r.scopus_id) ?? []).slice(0, 10).map(([k]) => k);
  const recent = atlas.recent.get(r.scopus_id) ?? 0;
  const papers = hit.papers.length ? hit.papers : r.paper_ids.slice(0, 3);
  return (
    <aside class="split-detail panel" ref={paneRef} aria-labelledby="detail-name" aria-live="polite">
      <h2 id="detail-name" ref={headingRef} tabIndex={-1}><a href={links.profile(r.scopus_id)}>{r.name}</a></h2>
      <div class="meta-line"><Position r={r} /><DeptLabel name={r.department} short={false} withFaculty /></div>
      {ranked && <div class="meta-line"><Affinity score={hit.score} /></div>}
      {r.summary && <p class="summary">{r.summary}</p>}
      <dl class="mini-stats">
        <div><dt>{t("ov.publications")}</dt><dd>{num(r.n_publications)}</dd></div>
        <div><dt>{t("ov.since", { y: String(atlas.meta.period.recent_from) })}</dt><dd>{num(recent)}</dd></div>
        <div><dt>{t("ov.citations")}</dt><dd>{num(r.citations)}</dd></div>
        <div><dt>{t("p.coauthors")}</dt><dd>{num(r.top_coauthors.length)}</dd></div>
      </dl>
      {topics.length > 0 && (<>
        <h3>{t("p.topics")}</h3>
        <div class="tags">{topics.map((k) => <a class="tag" key={k} href={links.search(k)}><Highlight text={k} terms={hit.terms} /></a>)}</div>
      </>)}
      <h3>{t(hit.papers.length ? "search.why" : "view.latest")}</h3>
      <ul class="pubs">
        {papers.map((eid) => {
          const p = atlas.papers[eid];
          if (!p) return null;
          const url = doiUrl(p.doi);
          const title = <Highlight text={p.title} terms={hit.terms} />;
          return <li key={eid}>{url ? <a href={url}>{title}</a> : title}<div class="venue">{p.year}{p.venue ? ` · ${p.venue}` : ""}</div></li>;
        })}
      </ul>
      {r.top_coauthors.length > 0 && (<>
        <h3>{t("p.uisCoauthors")}</h3>
        <p class="small">{r.top_coauthors.slice(0, 5).map((c, i) => (
          <span key={c.scopus_id}>{i > 0 && ", "}<a href={links.profile(c.scopus_id)}>{c.name}</a></span>))}</p>
      </>)}
      <div class="panel-actions">
        <a class="btn primary" href={links.profile(r.scopus_id)}>{t("net.openProfile")}</a>
        <ShortlistButton r={r} />
        {r.links.uis && <a class="btn" href={(lang === "en" && r.links.uis_en) || r.links.uis}>{t("p.uis")}</a>}
      </div>
    </aside>
  );
}

// ------------------------------------------------------------------ table view
type SortKey = "rank" | "name" | "dept" | "pubs" | "recent" | "cit";

export function ResultsTable({ hits, atlas, ranked }: { hits: Hit[]; atlas: Atlas; ranked: boolean }) {
  const i18n = useI18n();
  const { t, num, deptName } = i18n;
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: ranked ? "rank" : "recent", desc: !ranked });
  useEffect(() => setSort({ key: ranked ? "rank" : "recent", desc: !ranked }), [ranked]);

  const rows = useMemo(() => {
    const val = (h: Hit, i: number): number | string => {
      const r = h.researcher;
      switch (sort.key) {
        case "rank": return i;
        case "name": return r.name;
        case "dept": return deptName(r.department, true);
        case "pubs": return r.n_publications;
        case "recent": return atlas.recent.get(r.scopus_id) ?? 0;
        case "cit": return r.citations;
      }
    };
    const list = hits.map((h, i) => ({ h, i, v: val(h, i) }));
    list.sort((a, b) => {
      const c = typeof a.v === "string" ? a.v.localeCompare(String(b.v)) : (a.v as number) - (b.v as number);
      return (sort.desc ? -c : c) || a.i - b.i;
    });
    return list;
  }, [hits, sort, atlas, deptName]);

  const head = (key: SortKey, label: string, numeric = false) => {
    const active = sort.key === key;
    return (
      <th scope="col" class={numeric ? "n" : ""} aria-sort={active ? (sort.desc ? "descending" : "ascending") : "none"}>
        <button type="button" class="sort-btn" onClick={() => setSort({ key, desc: active ? !sort.desc : numeric })}>
          {label}<span aria-hidden="true" class="sort-mark">{active ? (sort.desc ? "▾" : "▴") : ""}</span>
        </button>
      </th>
    );
  };
  const exportCsv = () => downloadCsv("uis-researchers.csv",
    researcherRows(atlas, i18n, rows.map(({ h }) => ({ r: h.researcher, match: ranked ? h.score : undefined }))));

  return (
    <div>
      <div class="table-tools">
        <button type="button" class="btn" onClick={exportCsv}>{t("view.exportCsv", { n: hits.length })}</button>
      </div>
      <div class="scroll-x">
        <table class="data-table results-table">
          <thead><tr>
            {ranked && head("rank", "#", true)}
            {head("name", t("net.name"))}
            {head("dept", t("filter.department"))}
            {head("pubs", t("ov.publications"), true)}
            {head("recent", t("ov.since", { y: String(atlas.meta.period.recent_from) }), true)}
            {head("cit", t("ov.citations"), true)}
            {ranked && <th scope="col" class="n">{t("csv.match")}</th>}
            <th scope="col"><span class="visually-hidden">{t("sl.title")}</span></th>
          </tr></thead>
          <tbody>
            {rows.map(({ h, i }) => {
              const r = h.researcher;
              return (
                <tr key={r.scopus_id}>
                  {ranked && <td class="n">{i + 1}</td>}
                  <td><a href={links.profile(r.scopus_id)}>{r.name}</a><div class="muted small"><Position r={r} /></div></td>
                  <td><DeptLabel name={r.department} withFaculty /></td>
                  <td class="n">{num(r.n_publications)}</td>
                  <td class="n">{num(atlas.recent.get(r.scopus_id) ?? 0)}</td>
                  <td class="n">{num(r.citations)}</td>
                  {ranked && <td class="n">{Math.round(h.score * 100)}%</td>}
                  <td><ShortlistButton r={r} compact /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
