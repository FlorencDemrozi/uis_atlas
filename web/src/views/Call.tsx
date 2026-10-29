import { useState } from "preact/hooks";
import type { Atlas } from "../data";
import { callTitle, isInstitutionLevel, pick, useCallDetail, type Call, type Funding, type Match } from "../funding";
import { useI18n } from "../i18n";
import { links } from "../router";
import { CategoryBadge, FieldList, Freshness, FundingGate, MatchDetails, SourceBadge, StatusBadge, useFmt } from "../components/funding";

// The agreed field list, grouped as on the page (pipeline/build_calls.py, pipeline/eu.py).
// EU topics add the hierarchy (programme part, call), stages and cut-offs, the number
// of grants, the grant model and Norway's participation; fields a source never has are
// not shown.
const GROUPS: [string, string[]][] = [
  ["overview", ["summary", "description", "status", "funder", "programme", "programme_part", "parent_call", "scheme",
    "action_type", "opening_date", "deadline", "preliminary_deadline", "full_proposal_deadline", "deadline_model",
    "cutoff_dates", "rolling", "published", "updated", "call_id"]],
  ["financial", ["min_amount", "max_amount", "total_budget", "expected_grants", "currency", "funding_model",
    "funding_rate", "eligible_costs", "funding_restrictions", "cofunding"]],
  ["project", ["min_duration_months", "max_duration_months", "earliest_start", "latest_start", "latest_end",
    "orientation", "open_field", "institution_level", "trl", "structural_requirements", "deliverables", "expected_impact"]],
  ["eligibility", ["norway_eligible", "target_groups", "uis_can_apply", "eligible_applicants", "pi_requirements", "career_stage",
    "nationality_residency", "partner_requirements", "international", "international_rules", "consortium_size",
    "mandatory_partners", "industry_public_participation", "application_limits", "subcontracting", "mobility"]],
  ["evaluation", ["evaluation_criteria", "evaluation_weights", "priorities", "procedure", "required_documents",
    "ethics", "data_management", "open_science", "if_granted"]],
];

export function CallView({ atlas, id }: { atlas: Atlas; id: string }) {
  return <FundingGate>{(data) => <CallPage atlas={atlas} data={data} id={id} />}</FundingGate>;
}

function CallPage({ atlas, data, id }: { atlas: Atlas; data: Funding; id: string }) {
  const { t, lang } = useI18n();
  const fmt = useFmt();
  const call = data.byId.get(id);
  const detail = useCallDetail(data, call);
  if (!call) {
    return <div class="page-head"><h1>{t("f.notFound")}</h1><p><a href={links.funding()}>{t("f.back")}</a></p></div>;
  }
  if (detail === "loading") return <p class="loading" role="status">{t("f.loadingCall")}</p>;
  if (detail === "error") return <p class="muted">{t("f.errorCall")}</p>;
  const f = call.fields;
  const status = f.status.v as string;
  const matches = data.matches[call.id] ?? [];
  const url = f.url.v as { nb?: string; en?: string };
  const sections = ["overview", "scope", "financial", "project", "eligibility", "evaluation", "researchers",
    "collaborators", "sources", "history"];

  return (
    <>
      <p class="small" style={{ marginBottom: "16px" }}><a href={links.funding()}>← {t("f.back")}</a></p>
      <header class="profile-head">
        <h1>{callTitle(call, lang)}</h1>
        <div class="meta-line">
          <StatusBadge status={status} />
          <SourceBadge call={call} />
          <span>{pick<string>((call.source === "eu" ? f.programme : f.funder).v, lang).value}</span>
          {f.scheme.v && <span>{pick<string>(f.scheme.v, lang).value}</span>}
          {call.source === "eu" && <span class="num">{f.call_id.v}</span>}
          {f.deadline.v && <span>{t("f.deadline")}: <strong>{fmt.date(f.deadline.v, true)}</strong></span>}
          {!f.deadline.v && f.rolling.v && <span>{t("f.rolling")}</span>}
        </div>
        <div class="links">
          {url.nb && <a href={url.nb}>{t("f.official")}</a>}
          {url.en && <a href={url.en}>{t(call.source === "eu" ? "f.officialEu" : "f.officialEn")}</a>}
        </div>
        {call.closed_by_date && <p class="warn small" role="note">{t("f.closedByDate")}</p>}
        {call.review.length > 0 && (
          <p class="warn small" role="note"><strong>{t("f.review")}:</strong> {t("f.reviewText")} ({call.review.join("; ")})</p>
        )}
      </header>

      <nav class="toc" aria-label={t("f.toc")}>
        {sections.map((s) => <a key={s} href={links.call(call.id)} onClick={(e) => {
          e.preventDefault();
          document.getElementById(`sec-${s}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}>{t(`f.sec.${s}`)}</a>)}
      </nav>

      <section class="section" id="sec-overview" aria-labelledby="h-overview">
        <h2 id="h-overview">{t("f.sec.overview")}</h2>
        <FieldList names={GROUPS[0][1]} call={call} />
      </section>

      <ScopeSection call={call} />

      {GROUPS.slice(1).map(([key, names]) => (
        <section class="section" id={`sec-${key}`} key={key} aria-labelledby={`h-${key}`}>
          <h2 id={`h-${key}`}>{t(`f.sec.${key}`)}</h2>
          <FieldList names={names} call={call} />
        </section>
      ))}

      <ResearchersSection atlas={atlas} data={data} call={call} matches={matches} />
      <CollaboratorsSection atlas={atlas} call={call} matches={matches} />

      <section class="section" id="sec-sources" aria-labelledby="h-sources">
        <h2 id="h-sources">{t("f.sec.sources")}</h2>
        <FieldList names={["url", "documents", "themes"]} call={call} />
        <p class="small muted">{t(call.source === "eu" ? "f.docsNoteEu" : "f.docsNote")}</p>
        <p class="small muted">{t("f.extracted", { date: fmt.date(call.fetched, true) })}</p>
      </section>

      <section class="section" id="sec-history" aria-labelledby="h-history">
        <h2 id="h-history">{t("f.sec.history")}</h2>
        {(call.history ?? []).length <= 1 ? <p class="muted small">{t("f.noChanges")}</p> : (
          <ul class="history">
            {[...(call.history ?? [])].reverse().map((h, i) => (
              <li key={i}><span class="muted num">{fmt.date(h.date)}</span>{" "}
                {h.field === "new" ? t("f.change.new") : h.field === "text" ? t("f.change.text")
                  : h.field === "unlisted" ? t("f.change.unlisted")
                  : t("f.change.field", { field: t(`fld.${h.field === "target_groups" ? "target_groups" : h.field}`),
                    old: show(h.old, lang), new: show(h.new, lang) })}</li>
            ))}
          </ul>
        )}
      </section>
      <Freshness data={data} />
    </>
  );
}

function show(v: unknown, lang: "nb" | "en"): string {
  if (v == null) return "–";
  if (typeof v === "object" && !Array.isArray(v)) {
    const x = pick<unknown>(v as Record<string, unknown>, lang).value;
    return Array.isArray(x) ? x.join(", ") : String(x ?? "–");
  }
  return Array.isArray(v) ? v.join(", ") : String(v);
}

function ScopeSection({ call }: { call: Call }) {
  const { t } = useI18n();
  const p = call.profile;
  const aspects = call.aspects ?? [];
  const list = (key: string, items: string[]) => items.length > 0 && (
    <div class="scope-block"><h3>{t(key)}</h3><ul>{items.map((x) => <li key={x}>{x}</li>)}</ul></div>
  );
  return (
    <section class="section" id="sec-scope" aria-labelledby="h-scope">
      <h2 id="h-scope">{t("f.sec.scope")}</h2>
      {p ? (
        <>
          <p class="sub"><span class="src-badge ai">{t("f.badge.ai")}</span> {t("f.aiProfileNote")}</p>
          {p.disciplines.length > 0 && (
            <div class="scope-block"><h3>{t("f.disciplines")}</h3>
              <ul>{p.disciplines.map((d) => <li key={d.path.join(">")}>{d.path.join(" → ")}
                {d.level === "secondary" && <span class="muted small"> · {t("f.secondary")}</span>}</li>)}</ul></div>
          )}
          {p.topics.length > 0 && (
            <div class="scope-block"><h3>{t("f.topics")}</h3>
              <ul>{p.topics.map((x) => (
                <li key={x.path.join(">")}>{x.path.join(" → ")}{" "}
                  <span class={`src-badge ${x.basis === "explicit" ? "explicit" : "ai"}`}>
                    {t(x.basis === "explicit" ? "f.badge.explicit" : "f.interpretation")}</span>
                  {x.evidence && <details class="ev"><summary>{t("f.showSource")}</summary><q>{x.evidence}</q></details>}
                </li>))}</ul></div>
          )}
          <div class="cols-2">
            {list("f.objectives", p.objectives)}
            {list("f.challenges", p.challenges)}
            {list("f.methods", p.methods)}
            {list("f.technologies", p.technologies)}
            {list("f.expertise", p.contributing_expertise ?? [])}
            {list("f.domains", p.application_domains)}
            {list("f.contributions", p.expected_contributions)}
            {list("f.interdisciplinary", p.interdisciplinary)}
          </div>
          {p.competencies.length > 0 && (
            <div class="scope-block"><h3>{t("f.competencies")}</h3>
              {["core", "complementary", "mandatory_partner", "optional"].map((k) => {
                const items = p.competencies.filter((c) => c.kind === k);
                return items.length > 0 && (
                  <div key={k}><h4>{t(`f.kind.${k}`)}</h4>
                    <ul>{items.map((c) => <li key={c.name}><strong>{c.name}</strong> – {c.rationale}
                      {c.evidence && <details class="ev"><summary>{t("f.showSource")}</summary><q>{c.evidence}</q></details>}</li>)}</ul>
                  </div>
                );
              })}
            </div>
          )}
          <div class="scope-block interpretation">
            <h3>{t("f.interpretation")} <span class="src-badge ai">{t("f.badge.ai")}</span></h3>
            <p><strong>{t("f.interp.problems")}:</strong> {p.interpretation.problems}</p>
            <p><strong>{t("f.interp.projects")}:</strong> {p.interpretation.suitable_projects}</p>
            <p><strong>{t("f.interp.teams")}:</strong> {p.interpretation.competitive_teams}</p>
            {list("f.interp.explicit", p.interpretation.explicit_directions)}
            {list("f.interp.plausible", p.interpretation.plausible_directions)}
          </div>
        </>
      ) : (
        <>
          <p class="sub">{t("f.noProfile")}</p>
          <FieldList names={["themes", "research_scope"]} call={call} />
        </>
      )}
      {aspects.length > 0 && (
        <div class="scope-block">
          <h3>{t("f.aspects")}</h3>
          <p class="small muted">{t("f.aspectsSub")}</p>
          <ul>{aspects.map((a, i) => <li key={i}>{a.label} <span class="muted small">· {t(`f.kind.${a.kind}`)}</span></li>)}</ul>
        </div>
      )}
      {(call.title_terms?.length ?? 0) > 0 && (
        <p class="small muted">{t("f.titleTerms", { terms: call.title_terms!.join(", ") })}</p>
      )}
    </section>
  );
}

function ResearchersSection({ atlas, data, call, matches }:
  { atlas: Atlas; data: Funding; call: Call; matches: Match[] }) {
  const { t } = useI18n();
  const [showLow, setShowLow] = useState(false);
  const closed = call.fields.status.v === "closed";
  const strong = matches.filter((m) => m.category !== "low");
  const weak = matches.filter((m) => m.category === "low");
  const shown = showLow ? matches : strong.length ? strong : matches.slice(0, 5);
  return (
    <section class="section" id="sec-researchers" aria-labelledby="h-researchers">
      <h2 id="h-researchers">{t("f.sec.researchers")}</h2>
      {closed ? <p class="muted">{t("f.closedNoMatch")}</p>
        : isInstitutionLevel(call) ? <p>{t("f.institutionLevel")}{call.fields.institution_level?.ev && <> <q>{call.fields.institution_level.ev}</q></>}</p>
        : call.fields.open_field?.v ? <OpenFieldSummary atlas={atlas} call={call} />
        : matches.length === 0 ? <p class="muted">{t("f.noMatches")}</p> : (
        <>
          <p class="sub">{t("f.matchLede", { y: String(data.meta.papers_from_year) })}</p>
          <ol class="match-list">
            {shown.map((m) => <li key={m.id}><MatchDetails atlas={atlas} call={call} m={m} who /></li>)}
          </ol>
          {!showLow && strong.length > 0 && weak.length > 0 && (
            <button type="button" class="btn" onClick={() => setShowLow(true)}>{t("f.showLow", { n: weak.length })}</button>
          )}
        </>
      )}
    </section>
  );
}

/** Open-field calls: everyone is offered the call; counts by eligibility and the rules used. */
function OpenFieldSummary({ atlas, call }: { atlas: Atlas; call: Call }) {
  const { t, num } = useI18n();
  const restricted = Object.values(call.open_eligibility ?? {});
  const count = (s: string) => restricted.filter(([status]) => status === s).length;
  const unlikely = count("likely_ineligible"), check = count("check") + count("partner_only");
  const rules = Object.entries(call.eligibility_evidence ?? {}).filter(([reason, ev]) => ev && !reason.startsWith("position_"));
  return (
    <>
      <p>{t("f.openField")}{call.fields.open_field.ev && <> <q>{call.fields.open_field.ev}</q></>}</p>
      {call.open_role && <p><strong>{t("f.openRole")}:</strong> {t(`f.role.${call.open_role}`)}</p>}
      <p class="sub">{t("f.openFieldCounts", { a: num(atlas.researchers.length - unlikely - check), b: num(check), c: num(unlikely) })}</p>
      {rules.length > 0 && (
        <ul class="small">
          {rules.map(([reason, ev]) => <li key={reason}>{t(`f.reason.${reason}`)} <q>{ev}</q></li>)}
        </ul>
      )}
      <p class="small muted">{t("f.openFieldHow")}</p>
    </>
  );
}

function CollaboratorsSection({ atlas, call, matches }: { atlas: Atlas; call: Call; matches: Match[] }) {
  const { t } = useI18n();
  const aspects = call.aspects ?? [];
  if (!matches.length || !aspects.length) return null;
  return (
    <section class="section" id="sec-collaborators" aria-labelledby="h-collaborators">
      <h2 id="h-collaborators">{t("f.sec.collaborators")}</h2>
      <h3 style={{ marginTop: "8px" }}>{t("f.coverageTitle")}</h3>
      <p class="sub">{t("f.coverageSub")}</p>
      <dl class="coverage">
        {aspects.map((a, j) => {
          const who = matches.filter((m) => m.matched.some((x) => x.aspect === j));
          return (
            <div key={j}>
              <dt>{a.label}</dt>
              <dd>{who.length ? who.map((m, i) => {
                const r = atlas.byId.get(m.id);
                return r && <span key={m.id}>{i > 0 && ", "}<a href={links.profile(m.id)}>{r.name}</a> <CategoryBadge m={m} /></span>;
              }) : <span class="muted">{t("f.coverageNobody")}</span>}</dd>
            </div>
          );
        })}
      </dl>
      <p class="small muted">{t("f.collabNote")}</p>
    </section>
  );
}
