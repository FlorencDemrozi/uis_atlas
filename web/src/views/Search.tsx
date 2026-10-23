import { useEffect, useMemo, useState } from "preact/hooks";
import type { Atlas, Researcher } from "../data";
import { useI18n } from "../i18n";
import { links, replaceHash, type Route } from "../router";
import { buildIndex, search, type Hit } from "../search";
import { inScope, isAll, useSelection } from "../selection";
import { DeptLabel, Highlight, Position, doiUrl } from "../components/common";
import { OrgFilter } from "../components/OrgFilter";

const EXAMPLES = [
  "machine learning for predictive maintenance",
  "CO2 storage in reservoirs",
  "patient safety",
  "early childhood education",
  "tourism and hospitality",
];
const PAGE = 20;

export function SearchView({ atlas, route }: { atlas: Atlas; route: Route }) {
  const { t, num } = useI18n();
  const index = useMemo(() => buildIndex(atlas), [atlas]);
  const [q, setQ] = useState(route.params.get("q") ?? "");
  const [query, setQuery] = useState(q);
  const { sel } = useSelection();
  const [minPubs, setMinPubs] = useState(Number(route.params.get("min") ?? 0));
  const [shown, setShown] = useState(PAGE);

  // Follow hash changes (example clicks, theme links from other views).
  useEffect(() => {
    const next = route.params.get("q") ?? "";
    setQ(next); setQuery(next);
  }, [route.params.get("q")]);

  // Keep the URL shareable without adding history entries per keystroke.
  useEffect(() => {
    const p = new URLSearchParams();
    if (query) p.set("q", query);
    if (minPubs) p.set("min", String(minPubs));
    replaceHash("/", p);
    setShown(PAGE);
  }, [query, sel, minPubs]);

  // Search as you type, lightly debounced.
  useEffect(() => {
    const id = setTimeout(() => setQuery(q.trim()), 180);
    return () => clearTimeout(id);
  }, [q]);

  const hits: Hit[] = useMemo(() => {
    const keep = (r: Researcher) => inScope(sel, r.department) && r.n_publications >= minPubs;
    if (query) return search(index, atlas, query).filter((h) => keep(h.researcher));
    return atlas.researchers.filter(keep)
      .sort((a, b) => (atlas.recent.get(b.scopus_id) ?? 0) - (atlas.recent.get(a.scopus_id) ?? 0)
        || a.name.localeCompare(b.name))
      .map((researcher) => ({ researcher, score: 0, papers: [], terms: [] }));
  }, [index, atlas, query, sel, minPubs]);
  const inScopeCount = useMemo(() => atlas.researchers.filter((r) => inScope(sel, r.department)).length, [atlas, sel]);

  return (
    <>
      <section class="hero-search" aria-labelledby="search-title">
        <h1 id="search-title">{t("search.title")}</h1>
        <p class="lede">{t("search.lede", { n: atlas.researchers.length, f: atlas.meta.faculties.length })}</p>
        <form class="searchbox" role="search" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }}>
          <label for="q" class="visually-hidden">{t("search.label")}</label>
          <input id="q" type="search" value={q} autoComplete="off" placeholder={t("search.placeholder")}
            onInput={(e) => setQ((e.target as HTMLInputElement).value)} />
          <button class="btn primary" type="submit">{t("search.button")}</button>
        </form>
        <div class="examples">
          <span>{t("search.try")}</span>
          {EXAMPLES.map((ex) => <a class="chip-btn" key={ex} href={links.search(ex)}>{ex}</a>)}
        </div>
        {!atlas.meta.has_vectors && <p class="note">{t("search.keywordOnly")}</p>}
      </section>

      <OrgFilter atlas={atlas} />
      <div class="filters" role="group" aria-label={t("search.filters")}>
        <label class="field">{t("filter.minPubs")}
          <select value={String(minPubs)} onChange={(e) => setMinPubs(Number((e.target as HTMLSelectElement).value))}>
            {[0, 5, 10, 20, 40].map((n) => <option key={n} value={String(n)}>{n ? `≥ ${n}` : t("filter.any")}</option>)}
          </select>
        </label>
      </div>

      <div class="results-head">
        <h2 aria-live="polite">
          {query ? t("search.results", { n: hits.length, q: query }) : t("search.browse", { n: hits.length })}
        </h2>
        {!isAll(sel) && <span class="muted small">{t("search.inScope", { n: inScopeCount })}</span>}
        {!query && <span class="muted small">{t("search.browseSort")}</span>}
      </div>

      {query && hits.length === 0 && <p class="muted" style={{ padding: "24px 0" }}>{t("search.none")}</p>}

      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {hits.slice(0, shown).map((h, i) => <ResultItem key={h.researcher.scopus_id} hit={h} rank={i + 1} atlas={atlas} ranked={!!query} />)}
      </ol>
      {shown < hits.length && (
        <p style={{ marginTop: "20px" }}>
          <button class="btn" onClick={() => setShown(shown + PAGE)}>
            {t("search.more", { n: Math.min(PAGE, hits.length - shown) })}
          </button>
          <span class="muted small" style={{ marginLeft: "12px" }}>{t("search.showing", { a: num(shown), b: num(hits.length) })}</span>
        </p>
      )}
    </>
  );
}

function ResultItem({ hit, rank, atlas, ranked }: { hit: Hit; rank: number; atlas: Atlas; ranked: boolean }) {
  const { t, num } = useI18n();
  const r = hit.researcher;
  const kw = (atlas.keywords.get(r.scopus_id) ?? []).slice(0, 6);
  const recent = atlas.recent.get(r.scopus_id) ?? 0;
  return (
    <li class="result">
      <span class="rank">{ranked ? rank : ""}</span>
      <div>
        <h3><a href={links.profile(r.scopus_id)}>{r.name}</a></h3>
        <div class="meta-line">
          <Position r={r} />
          <DeptLabel name={r.department} withFaculty />
          <span>{t("r.pubs", { n: r.n_publications })}</span>
          <span>{t("r.recent", { n: recent, y: String(atlas.meta.period.recent_from) })}</span>
          {ranked && (
            <span class="affinity" title={t("search.affinity")}>
              <span class="track" aria-hidden="true"><span class="fill" style={{ display: "block", width: `${Math.round(hit.score * 100)}%` }} /></span>
              {t("search.affinityPct", { n: Math.round(hit.score * 100) })}
            </span>
          )}
        </div>
        {r.summary
          ? <p class="summary">{r.summary}</p>
          : <p class="summary pending">{t("r.summaryPending")}</p>}
        <div class="tags">
          {(r.tags.length ? r.tags.map((x): [string, number] => [x, 0]) : kw).map(([k]) => (
            <a class="tag" key={k} href={links.search(k)}><Highlight text={k} terms={hit.terms} /></a>
          ))}
        </div>
        {hit.papers.length > 0 && (
          <div class="why">
            <h4>{t("search.why")}</h4>
            <ul>
              {hit.papers.map((eid) => {
                const p = atlas.papers[eid];
                const url = doiUrl(p.doi);
                const title = <Highlight text={p.title} terms={hit.terms} />;
                return (
                  <li key={eid}>
                    {url ? <a href={url}>{title}</a> : title}
                    <span class="muted"> — {p.year}{p.venue ? `, ${p.venue}` : ""}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        <div class="links">
          <a href={links.profile(r.scopus_id)}>{t("r.profile")}</a>
          {r.links.scopus && <a href={r.links.scopus}>Scopus</a>}
          {r.links.orcid && <a href={r.links.orcid}>ORCID</a>}
          <span class="muted">{t("r.citations", { n: num(r.citations) })}</span>
        </div>
      </div>
    </li>
  );
}
