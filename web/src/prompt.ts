// Gathers what "Prepare AI prompt" needs from the atlas and the unlocked funding export
// (full call details are loaded first) and hands it to prompt-core.ts.
import type { Atlas, Researcher } from "./data";
import { callTitle, loadDetail, pick, type Call, type Field, type Funding } from "./funding";
import { paperUrl } from "./components/common";
import { buildPrompt, type Evidence, type PromptCall, type PromptField, type PromptInput, type PromptPackage,
  type PromptPrefs, type PromptResearcher } from "./prompt-core";

const INLINE_LIMIT = 60_000;   // characters; about 15 000 tokens
const FIELD_LIMIT = 12_000;  // per call field; the split into two files handles size
const RECENT_PAPERS = 12;

// Call fields per section, with English labels (the prompt is in English).
const SECTIONS: [string, [string, string][]][] = [
  ["Overview", [["scheme", "Scheme"], ["call_id", "Call identifier"], ["status", "Status"],
    ["opening_date", "Opens"], ["preliminary_deadline", "Pre-proposal deadline"], ["deadline", "Deadline"],
    ["full_proposal_deadline", "Full proposal deadline"], ["rolling", "Rolling submission"]]],
  ["Scope and objectives", [["summary", "Summary"], ["research_scope", "Scope"], ["description", "Description"],
    ["priorities", "Priorities"], ["themes", "Themes"], ["orientation", "Orientation"]]],
  ["Expected outcomes", [["expected_impact", "Expected outcomes and impact"], ["deliverables", "Deliverables"]]],
  ["Budget and duration", [["total_budget", "Total budget"], ["min_amount", "Minimum grant"],
    ["max_amount", "Maximum grant"], ["expected_grants", "Expected number of grants"], ["funding_rate", "Funding rate"],
    ["min_duration_months", "Minimum duration (months)"], ["max_duration_months", "Maximum duration (months)"],
    ["earliest_start", "Earliest start"], ["latest_start", "Latest start"], ["latest_end", "Latest end"]]],
  ["Eligibility and consortium", [["target_groups", "Target groups"], ["eligible_applicants", "Eligible applicants"],
    ["uis_can_apply", "UiS can be project owner"], ["norway_eligible", "Norway eligible"],
    ["international", "International cooperation"], ["consortium_size", "Consortium requirements"],
    ["partner_requirements", "Partner requirements"], ["mandatory_partners", "Mandatory partners"],
    ["industry_public_participation", "Industry or public-sector participation"],
    ["pi_requirements", "Project leader requirements"], ["career_stage", "Career stage"],
    ["nationality_residency", "Nationality or residency"], ["structural_requirements", "Structural requirements"],
    ["trl", "Technology readiness level"]]],
  ["Evaluation and submission", [["evaluation_criteria", "Evaluation criteria"], ["evaluation_weights", "Weighting"],
    ["procedure", "Procedure"], ["required_documents", "Required documents"], ["application_limits", "Application limits"]]],
];
// Requirements an applicant needs; listed as "not found" when the call text has none.
const KEY: [string[], string][] = [
  [["research_scope", "summary", "description"], "Scope"],
  [["expected_impact"], "Expected outcomes and impact"],
  [["deadline", "full_proposal_deadline", "preliminary_deadline", "rolling"], "Deadline"],
  [["total_budget", "max_amount", "min_amount"], "Budget or grant size"],
  [["max_duration_months", "min_duration_months"], "Project duration"],
  [["eligible_applicants", "target_groups"], "Eligible applicants"],
  [["consortium_size", "partner_requirements", "mandatory_partners"], "Consortium or partner requirements"],
  [["evaluation_criteria"], "Evaluation criteria"],
];

function text(f: Field<any> | undefined): string {
  const v = f?.v;
  if (v == null || v === "") return "";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return v.toLocaleString("en-GB");
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join("; ");
  if (typeof v === "object") {
    const { value, fallback } = pick<string | string[]>(v, "en");
    if (value == null) return "";
    const s = Array.isArray(value) ? value.join("; ") : String(value);
    return fallback ? `${s} (Norwegian original)` : s;
  }
  return String(v);
}

const evidenceOf = (f: Field<any>): Evidence =>
  f.s === "not_specified" ? "missing" : f.m === "ai" ? "ai" : f.s === "inferred" ? "inferred" : "explicit";

function promptCall(c: Call): PromptCall {
  const f = c.fields;
  const currency = (f.currency?.v as string) || "";
  const url = (f.url?.v as { en?: string; nb?: string } | null) ?? {};
  const own = url.en || url.nb || "";
  const sections = SECTIONS.map(([title, keys]) => ({
    title,
    fields: keys.map(([k, label]): PromptField => {
      const fld = f[k];
      const money = ["total_budget", "min_amount", "max_amount"].includes(k) && currency;
      const value = fld ? text(fld) + (money && fld.v != null ? ` ${currency}` : "") : "";
      return { label, value, evidence: fld && value ? evidenceOf(fld) : "missing", source: fld?.url ?? undefined };
    }),
  }));
  const p = c.profile;
  if (p) {
    const ai = (label: string, v: string[] | string | undefined): PromptField =>
      ({ label, value: Array.isArray(v) ? v.join("; ") : v ?? "", evidence: "ai" });
    sections.push({ title: "AI reading of the call (generated; not official text)", fields: [
      ai("Objectives", p.objectives), ai("Expected contributions", p.expected_contributions),
      ai("Competencies a team needs", p.competencies.map((x) => x.name)),
      ai("Suitable projects", p.interpretation?.suitable_projects),
      ai("Competitive teams", p.interpretation?.competitive_teams)] });
  }
  const has = (keys: string[]) => keys.some((k) => f[k] && f[k].s !== "not_specified" && f[k].v != null && f[k].v !== "");
  const funder = [pick<string>(f.funder?.v, "en").value, pick<string>(f.programme?.v, "en").value]
    .filter((x, i, a) => x && a.indexOf(x) === i).join(" / ");
  return { id: c.id, title: callTitle(c, "en"), url: own, funder: funder || c.source, collected: (c.fetched ?? "").slice(0, 10),
    sections, missing: KEY.filter(([keys]) => !has(keys)).map(([, label]) => label) };
}

function promptResearcher(atlas: Atlas, r: Researcher, calls: Call[], data: Funding, base: string): PromptResearcher {
  const forCalls = new Map<string, number[]>();
  const matches: { call: number; category: string }[] = [];
  calls.forEach((c, k) => {
    const m = (data.matches[c.id] ?? []).find((x) => x.id === r.scopus_id);
    if (!m) return;
    matches.push({ call: k, category: m.category });
    for (const p of m.papers) forCalls.set(p.eid, [...(forCalls.get(p.eid) ?? []), k]);
  });
  const recentFrom = atlas.meta.period.recent_from;
  const relevant = [...forCalls.keys()].filter((e) => atlas.papers[e]);
  const recent = r.paper_ids.filter((e) => !forCalls.has(e) && Number(atlas.papers[e]?.year) >= recentFrom - 2)
    .slice(0, RECENT_PAPERS);
  const papers = [...relevant, ...recent].map((e) => {
    const p = atlas.papers[e];
    return { title: p.title.replace(/\s+/g, " "), year: p.year, venue: p.venue ?? "", link: paperUrl(p) ?? "",
      forCalls: forCalls.get(e) ?? [] };
  });
  const topics = r.tags.length ? r.tags : (atlas.keywords.get(r.scopus_id) ?? []).slice(0, 10).map(([k]) => k);
  const position = r.position?.en ?? r.position?.nb ?? "";
  const links = [r.links.uis_en ?? r.links.uis, r.links.scopus, r.links.orcid].filter((x): x is string => !!x);
  return { id: r.scopus_id, name: r.name, position, unit: [r.department, r.faculty].filter((x, i, a) => x && a.indexOf(x) === i).join(", "),
    profile: `${base}#/r/${encodeURIComponent(r.scopus_id)}`, links, summary: r.summary ?? "", topics, papers, matches };
}

/** Loads the selected calls' full details, then builds the package. */
export async function preparePrompt(atlas: Atlas, data: Funding, researcherIds: string[], callIds: string[],
  prefs: PromptPrefs, answerLanguage: PromptInput["answerLanguage"]): Promise<PromptPackage> {
  const calls = callIds.map((id) => data.byId.get(id)).filter((c): c is Call => !!c);
  await Promise.all(calls.map((c) => loadDetail(data, c)));
  const people = researcherIds.map((id) => atlas.byId.get(id)).filter((r): r is Researcher => !!r);
  const base = `${location.origin}${location.pathname}`;
  return buildPrompt({
    calls: calls.map(promptCall),
    researchers: people.map((r) => promptResearcher(atlas, r, calls, data, base)),
    prefs, answerLanguage,
    dates: { today: new Date().toISOString().slice(0, 10), atlas: atlas.meta.generated.slice(0, 10),
      funding: data.meta.generated.slice(0, 10) },
    inlineLimit: INLINE_LIMIT, fieldLimit: FIELD_LIMIT,
  });
}

export function download(name: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: `${type};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
