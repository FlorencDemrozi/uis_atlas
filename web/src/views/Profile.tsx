import type { Atlas, Paper } from "../data";
import { dept, orderedDepts } from "../org";
import { useI18n } from "../i18n";
import { links } from "../router";
import { BarList, ColumnChart } from "../components/charts";
import { DeptLabel, Position, doiUrl } from "../components/common";
import { useState } from "preact/hooks";
import { CategoryBadge, EligibilityBadge, FundingGate, MatchDetails, SourceBadge, StatusBadge, useFmt } from "../components/funding";
import { FAMILIES, callTitle, familyOf, nextDeadline, openFieldCallsFor, pick, useFunding, type Call,
  type Funding } from "../funding";

/** Calls open to all research fields (e.g. FRIPRO), offered to everyone with their eligibility. */
function OpenFieldCalls({ data, id, keep }: { data: Funding; id: string; keep: (c: Call) => boolean }) {
  const { t, lang } = useI18n();
  const fmt = useFmt();
  const all = openFieldCallsFor(data, id).filter(({ call }) => keep(call));
  if (!all.length) return null;
  const likely = all.filter((x) => x.eligibility.status !== "likely_ineligible");
  const unlikely = all.filter((x) => x.eligibility.status === "likely_ineligible");
  const row = ({ call, eligibility }: (typeof all)[number]) => {
    const d = nextDeadline(call) ?? call.fields.deadline.v;
    return (
      <li key={call.id}>
        <a href={links.call(call.id)}>{callTitle(call, lang)}</a> <SourceBadge call={call} />
        <span class="muted small"> · {d ? fmt.date(d, true) : call.fields.rolling.v ? t("f.rolling") : t("f.noDeadline")}
          {fmt.range(call) && ` · ${fmt.range(call)}`}</span>
        <EligibilityBadge e={eligibility} />
        {call.open_role && <span class="muted small"> · {t(`f.role.${call.open_role}`)}</span>}
      </li>
    );
  };
  return (
    <div class="open-field">
      <h3>{t("f.openFieldTitle")}</h3>
      <p class="small muted">{t("f.openFieldSub")}</p>
      <ul class="open-field-list">{likely.map(row)}</ul>
      {unlikely.length > 0 && (
        <details class="unspecified">
          <summary>{t("f.openFieldIneligible", { n: unlikely.length })}</summary>
          <ul class="open-field-list">{unlikely.map(row)}</ul>
        </details>
      )}
    </div>
  );
}

/** Funding calls that fit this researcher's recent work (password-protected data). */
function ProfileFunding({ atlas, id, name }: { atlas: Atlas; id: string; name: string }) {
  const { t, lang } = useI18n();
  const fmt = useFmt();
  const { state } = useFunding();
  const [fam, setFam] = useState("");
  if (state.status === "missing") return null;
  // Source / programme filter: NFR, all EU, or one EU programme family.
  const keep = (c: Call) => !fam || (fam === "eu" ? c.source === "eu" : familyOf(c) === fam);
  return (
    <section class="section funding-profile" aria-labelledby="h-funding">
      <h2 id="h-funding">{t("f.profileTitle")}</h2>
      <FundingGate compact>{(data) => {
        // Strong and medium matches; if there are none, the best weaker ones.
        const every = data.byResearcher.get(id) ?? [];
        const all = every.filter(({ call }) => keep(call));
        const strong = all.filter(({ match }) => match.category !== "low");
        const items = strong.length ? strong : all.slice(0, 3);
        const present = new Set([...every.map(({ call }) => familyOf(call)),
          ...openFieldCallsFor(data, id).map(({ call }) => familyOf(call))]);
        return (
          <>
            <p class="sub">{t("f.profileSub", { name, y: String(data.meta.papers_from_year) })}</p>
            {present.size > 1 && (
              <label class="field inline">
                <span>{t("f.family")}</span>
                <select value={fam} onChange={(e) => setFam((e.target as HTMLSelectElement).value)}>
                  <option value="">{t("f.any")}</option>
                  {[...present].some((x) => x !== "nfr") && <option value="eu">{t("f.family.eu")}</option>}
                  {FAMILIES.filter((x) => present.has(x)).map((x) => <option key={x} value={x}>{t(`f.family.${x}`)}</option>)}
                </select>
              </label>
            )}
            {items.length === 0 ? <p class="muted small">{t("f.profileNone")}</p> : (
              <ul class="call-list compact">
                {items.map(({ call, match }) => {
                  const d = nextDeadline(call) ?? call.fields.deadline.v;
                  return (
                    <li class="call-card" key={call.id}>
                      <div class="call-main">
                        <h3><a href={links.call(call.id)}>{callTitle(call, lang)}</a> <CategoryBadge m={match} /></h3>
                        <p class="meta-line">
                          <StatusBadge status={call.fields.status.v} />
                          <SourceBadge call={call} />
                          <span>{pick<string>((call.source === "eu" ? call.fields.programme : call.fields.funder).v, lang).value}</span>
                          <span>{t("f.deadline")}: {d ? fmt.date(d, true) : call.fields.rolling.v ? t("f.rolling") : t("f.noDeadline")}</span>
                          {fmt.range(call) && <span>{fmt.range(call)}</span>}
                        </p>
                        <MatchDetails atlas={atlas} call={call} m={match} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <OpenFieldCalls data={data} id={id} keep={keep} />
          </>
        );
      }}</FundingGate>
    </section>
  );
}

export function ProfileView({ atlas, id }: { atlas: Atlas; id: string }) {
  const { t, num, deptName, lang } = useI18n();
  const ptype = (type: string) => { const s = t(`ptype.${type}`); return s.startsWith("ptype.") ? type : s; };
  const r = atlas.byId.get(id);
  if (!r) {
    return (
      <div class="page-head">
        <h1>{t("p.notFound")}</h1>
        <p><a href={links.search()}>{t("p.back")}</a></p>
      </div>
    );
  }
  const color = dept(r.department).color;
  const lastYear = new Date(atlas.meta.generated).getFullYear();
  const years: string[] = [];
  // From the person's first year (at least the last 10 years), not the whole period.
  const fromYear = Math.max(atlas.meta.period.first_year, Math.min(r.first_year ?? lastYear, lastYear - 9));
  for (let y = fromYear; y <= lastYear; y++) years.push(String(y));
  const keywords = atlas.keywords.get(r.scopus_id) ?? [];
  const recent = atlas.recent.get(r.scopus_id) ?? 0;
  const byYear = new Map<string, Paper[]>();
  for (const eid of r.paper_ids) {
    const p = atlas.papers[eid];
    if (!p) continue;
    byYear.set(p.year, [...(byYear.get(p.year) ?? []), p]);
  }
  const collabDepts = orderedDepts(Object.keys(r.collab_departments));

  return (
    <>
      <p class="small" style={{ marginBottom: "16px" }}><a href={links.search()} onClick={(e) => {
        if (history.length > 1) { e.preventDefault(); history.back(); }
      }}>← {t("p.back")}</a></p>

      <header class="profile-head">
        <h1>{r.name}</h1>
        <div class="meta-line">
          <Position r={r} />
          <DeptLabel name={r.department} short={false} withFaculty />
          <span>{t("p.active", { a: String(r.first_year), b: String(r.last_year) })}</span>
        </div>
        {r.summary
          ? <p class="summary" style={{ fontSize: "17px" }}>{r.summary}
            <br /><span class="muted small">{t("p.autoSummary")}</span></p>
          : <p class="summary pending">{t("r.summaryPending")}</p>}
        <div class="links">
          <a href={links.networkFocus(r.scopus_id)}>{t("p.exploreNetwork")}</a>
          {r.links.scopus && <a href={r.links.scopus}>{t("p.scopus")}</a>}
          {r.links.orcid && <a href={r.links.orcid}>ORCID</a>}
          {r.links.uis && <a href={(lang === "en" && r.links.uis_en) || r.links.uis}>{t("p.uis")}</a>}
          {r.links.cristin && <a href={r.links.cristin}>Cristin</a>}
        </div>
      </header>

      <div class="tiles" style={{ marginTop: "24px" }}>
        <div class="tile"><div class="label">{t("ov.publications")}</div><div class="value">{num(r.n_publications)}</div>
          <div class="hint">{t("ov.since", { y: String(atlas.meta.period.first_year) })}</div></div>
        <div class="tile"><div class="label">{t("p.recent")}</div><div class="value">{num(recent)}</div>
          <div class="hint">{t("ov.since", { y: String(atlas.meta.period.recent_from) })}</div></div>
        <div class="tile"><div class="label">{t("ov.citations")}</div><div class="value">{num(r.citations)}</div>
          <div class="hint">{t("ov.citationsHint")}</div></div>
        <div class="tile"><div class="label">{t("p.coauthors")}</div><div class="value">{num(r.top_coauthors.length)}</div>
          <div class="hint">{t("p.coauthorsHint")}</div></div>
      </div>

      <div class="profile-grid">
        <div>
          <section aria-labelledby="h-topics">
            <h2 id="h-topics" style={{ marginBottom: "8px" }}>{t("p.topics")}</h2>
            <div class="tags">
              {(r.tags.length ? r.tags.map((x): [string, number] => [x, 0]) : keywords.slice(0, 20)).map(([k, n]) => (
                <a class="tag" key={k} href={links.search(k)}>{k}{n > 1 && <span class="n">{n}</span>}</a>
              ))}
            </div>
          </section>

          <ProfileFunding atlas={atlas} id={r.scopus_id} name={r.name} />

          <section class="section" aria-labelledby="h-pubs">
            <h2 id="h-pubs">{t("p.publications", { n: r.n_publications })}</h2>
            {[...byYear.entries()].map(([year, papers]) => (
              <div class="pub-year" key={year}>
                <h3>{year} <span class="muted">· {papers.length}</span></h3>
                <ul class="pubs">
                  {papers.map((p) => {
                    const url = doiUrl(p.doi);
                    const others = p.uis_author_ids.filter((x) => x !== r.scopus_id)
                      .map((x) => atlas.byId.get(x)).filter((x) => !!x);
                    return (
                      <li key={p.eid}>
                        {url ? <a href={url}>{p.title}</a> : p.title}
                        <div class="venue">
                          {[p.venue, p.type && ptype(p.type)].filter(Boolean).join(" · ")}
                          {p.citations > 0 && ` · ${t("r.citations", { n: num(p.citations) })}`}
                          {others.length > 0 && <> · {t("p.with")} {others.map((o, i) => (
                            <span key={o!.scopus_id}>{i > 0 && ", "}<a href={links.profile(o!.scopus_id)}>{o!.name}</a></span>
                          ))}</>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </section>
        </div>

        <aside>
          <section class="panel" aria-labelledby="h-years">
            <h2 id="h-years" style={{ fontSize: "17px", marginBottom: "8px" }}>{t("ov.perYear")}</h2>
            <ColumnChart color={color} unit={t("chart.papers")} height={150} ariaLabel={t("ov.perYear")}
              data={years.map((y) => ({ x: y, y: r.pubs_per_year[y] ?? 0, partial: Number(y) === lastYear }))} />
          </section>

          <section class="panel" style={{ marginTop: "20px" }} aria-labelledby="h-co">
            <h2 id="h-co" style={{ fontSize: "17px", marginBottom: "8px" }}>{t("p.uisCoauthors")}</h2>
            {r.top_coauthors.length ? (
              <ul class="people">
                {r.top_coauthors.map((c) => {
                  const co = atlas.byId.get(c.scopus_id);
                  return (
                    <li key={c.scopus_id}>
                      <span class="dept">
                        <span class="dot" style={{ background: dept(co?.department ?? "").color }} aria-hidden="true" />
                        <a href={links.profile(c.scopus_id)}>{c.name}</a>
                      </span>
                      <span class="muted num">{t("p.jointPapers", { n: c.n_papers })}</span>
                    </li>
                  );
                })}
              </ul>
            ) : <p class="muted small">{t("p.noCoauthors")}</p>}
          </section>

          {collabDepts.length > 0 && (
            <section class="panel" style={{ marginTop: "20px" }} aria-labelledby="h-cd">
              <h2 id="h-cd" style={{ fontSize: "17px", marginBottom: "4px" }}>{t("p.collabDepts")}</h2>
              <p class="muted small" style={{ marginBottom: "10px" }}>{t("p.collabDeptsSub")}</p>
              <BarList ariaLabel={t("p.collabDepts")} rows={collabDepts.map((d) => ({
                key: d.key, label: deptName(d.key, true), value: r.collab_departments[d.key], color: d.color }))} />
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
