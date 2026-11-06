// Project builder, "Prepare AI prompt": assembles a prompt package for an external LLM
// (ChatGPT, Claude, …) from the selected funding calls and researchers. Pure functions
// on plain data (prompt.ts gathers it), no imports: tests/test_prompt.py runs this file
// with Node. The prompt is always in English; the answer language is a setting.

export type Evidence = "explicit" | "inferred" | "ai" | "missing";

export interface PromptField { label: string; value: string; evidence: Evidence; source?: string }
export interface PromptSection { title: string; fields: PromptField[] }

export interface PromptCall {
  id: string;
  title: string;
  url: string;
  funder: string;
  collected: string;            // when the call page was read (ISO date)
  sections: PromptSection[];
  /** Key requirements not found in the collected text (labels). */
  missing: string[];
}

export interface PromptPaper { title: string; year: string; venue: string; link: string; forCalls: number[] }

export interface PromptResearcher {
  id: string;
  name: string;
  position: string;
  unit: string;                 // department, faculty
  profile: string;              // atlas profile URL
  links: string[];              // Scopus, ORCID, UiS
  summary: string;              // AI-written, labelled as such
  topics: string[];
  papers: PromptPaper[];        // relevant first, then recent
  /** Per call (index into calls): how the atlas matching rated this person, if at all. */
  matches: { call: number; category: string }[];
}

export interface PromptPrefs { direction: string; area: string; constraints: string }

export interface PromptInput {
  calls: PromptCall[];
  researchers: PromptResearcher[];
  prefs: PromptPrefs;
  answerLanguage: "English" | "Norwegian (bokmål)";
  dates: { today: string; atlas: string; funding: string };
  /** Above this many characters the package is split into prompt + supporting file. */
  inlineLimit: number;
  /** Longest text kept per field (in the full information); longer text is shortened and noted. */
  fieldLimit: number;
}

export interface PromptPackage { prompt: string; support: string | null; omitted: string[] }

const EVIDENCE_NOTE: Record<Evidence, string> = {
  explicit: "", inferred: " (inferred from the call text)", ai: " (AI reading of the call, not official text)",
  missing: "",
};

function cut(text: string, limit: number, what: string, url: string, omitted: string[]): string {
  const t = text.trim();
  if (t.length <= limit) return t;
  omitted.push(`${what}: shortened from ${t.length} to ${limit} characters`);
  return `${t.slice(0, limit).trimEnd()} […shortened; full text: ${url || "see the call page"}]`;
}

const indent = (text: string) => text.split("\n").map((l) => (l ? `  ${l}` : l)).join("\n");

function callBlock(c: PromptCall, k: number, limit: number, omitted: string[], compact: boolean): string {
  const out = [`## Call ${k + 1}: ${c.title}`, "",
    `- Identifier: ${c.id}`, `- Funder / programme: ${c.funder}`, `- Official page: ${c.url || "not available"}`,
    `- Information collected: ${c.collected || "date unknown"}`];
  for (const s of c.sections) {
    const fields = s.fields.filter((f) => f.evidence !== "missing" && f.value.trim());
    if (!fields.length) continue;
    out.push("", `### ${s.title}`);
    for (const f of fields) {
      const value = cut(f.value, compact ? Math.min(limit, 1200) : limit, `Call ${k + 1}, ${f.label}`, c.url, omitted);
      const src = f.source && f.source !== c.url ? ` [source: ${f.source}]` : "";
      out.push(value.includes("\n") || value.length > 160
        ? `- **${f.label}**${EVIDENCE_NOTE[f.evidence]}${src}:\n${indent(value)}`
        : `- **${f.label}**${EVIDENCE_NOTE[f.evidence]}${src}: ${value}`);
    }
  }
  out.push("", `### Not found in the collected call text`,
    c.missing.length ? c.missing.map((m) => `- ${m}`).join("\n") + "\n- Check these on the official page before relying on them."
      : "- (all key requirements were found)");
  return out.join("\n");
}

function researcherBlock(r: PromptResearcher, k: number, calls: PromptCall[], compact: boolean): string {
  const papers = compact ? r.papers.slice(0, 6) : r.papers;
  const out = [`## R${k + 1}: ${r.name}`, "",
    `- Position and unit: ${[r.position, r.unit].filter(Boolean).join(", ") || "not stated"}`,
    `- Atlas profile: ${r.profile}`];
  if (r.links.length) out.push(`- Other profiles: ${r.links.join(" · ")}`);
  if (r.summary) out.push(`- Research summary (AI-written from their publications; an indication, not a fact): ${r.summary}`);
  if (r.topics.length) out.push(`- Research themes (from publication keywords and the summary): ${r.topics.join("; ")}`);
  const m = r.matches.filter((x) => x.call < calls.length);
  out.push(`- Atlas matching against the selected calls: ${m.length
    ? m.map((x) => `Call ${x.call + 1}: ${x.category}`).join("; ")
    : "not matched to any of them (this does not rule out a fit)"}`);
  out.push("", papers.length ? "Publications (relevant to a selected call first, then most recent):" : "No recent publications in the atlas.");
  papers.forEach((p, i) => {
    const rel = p.forCalls.length ? ` — relevant to ${p.forCalls.map((c) => `Call ${c + 1}`).join(", ")}` : "";
    out.push(`${i + 1}. ${p.title} (${p.year}${p.venue ? `, ${p.venue}` : ""})${p.link ? ` ${p.link}` : ""}${rel}`);
  });
  if (compact && r.papers.length > papers.length) out.push(`(${r.papers.length - papers.length} more in the supporting information)`);
  return out.join("\n");
}

function task(input: PromptInput, split: boolean): string {
  const n = input.calls.length;
  return [
    "# Task: project concepts for selected funding calls",
    "",
    `You are assisting researchers at the University of Stavanger (UiS), Norway, in developing proposal concepts. ` +
    `Below are the user's preferences, ${n} funding call${n > 1 ? "s" : ""} and ${input.researchers.length} UiS ` +
    `researcher${input.researchers.length > 1 ? "s" : ""}, each with sources.` +
    (split ? " The attached file \"supporting information\" holds the full call texts and publication lists: read it before answering." : ""),
    "",
    `For EACH call separately (${n > 1 ? "one section per call" : "one section"}):`,
    "",
    "1. **Assess the match.** Do these researchers, on their documented work, cover what the call asks for? " +
    "Judge the substance (problems, methods, application domain), not shared keywords. If they do not adequately " +
    "cover the call, say so plainly, explain the mismatch, name the expertise that is missing, and do not force a " +
    "project concept.",
    "2. **If there is a reasonable match, propose one project concept** with these headings:",
    "   - Project title and acronym",
    "   - Concept summary: the problem, the proposed approach and the intended beneficiaries",
    "   - Fit with the call: map the idea to the call's scope, objectives, expected outcomes and relevant requirements, quoting the call",
    "   - Research objectives and innovation: the contribution, and what still needs validation",
    "   - Team roles: each researcher's role, with the evidence (cite R-number and publication number or profile item)",
    "   - Indicative work packages: activities, deliverables and a suitable lead",
    "   - Expected outcomes and impact",
    "   - Missing expertise or partners (clinical, industrial, municipal or other partners where relevant)",
    "   - Feasibility and eligibility: consortium requirements, duration, budget and technology readiness, as far as the information allows",
    "   - Sources and assumptions",
    "",
    "## Rules",
    "",
    "- Use only the information given here (and the linked official pages, if you can open them). Never invent " +
    "researcher capabilities, publications, partnerships, budgets or funding conditions.",
    "- Distinguish documented facts from assumptions. Cite facts as [Call 1: <section>] or [R2: publication 3]; " +
    "mark everything else as [Assumption].",
    "- Treat eligibility as **unverified** unless the call text states the rule; requirements listed under " +
    "\"Not found in the collected call text\" are unknown, not absent.",
    "- Research summaries and \"AI reading\" entries were generated automatically: indications, not facts.",
    "- The atlas matching is a text-similarity score; use it as a hint only.",
    "- Do not say that anyone has agreed to take part. The output is a draft for the researchers to review.",
    `- Write the answer in ${input.answerLanguage}.`,
  ].join("\n");
}

function prefsBlock(p: PromptPrefs): string {
  const line = (label: string, v: string) => `- ${label}: ${v.trim() || "none given"}`;
  return ["# The user's preferences", "", line("Intended research direction", p.direction),
    line("Application area", p.area), line("Ambition, constraints and other wishes", p.constraints)].join("\n");
}

function sourcesBlock(input: PromptInput): string {
  const d = input.dates;
  return ["# Sources and dates", "",
    `- Prepared: ${d.today}, from the UiS Researcher Atlas.`,
    `- Researcher data (publications from Scopus and NVA, UiS employee directory) updated: ${d.atlas || "unknown"}.`,
    `- Funding call data updated: ${d.funding || "unknown"}; each call shows when its page was read.`,
    "- Call texts are as published by the funder at that time; check the official page before submitting."].join("\n");
}

/** The prompt package: one file when it fits in inlineLimit characters, else a compact
 *  prompt plus a supporting-information file with everything in full. */
export function buildPrompt(input: PromptInput): PromptPackage {
  const omittedFull: string[] = [];
  const full = (compact: boolean, omitted: string[]) => [
    "# Funding calls", "",
    input.calls.map((c, k) => callBlock(c, k, input.fieldLimit, omitted, compact)).join("\n\n"),
    "", "# Researchers", "",
    input.researchers.map((r, k) => researcherBlock(r, k, input.calls, compact)).join("\n\n"),
  ].join("\n");
  const info = full(false, omittedFull);
  const single = [task(input, false), prefsBlock(input.prefs), info, sourcesBlock(input)].join("\n\n") + "\n";
  if (single.length <= input.inlineLimit) return { prompt: single, support: null, omitted: omittedFull };
  const omittedCompact: string[] = [];
  const compactInfo = full(true, omittedCompact);
  const prompt = [task(input, true), prefsBlock(input.prefs),
    "# Summary of the calls and researchers (full details in the supporting information)", "",
    compactInfo.replace(/^# /gm, "## ").replace(/^## (Call|R)/gm, "### $1"), sourcesBlock(input)].join("\n\n") + "\n";
  const support = ["# Supporting information", "",
    "Full call texts and publication lists for the prompt prepared from the UiS Researcher Atlas.", "",
    info, "", sourcesBlock(input)].join("\n") + "\n";
  return { prompt, support, omitted: omittedFull };
}

/** Markdown to plain text for the .txt download: headings and emphasis without symbols. */
export function toPlainText(md: string): string {
  return md.replace(/^#{1,6} +(.*)$/gm, (_, h: string) => h.toUpperCase()).replace(/\*\*(.+?)\*\*/g, "$1");
}
