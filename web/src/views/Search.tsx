import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Atlas, Researcher } from "../data";
import { useI18n } from "../i18n";
import { links, replaceHash, type Route } from "../router";
import { buildIndex, search, type Hit } from "../search";
import { inScope, isAll, useSelection } from "../selection";
import { ROLES, isRole, roleOf, type Role } from "../role";
import { DeptLabel, Highlight, Position, paperUrl } from "../components/common";
import { OrgFilter } from "../components/OrgFilter";
import { Explore } from "../components/Explore";
import { Affinity, ResultsTable, ShortlistButton, SplitView } from "../components/results";
import { handTextToTeam } from "../handover";
import en from "../i18n/en.json";

type Mode = "list" | "split" | "table";
const wide = () => matchMedia("(min-width: 1000px)").matches;

// Keyword search matches English titles only, so Norwegian examples are offered
// once meaning-based search (vectors) is available.
const examples = (text: string) => text.split("|");
const PAGE = 20;
/** A query this long is a project description: "Build a team" handles it better. */
const TEAM_HINT_WORDS = 15;
/** ?min= as a number; anything else (missing, "abc", negative) is no minimum. */
const minOf = (v: string | null) => { const n = Number(v ?? 0); return Number.isFinite(n) && n > 0 ? n : 0; };

export function SearchView({ atlas, route }: { atlas: Atlas; route: Route }) {
  const { t, num } = useI18n();
  const index = useMemo(() => buildIndex(atlas), [atlas]);
  const [q, setQ] = useState(route.params.get("q") ?? "");
  const [query, setQuery] = useState(q);
  const { sel } = useSelection();
  const [minPubs, setMinPubs] = useState(minOf(route.params.get("min")));
  const roleParam = route.params.get("role");
  const [role, setRole] = useState<Role | "">(isRole(roleParam) ? roleParam : "");
  const [shown, setShown] = useState(PAGE);
  const param = route.params.get("view");
  const [mode, setMode] = useState<Mode>(param === "split" || param === "table" ? param : "list");
  const [selected, setSelected] = useState<string | null>(route.params.get("r"));
  const [isWide, setWide] = useState(wide);
  useEffect(() => {
    const onResize = () => setWide(wide());
    addEventListener("resize", onResize);
    return () => removeEventListener("resize", onResize);
  }, []);
  const shownMode: Mode = mode === "split" && !isWide ? "list" : mode;

  // Follow every hash change (example clicks, theme links from other views). Typing
  // updates the address without an event, so a link may carry the q the route still has.
  useEffect(() => {
    const next = route.params.get("q") ?? "";
    setQ(next); setQuery(next);
    const r = route.params.get("role");
    setRole(isRole(r) ? r : "");
    setMinPubs(minOf(route.params.get("min")));
  }, [route]);
  useEffect(() => {
    const v = route.params.get("view");
    setMode(v === "split" || v === "table" ? v : "list");
    if (route.params.get("r")) setSelected(route.params.get("r"));
  }, [route.params.get("view"), route.params.get("r")]);

  // Keep the URL shareable without adding history entries per keystroke.
  useEffect(() => {
    const p = new URLSearchParams();
    if (query) p.set("q", query);
    if (minPubs) p.set("min", String(minPubs));
    if (role) p.set("role", role);
    if (mode !== "list") p.set("view", mode);
    if (mode === "split" && selected) p.set("r", selected);
    replaceHash("/", p);
  }, [query, sel, minPubs, role, mode, selected]);
  const firstRun = useRef(true);   // keep a shared ?r= on first load
  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; }
    setShown(PAGE); setSelected(null);
  }, [query, sel, minPubs, role]);

  // Search as you type, lightly debounced.
  useEffect(() => {
    const id = setTimeout(() => setQuery(q.trim()), 180);
    return () => clearTimeout(id);
  }, [q]);

  // Every filter except the role: the role buttons count these researchers.
  const unroled: Hit[] = useMemo(() => {
    const keep = (r: Researcher) => inScope(sel, r.department) && r.n_publications >= minPubs;
    if (query) return search(index, atlas, query).filter((h) => keep(h.researcher));
    return atlas.researchers.filter(keep)
      .sort((a, b) => (atlas.recent.get(b.scopus_id) ?? 0) - (atlas.recent.get(a.scopus_id) ?? 0)
        || a.name.localeCompare(b.name))
      .map((researcher) => ({ researcher, score: 0, papers: [], terms: [] }));
  }, [index, atlas, query, sel, minPubs]);
  const roleCounts = useMemo(() => {
    const c = new Map<Role, number>();
    for (const h of unroled) c.set(roleOf(h.researcher), (c.get(roleOf(h.researcher)) ?? 0) + 1);
    return c;
  }, [unroled]);
  const hits = useMemo(() => role ? unroled.filter((h) => roleOf(h.researcher) === role) : unroled, [unroled, role]);
  // A shared ?r= further down the list: show enough results to include it.
  useEffect(() => {
    if (!selected) return;
    const i = hits.findIndex((h) => h.researcher.scopus_id === selected);
    if (i >= shown) setShown(Math.ceil((i + 1) / PAGE) * PAGE);
  }, [hits, selected]);
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
          {examples(atlas.meta.has_vectors ? t("search.examples") : en["search.examples"]).map((ex) => <a class="chip-btn" key={ex} href={links.search(ex)}>{ex}</a>)}
        </div>
        <p class="note">{t("search.syntax")}</p>
        {!atlas.meta.has_vectors && <p class="note">{t("search.keywordOnly")}</p>}
        {q.trim().split(/\s+/).length >= TEAM_HINT_WORDS && (
          <p class="warn small" role="note">{t("search.teamHint")}{" "}
            <a href={links.builder} onClick={() => handTextToTeam(q.trim())}>{t("search.teamLink")}</a></p>
        )}
        <DataSources atlas={atlas} />
      </section>

      <OrgFilter atlas={atlas}>
        <label class="field">{t("filter.minPubs")}
          <select value={String(minPubs)} onChange={(e) => setMinPubs(Number((e.target as HTMLSelectElement).value))}>
            {[0, 5, 10, 20, 40].map((n) => <option key={n} value={String(n)}>{n ? `≥ ${n}` : t("filter.any")}</option>)}
          </select>
        </label>
        <fieldset class="role-filter">
          <legend>{t("filter.role")}</legend>
          {(["", ...ROLES] as const).map((x) => (
            <label key={x || "all"} class={`role-option${role === x ? " on" : ""}`}>
              <input type="radio" name="role" value={x} checked={role === x} onChange={() => setRole(x)} />
              <span>{t(x ? `role.${x}` : "role.all")}</span>
              <span class="muted num">{num(x ? roleCounts.get(x) ?? 0 : unroled.length)}</span>
            </label>
          ))}
        </fieldset>
      </OrgFilter>

      {!query && <Explore atlas={atlas} />}

      <div class="results-head">
        <h2 aria-live="polite">
          {query ? t("search.results", { n: hits.length, q: query }) : t("search.browse", { n: hits.length })}
        </h2>
        {!isAll(sel) && <span class="muted small">{t("search.inScope", { n: inScopeCount })}</span>}
        {!query && <span class="muted small">{t("search.browseSort")}</span>}
        <span class="segmented view-switch" role="group" aria-label={t("view.label")}>
          {(["list", "split", "table"] as Mode[]).filter((m) => m !== "split" || isWide).map((m) => (
            <button key={m} type="button" aria-pressed={shownMode === m} onClick={() => setMode(m)}>{t(`view.${m}`)}</button>
          ))}
        </span>
      </div>

      {query && hits.length === 0 && <p class="muted" style={{ padding: "24px 0" }}>{t("search.none")}</p>}

      {shownMode === "table" && <ResultsTable hits={hits} atlas={atlas} ranked={!!query} />}
      {shownMode === "split" && (
        <SplitView hits={hits.slice(0, shown)} atlas={atlas} ranked={!!query} selected={selected} onSelect={setSelected} />
      )}
      {shownMode === "list" && (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {hits.slice(0, shown).map((h, i) => <ResultItem key={h.researcher.scopus_id} hit={h} rank={i + 1} atlas={atlas} ranked={!!query} />)}
        </ol>
      )}
      {shownMode !== "table" && shown < hits.length && (
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

const SOURCES: [string, string, string][] = [   // [key, name, link]
  ["scopus", "Scopus", "https://www.scopus.com/"],
  ["nva", "NVA", "https://nva.sikt.no/"],
  ["pubmed", "PubMed", "https://pubmed.ncbi.nlm.nih.gov/"],
  ["directory", "UiS", "https://www.uis.no/nb/sok/ansatte"],
];

/** Where the data comes from and how often it is refreshed (home page). */
function DataSources({ atlas }: { atlas: Atlas }) {
  const { t, lang } = useI18n();
  const date = new Date(atlas.meta.generated).toLocaleDateString(lang === "nb" ? "nb-NO" : "en-GB",
    { day: "numeric", month: "long", year: "numeric" });
  return (
    <div class="data-sources" aria-labelledby="h-sources">
      <h2 id="h-sources" class="visually-hidden">{t("src.title")}</h2>
      <p class="note"><span aria-hidden="true">⟳ </span>{t("src.weekly", { date })}</p>
      <details>
        <summary>{t("src.lead")}: {SOURCES.map(([, name]) => name).join(" · ")}</summary>
        <ul>
          {SOURCES.map(([key, , href]) => {
            // "Name (detail): description" -> the name part links to the source.
            const [head, ...rest] = t(`src.${key}`, { from: String(atlas.meta.period.first_year) }).split(": ");
            return <li key={key}><a href={href}>{head}</a>: {rest.join(": ")}</li>;
          })}
        </ul>
      </details>
    </div>
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
        <div class="result-title">
          <h3><a href={links.profile(r.scopus_id)}>{r.name}</a></h3>
          <ShortlistButton r={r} />
        </div>
        <div class="meta-line">
          <Position r={r} />
          <DeptLabel name={r.department} withFaculty />
          <span>{t("r.pubs", { n: r.n_publications })}</span>
          <span>{t("r.recent", { n: recent, y: String(atlas.meta.period.recent_from) })}</span>
          {ranked && <Affinity score={hit.score} />}
        </div>
        {r.summary && <p class="summary">{r.summary}</p>}
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
                const url = paperUrl(p);
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
