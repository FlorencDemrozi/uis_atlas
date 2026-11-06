// Project builder, project ideas (milestone 3). The selection file the site exports for
// pipeline/project_ideas.py, the ideas file that script writes, and the idea rendered as
// blocks (shown on the page, exported as Markdown or Word). No imports: tested with Node
// in tests/test_ideas.py. Keep the formats in step with pipeline/project_ideas.py.

export const SELECTION_FORMAT = "uis-atlas-selection";
export const IDEAS_FORMAT = "uis-atlas-project-ideas";

export interface Prefs { direction: string; area: string; constraints: string }

export interface Selection {
  format: typeof SELECTION_FORMAT;
  version: 1;
  created: string;
  researchers: string[];
  /** Each call with its key facts at export time (builder-core FACTS), to flag later changes. */
  calls: { id: string; facts: Record<string, string> }[];
  prefs: Prefs;
  answer_language: string;
  data_dates: { atlas: string; funding: string };
}

export function makeSelection(researchers: string[], calls: { id: string; facts: Record<string, string> }[],
  prefs: Prefs, answerLanguage: string, dates: { atlas: string; funding: string }, now: string): Selection {
  return { format: SELECTION_FORMAT, version: 1, created: now, researchers: [...new Set(researchers)],
    calls: calls.filter((c, i) => calls.findIndex((x) => x.id === c.id) === i), prefs, answer_language: answerLanguage,
    data_dates: dates };
}

export interface Checked { text: string; verified: boolean }
export interface Concept {
  title: string;
  acronym: string;
  problem: string;
  approach: string;
  beneficiaries: string;
  call_fit: { element: string; how: string; quote: string; verified: boolean }[];
  objectives: string[];
  innovation: string;
  needs_validation: string[];
  roles: { researcher: string; name: string; role: string; evidence: Checked[] }[];
  work_packages: { name: string; activities: string[]; deliverables: string[]; lead: string }[];
  outcomes: string[];
  impact: string;
  partners: { kind: string; why: string }[];
  feasibility: { consortium: string; duration: string; budget: string; trl: string;
    eligibility: { item: string; status: "stated" | "unverified"; note: string }[] };
  assumptions: string[];
  sources: { label: string; url: string }[];
}

export interface Idea {
  /** Unique: generation time + call id. */
  id: string;
  call: { id: string; title: string; url: string; funder: string; deadline: string; facts: Record<string, string> };
  researchers: { id: string; name: string; unit: string; profile: string }[];
  fit: "good" | "partial" | "poor";
  fit_reason: string;
  missing_expertise: string[];
  concept: Concept | null;
  warnings: string[];
  // Copied from the file, so each saved idea keeps its own record.
  generated: string;
  model: string;
  prefs: Prefs;
  answer_language: string;
  data_dates: { atlas: string; funding: string; calls: string };
}

export interface IdeasFile {
  format: typeof IDEAS_FORMAT;
  version: 1;
  generated: string;
  model: string;
  prefs: Prefs;
  answer_language: string;
  data_dates: { atlas: string; funding: string; calls: string };
  ideas: Omit<Idea, "generated" | "model" | "prefs" | "answer_language" | "data_dates">[];
}

const str = (v: unknown) => (typeof v === "string" ? v : "");
const strs = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const arr = (v: unknown): Record<string, unknown>[] =>
  Array.isArray(v) ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === "object") : [];
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" ? v as Record<string, unknown> : {});
const facts = (v: unknown) => Object.fromEntries(Object.entries(obj(v)).filter(([, x]) => typeof x === "string")) as Record<string, string>;

function concept(v: unknown): Concept | null {
  if (!v || typeof v !== "object") return null;
  const c = obj(v);
  const f = obj(c.feasibility);
  return {
    title: str(c.title), acronym: str(c.acronym), problem: str(c.problem), approach: str(c.approach),
    beneficiaries: str(c.beneficiaries),
    call_fit: arr(c.call_fit).map((x) => ({ element: str(x.element), how: str(x.how), quote: str(x.quote), verified: x.verified === true })),
    objectives: strs(c.objectives), innovation: str(c.innovation), needs_validation: strs(c.needs_validation),
    roles: arr(c.roles).map((x) => ({ researcher: str(x.researcher), name: str(x.name), role: str(x.role),
      evidence: arr(x.evidence).map((e) => ({ text: str(e.text), verified: e.verified === true })) })),
    work_packages: arr(c.work_packages).map((x) => ({ name: str(x.name), activities: strs(x.activities),
      deliverables: strs(x.deliverables), lead: str(x.lead) })),
    outcomes: strs(c.outcomes), impact: str(c.impact),
    partners: arr(c.partners).map((x) => ({ kind: str(x.kind), why: str(x.why) })),
    feasibility: { consortium: str(f.consortium), duration: str(f.duration), budget: str(f.budget), trl: str(f.trl),
      eligibility: arr(f.eligibility).map((x) => ({ item: str(x.item), status: x.status === "stated" ? "stated" : "unverified",
        note: str(x.note) })) },
    assumptions: strs(c.assumptions),
    sources: arr(c.sources).map((x) => ({ label: str(x.label), url: str(x.url) })).filter((x) => /^https?:\/\//.test(x.url) || !x.url),
  };
}

/** The ideas in a file written by project_ideas.py; throws with a short reason when it is not one. */
export function parseIdeasFile(text: string): Idea[] {
  let v: unknown;
  try { v = JSON.parse(text); } catch { throw new Error("not JSON"); }
  const f = obj(v);
  if (f.format !== IDEAS_FORMAT) throw new Error("not a project ideas file");
  if (f.version !== 1) throw new Error(`unsupported version ${String(f.version)}`);
  const d = obj(f.data_dates);
  const p = obj(f.prefs);
  const shared = {
    generated: str(f.generated), model: str(f.model), answer_language: str(f.answer_language),
    prefs: { direction: str(p.direction), area: str(p.area), constraints: str(p.constraints) },
    data_dates: { atlas: str(d.atlas), funding: str(d.funding), calls: str(d.calls) },
  };
  const ideas = arr(f.ideas).map((x): Idea | null => {
    const call = obj(x.call);
    if (!str(x.id) || !str(call.id)) return null;
    const fit = x.fit === "good" || x.fit === "partial" ? x.fit : "poor";
    return {
      id: str(x.id),
      call: { id: str(call.id), title: str(call.title) || str(call.id), url: /^https?:\/\//.test(str(call.url)) ? str(call.url) : "",
        funder: str(call.funder), deadline: str(call.deadline), facts: facts(call.facts) },
      researchers: arr(x.researchers).map((r) => ({ id: str(r.id), name: str(r.name), unit: str(r.unit), profile: str(r.profile) })),
      fit, fit_reason: str(x.fit_reason), missing_expertise: strs(x.missing_expertise),
      concept: concept(x.concept), warnings: strs(x.warnings), ...shared,
    };
  }).filter((x): x is Idea => x !== null);
  if (!ideas.length) throw new Error("no ideas in the file");
  return ideas;
}

/** Saved ideas: the new ones replace saved ones with the same id; order: newest first. */
export function mergeIdeas(saved: Idea[], added: Idea[]): Idea[] {
  const ids = new Set(added.map((i) => i.id));
  return [...added, ...saved.filter((i) => !ids.has(i.id))];
}

// ------------------------------------------------------------------ rendering
export type Block =
  | { kind: "title" | "h1" | "h2" | "p" | "note"; text: string }
  | { kind: "bullets"; items: string[] };

/** Headings and fixed phrases, in the language of the page (passed in by the caller). */
export type Labels = Record<
  "draft" | "call" | "deadline" | "researchers" | "generated" | "dataDates" | "fit" | "fitGood" | "fitPartial" | "fitPoor" |
  "mismatch" | "missingExpertise" | "summary" | "problem" | "approach" | "beneficiaries" | "callFit" | "quote" |
  "unverified" | "objectives" | "innovation" | "needsValidation" | "roles" | "evidence" | "workPackages" |
  "activities" | "deliverables" | "lead" | "outcomes" | "impact" | "partners" | "feasibility" | "consortium" |
  "duration" | "budget" | "trl" | "eligibility" | "stated" | "assumptions" | "sources" | "warnings" | "preferences" |
  "notChecked", string>;

const nonEmpty = (xs: string[]) => xs.filter((x) => x.trim());

export function ideaBlocks(idea: Idea, L: Labels): Block[] {
  const c = idea.concept;
  const fitLabel = { good: L.fitGood, partial: L.fitPartial, poor: L.fitPoor }[idea.fit];
  const b: Block[] = [
    { kind: "title", text: c ? `${c.acronym ? `${c.acronym}: ` : ""}${c.title}` : idea.call.title },
    { kind: "note", text: L.draft },
    { kind: "bullets", items: nonEmpty([
      `${L.call}: ${idea.call.title}${idea.call.funder ? ` (${idea.call.funder})` : ""}${idea.call.url ? ` – ${idea.call.url}` : ""}`,
      idea.call.deadline ? `${L.deadline}: ${idea.call.deadline}` : "",
      `${L.researchers}: ${idea.researchers.map((r) => r.unit ? `${r.name} (${r.unit})` : r.name).join("; ")}`,
      `${L.generated}: ${idea.generated.slice(0, 16).replace("T", " ")}${idea.model ? ` (${idea.model})` : ""}`,
      `${L.dataDates}: ${[idea.data_dates.atlas, idea.data_dates.funding].filter(Boolean).join(" / ")}`,
      [idea.prefs.direction, idea.prefs.area, idea.prefs.constraints].some((x) => x.trim())
        ? `${L.preferences}: ${nonEmpty([idea.prefs.direction, idea.prefs.area, idea.prefs.constraints]).join(" · ")}` : "",
    ]) },
    { kind: "h1", text: `${L.fit}: ${fitLabel}` },
    { kind: "p", text: idea.fit_reason },
  ];
  if (idea.missing_expertise.length) b.push({ kind: "h2", text: L.missingExpertise }, { kind: "bullets", items: idea.missing_expertise });
  if (!c) {
    b.push({ kind: "note", text: L.mismatch });
  } else {
    b.push({ kind: "h1", text: L.summary },
      { kind: "p", text: `${L.problem}: ${c.problem}` }, { kind: "p", text: `${L.approach}: ${c.approach}` },
      { kind: "p", text: `${L.beneficiaries}: ${c.beneficiaries}` });
    if (c.call_fit.length) {
      b.push({ kind: "h1", text: L.callFit }, { kind: "bullets", items: c.call_fit.map((x) =>
        `${x.element}: ${x.how}${x.quote ? ` – ${L.quote}: “${x.quote}”${x.verified ? "" : ` (${L.unverified})`}` : ""}`) });
    }
    b.push({ kind: "h1", text: L.objectives }, { kind: "bullets", items: c.objectives },
      { kind: "h2", text: L.innovation }, { kind: "p", text: c.innovation });
    if (c.needs_validation.length) b.push({ kind: "h2", text: L.needsValidation }, { kind: "bullets", items: c.needs_validation });
    b.push({ kind: "h1", text: L.roles });
    for (const r of c.roles) {
      b.push({ kind: "h2", text: `${r.name}: ${r.role}` });
      if (r.evidence.length) b.push({ kind: "bullets", items: r.evidence.map((e) => `${L.evidence}: ${e.text}${e.verified ? "" : ` (${L.unverified})`}`) });
    }
    b.push({ kind: "h1", text: L.workPackages });
    c.work_packages.forEach((w, i) => {
      b.push({ kind: "h2", text: `WP${i + 1}: ${w.name}${w.lead ? ` – ${L.lead}: ${w.lead}` : ""}` });
      if (w.activities.length) b.push({ kind: "p", text: `${L.activities}:` }, { kind: "bullets", items: w.activities });
      if (w.deliverables.length) b.push({ kind: "p", text: `${L.deliverables}:` }, { kind: "bullets", items: w.deliverables });
    });
    b.push({ kind: "h1", text: L.outcomes }, { kind: "bullets", items: c.outcomes }, { kind: "h2", text: L.impact },
      { kind: "p", text: c.impact });
    if (c.partners.length) b.push({ kind: "h1", text: L.partners }, { kind: "bullets", items: c.partners.map((p) => `${p.kind}: ${p.why}`) });
    const f = c.feasibility;
    b.push({ kind: "h1", text: L.feasibility }, { kind: "bullets", items: nonEmpty([
      f.consortium && `${L.consortium}: ${f.consortium}`, f.duration && `${L.duration}: ${f.duration}`,
      f.budget && `${L.budget}: ${f.budget}`, f.trl && `${L.trl}: ${f.trl}`]) });
    if (f.eligibility.length) {
      b.push({ kind: "h2", text: L.eligibility }, { kind: "bullets", items: f.eligibility.map((e) =>
        `${e.item}: ${e.status === "stated" ? L.stated : L.unverified}${e.note ? ` – ${e.note}` : ""}`) });
    }
    if (c.assumptions.length) b.push({ kind: "h1", text: L.assumptions }, { kind: "bullets", items: c.assumptions });
    if (c.sources.length) b.push({ kind: "h1", text: L.sources }, { kind: "bullets", items: c.sources.map((s) => s.url ? `${s.label} – ${s.url}` : s.label) });
  }
  if (idea.warnings.length) b.push({ kind: "h1", text: L.warnings }, { kind: "bullets", items: idea.warnings });
  return b.filter((x) => (x.kind === "bullets" ? x.items.length > 0 : x.text.trim().length > 0));
}

export function blocksToMarkdown(blocks: Block[]): string {
  return blocks.map((b) => {
    switch (b.kind) {
      case "title": return `# ${b.text}`;
      case "h1": return `## ${b.text}`;
      case "h2": return `### ${b.text}`;
      case "note": return `> ${b.text}`;
      case "bullets": return b.items.map((x) => `- ${x}`).join("\n");
      default: return b.text;
    }
  }).join("\n\n") + "\n";
}
