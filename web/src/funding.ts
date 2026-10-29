// Funding Intelligence data: loaded from public/data/funding.enc.json and decrypted
// in the browser once the user types the password (pipeline/export_funding.py).
// That index holds every call and match; a call's full details (official text,
// AI profile, history) come from its detail shard when its page opens (loadDetail).
// The password never appears in the code; only a key derived from it is kept for
// the browser session (sessionStorage), so the pages stay open while navigating.
import { createContext } from "preact";
import { useCallback, useContext, useEffect, useMemo, useState } from "preact/hooks";

export type FieldStatus = "explicit" | "inferred" | "not_specified";
export type Method = "metadata" | "section" | "rule" | "manual" | "ai" | null;
export type L<T = string> = { nb?: T | null; en?: T | null };

export interface Field<T = unknown> {
  v: T;
  s: FieldStatus;
  src: string | null;     // where on the call page (label or section heading)
  url: string | null;     // source page
  ev: string | null;      // supporting text as published
  c: "high" | "medium" | "low" | null;
  m: Method;
  ai?: { v: string; s: FieldStatus; ev: string | null };
}

export interface DocLink { text: string; url: string; kind: string; src: string }
export interface Change { date: string; field: string; old: unknown; new: unknown }
export interface Aspect { label: string; kind: string; source: "ai" | "call_text"; evidence: string }

export interface CallProfile {
  disciplines: { path: string[]; level: "primary" | "secondary" }[];
  topics: { path: string[]; basis: "explicit" | "interpretation"; evidence: string }[];
  objectives: string[]; challenges: string[]; methods: string[]; technologies: string[];
  application_domains: string[]; expected_contributions: string[]; interdisciplinary: string[];
  contributing_expertise?: string[];
  competencies: { name: string; kind: string; rationale: string; evidence: string; verified?: boolean }[];
  interpretation: { problems: string; suitable_projects: string; competitive_teams: string;
    explicit_directions: string[]; plausible_directions: string[] };
  generated: string; model: string;
}

/** Funding source and programme family, for filters and badges (pipeline/eu.py FAMILIES). */
export const FAMILIES = ["nfr", "horizon", "erc", "msca", "eic", "missions", "partnerships", "other_eu"] as const;
export type Family = typeof FAMILIES[number];

export interface Call {
  id: string;
  source: "rcn" | "eu";
  family: Family;
  listing_group: string;
  tags: string[];
  fetched: string;
  fields: Record<string, Field<any>>;
  review: string[];
  listed: boolean;
  history?: Change[];  // from the detail shard
  profile?: CallProfile;
  aspects?: Aspect[];
  aspect_basis?: "ai_profile" | "call_text" | "open_field" | "institution_level";
  title_terms?: string[];
  /** Open-field calls: researchers with a restriction ([status, reason]); everyone else "no_restriction_found". */
  open_eligibility?: Record<string, [Eligibility["status"], string]>;
  eligibility_evidence?: Record<string, string | null>;
  /** ERC / MSCA: the role a UiS researcher takes (e.g. "supervisor" for MSCA fellowships). */
  open_role?: string;
  /** Detail shard holding the call's other fields, profile and history. */
  d?: number;
  /** Listed as open or planned, but every deadline has passed (set in the browser, see closeByDate). */
  closed_by_date?: boolean;
}

export interface Eligibility {
  status: "no_restriction_found" | "check" | "likely_ineligible" | "partner_only";
  reason: string;
  evidence: string | null;
}

export interface Match {
  id: string;
  score: number;
  category: "high" | "medium" | "low";
  components: { scope: number; coverage: number; evidence: number };
  papers: { eid: string; rel: number; terms: string[] }[];
  matched: { aspect: number; paper: string; rel: number }[];
  missing: number[];
  eligibility: Eligibility;
  role: string;
  specialist_for?: number[];   // aspects this researcher covers among the best at UiS
  collaborators: { id: string; fills: number[]; joint_papers: number; other_department: boolean }[];
}

export interface SourceSync {
  id: "rcn" | "eu"; name: string; url: string;
  last_attempt: string | null; last_success: string | null; errors: { url: string; error: string }[] | null;
}

export interface FundingMeta {
  generated: string;
  sources: SourceSync[];
  calls_extracted: string;
  profiles_generated: string | null;
  matches_generated: string;
  researchers_updated: string | null;
  papers_from_year: number;
  algorithm: string;
  weights: Record<string, number>;
  categories: Record<string, number>;
  has_ai_profiles: boolean;
  detail_shards?: number;
}

export interface Funding {
  meta: FundingMeta;
  calls: Call[];
  byId: Map<string, Call>;
  matches: Record<string, Match[]>;
  /** Researcher id -> their call matches, best first. */
  byResearcher: Map<string, { call: Call; match: Match }[]>;
  /** Key and salt of this export, to open the detail shards. */
  key: Uint8Array<ArrayBuffer>;
  salt: string;
}

interface EncryptedFile {
  format: string;
  kdf: { name: "PBKDF2"; hash: "SHA-256"; iterations: number; salt: string };
  cipher: { name: "AES-GCM"; iv: string };
  compression: "gzip";
  data: string;
}

const KEY_STORE = "atlas-funding-key";
const b64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const toB64 = (b: Uint8Array) => btoa(String.fromCharCode(...b));

async function deriveKey(password: string, file: EncryptedFile): Promise<Uint8Array<ArrayBuffer>> {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: b64(file.kdf.salt), iterations: file.kdf.iterations }, base, 256);
  return new Uint8Array(bits);
}

async function openFile<T>(file: EncryptedFile, raw: Uint8Array<ArrayBuffer>): Promise<T> {
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(file.cipher.iv) }, key, b64(file.data));
  const stream = new Blob([plain]).stream().pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(stream).text()) as T;
}

// Fields as exported (before restoreFields), so detail fields can be merged in later.
const rawFields = new WeakMap<Call, Record<string, Partial<Field<any>>>>();

async function decrypt(file: EncryptedFile, raw: Uint8Array<ArrayBuffer>): Promise<Funding> {
  const data = await openFile<Omit<Funding, "byId" | "byResearcher" | "key" | "salt">>(file, raw);
  const today = new Date().toISOString().slice(0, 10);
  for (const c of data.calls) {
    rawFields.set(c, c.fields as Record<string, Partial<Field<any>>>);
    c.fields = restoreFields(c.fields);
    closeByDate(c, today);
  }
  const byId = new Map(data.calls.map((c) => [c.id, c]));
  const byResearcher = new Map<string, { call: Call; match: Match }[]>();
  for (const [cid, list] of Object.entries(data.matches)) {
    const call = byId.get(cid);
    if (!call || call.closed_by_date) continue;  // matches are only for open and planned calls
    for (const match of list) {
      const arr = byResearcher.get(match.id) ?? [];
      arr.push({ call, match });
      byResearcher.set(match.id, arr);
    }
  }
  for (const arr of byResearcher.values()) arr.sort((a, b) => b.match.score - a.match.score);
  return { ...data, byId, byResearcher, key: raw, salt: file.kdf.salt };
}

/** The weekly pipeline sets the status; a call whose deadlines have all passed since
 * then is shown as closed straight away. Rolling calls, calls without a deadline and
 * calls with cut-offs still ahead stay as they are. */
export function closeByDate(c: Call, today: string): void {
  const f = c.fields;
  if (f.status.v === "closed" || f.rolling.v) return;
  const dates = [f.preliminary_deadline.v, f.deadline.v, f.full_proposal_deadline.v, ...(f.cutoff_dates.v ?? [])]
    .filter((d): d is string => !!d).map((d) => d.slice(0, 10));
  if (!dates.length || dates.some((d) => d >= today)) return;
  c.fields.status = { ...f.status, v: "closed" };
  c.closed_by_date = true;
}

// ------------------------------------------------------------ call details
interface CallDetail { fields: Record<string, Partial<Field<any>>>; profile?: CallProfile; history?: Change[] }
const shardFiles = new Map<string, Promise<Record<string, CallDetail>>>();

/** Loads the call's detail shard (once per shard) and merges it into every call of that shard. */
export async function loadDetail(data: Funding, call: Call): Promise<void> {
  if (call.d == null || !rawFields.has(call)) return;
  const name = "./data/funding.detail-" + String(call.d).padStart(2, "0") + ".enc.json";
  if (!shardFiles.has(name)) {
    shardFiles.set(name, fetch(name).then(async (res) => {
      if (!res.ok) throw new Error(String(res.status));
      const file = (await res.json()) as EncryptedFile;
      if (file.kdf.salt !== data.salt) throw new Error("outdated");  // a newer export: reload the page
      return openFile<Record<string, CallDetail>>(file, data.key);
    }));
  }
  let shard: Record<string, CallDetail>;
  try {
    shard = await shardFiles.get(name)!;
  } catch (e) {
    shardFiles.delete(name);  // try again next time
    throw e;
  }
  const today = new Date().toISOString().slice(0, 10);
  for (const [id, detail] of Object.entries(shard)) {
    const c = data.byId.get(id);
    const own = c && rawFields.get(c);
    if (!c || !own) continue;
    rawFields.delete(c);  // merged once
    c.fields = restoreFields({ ...own, ...detail.fields });
    closeByDate(c, today);
    if (detail.profile) c.profile = detail.profile;
    c.history = detail.history ?? [];
  }
}

/** "ready" once the call's details are merged (at once for older single-file exports). */
export function useCallDetail(data: Funding, call: Call | undefined): "loading" | "ready" | "error" {
  const pending = !!call && call.d != null && rawFields.has(call);
  const [state, setState] = useState<"loading" | "ready" | "error">(pending ? "loading" : "ready");
  useEffect(() => {
    if (!call || !pending) { setState("ready"); return; }
    let live = true;
    setState("loading");
    loadDetail(data, call).then(() => { if (live) setState("ready"); }, () => { if (live) setState("error"); });
    return () => { live = false; };
  }, [data, call?.id]);
  return state;
}

const NOT_SPECIFIED: Field<null> = { v: null, s: "not_specified", src: null, url: null, ev: null, c: null, m: null };

/** The export leaves out empty keys, a source URL equal to the call's own page and,
 * for closed EU topics, most fields (pipeline/export_funding.py slim()). Put them
 * back, and answer "not specified" for any field that is absent. */
function restoreFields(fields: Record<string, Partial<Field<any>>>): Record<string, Field<any>> {
  const page = fields.url?.v ? (fields.url.v.en ?? fields.url.v.nb ?? null) : null;
  const out: Record<string, Field<any>> = {};
  for (const [k, f] of Object.entries(fields)) {
    out[k] = { ...NOT_SPECIFIED, v: null, url: page, ...f } as Field<any>;
  }
  return new Proxy(out, { get: (t, k: string) => t[k] ?? NOT_SPECIFIED });
}

export type FundingState =
  | { status: "idle" | "loading" | "locked" | "missing" | "unsupported" }
  | { status: "error"; error: string }
  | { status: "ready"; data: Funding };

export interface FundingValue {
  state: FundingState;
  /** Fetches the file and opens it with a key saved in this session, if any. */
  load: () => void;
  /** Returns false if the password is wrong. */
  unlock: (password: string) => Promise<boolean>;
  lock: () => void;
}

export const FundingContext = createContext<FundingValue>(null as unknown as FundingValue);
export const useFunding = () => useContext(FundingContext);

export function useFundingState(): FundingValue {
  const [state, setState] = useState<FundingState>({ status: "idle" });
  const [file, setFile] = useState<EncryptedFile | null>(null);

  const load = useCallback(() => {
    if (state.status !== "idle") return;
    if (!globalThis.crypto?.subtle || typeof DecompressionStream === "undefined") {
      setState({ status: "unsupported" });
      return;
    }
    setState({ status: "loading" });
    fetch("./data/funding.enc.json")
      .then(async (res) => {
        if (res.status === 404) return setState({ status: "missing" });
        if (!res.ok) throw new Error(String(res.status));
        const f = (await res.json()) as EncryptedFile;
        setFile(f);
        let saved: string | null = null;
        try { saved = sessionStorage.getItem(KEY_STORE); } catch { /* storage unavailable */ }
        const [salt, key] = saved?.split(":") ?? [];
        if (salt === f.kdf.salt && key) {
          try { return setState({ status: "ready", data: await decrypt(f, b64(key)) }); } catch { /* key outdated */ }
        }
        setState({ status: "locked" });
      })
      .catch((e) => setState({ status: "error", error: String(e) }));
  }, [state.status]);

  const unlock = useCallback(async (password: string) => {
    if (!file) return false;
    const raw = await deriveKey(password, file);
    try {
      const data = await decrypt(file, raw);
      try { sessionStorage.setItem(KEY_STORE, `${file.kdf.salt}:${toB64(raw)}`); } catch { /* ignore */ }
      setState({ status: "ready", data });
      return true;
    } catch {
      return false;
    }
  }, [file]);

  const lock = useCallback(() => {
    try { sessionStorage.removeItem(KEY_STORE); } catch { /* ignore */ }
    setState(file ? { status: "locked" } : { status: "idle" });
  }, [file]);

  return useMemo(() => ({ state, load, unlock, lock }), [state, load, unlock, lock]);
}

// ------------------------------------------------------------------ helpers
export type Lang = "nb" | "en";

/** Text in the current language, else the other one (flagged by `fallback`). */
export function pick<T>(v: L<T> | null | undefined, lang: Lang): { value: T | null; fallback: boolean } {
  if (!v) return { value: null, fallback: false };
  const own = v[lang];
  if (own != null && (!Array.isArray(own) || own.length)) return { value: own, fallback: false };
  const other = v[lang === "nb" ? "en" : "nb"];
  return { value: other ?? null, fallback: other != null };
}

export function callTitle(c: Call, lang: Lang): string {
  return pick<string>(c.fields.title.v, lang).value ?? c.id;
}

export function deadlineOf(c: Call): string | null {
  const f = c.fields;
  return f.deadline?.v ?? f.full_proposal_deadline?.v ?? f.preliminary_deadline?.v ?? null;
}

/** The next deadline still ahead (preliminary or main), for sorting and display. */
export function nextDeadline(c: Call, today = new Date().toISOString().slice(0, 10)): string | null {
  const f = c.fields;
  const all = [f.preliminary_deadline?.v, f.deadline?.v, f.full_proposal_deadline?.v].filter((d): d is string => !!d);
  return all.filter((d) => d.slice(0, 10) >= today).sort()[0] ?? null;
}

/** A call open to all research fields (offered to everyone, not topic-matched). */
export function isOpenField(c: Call): boolean {
  return !isInstitutionLevel(c) && (c.aspect_basis === "open_field" || !!c.fields.open_field?.v);
}

/** A call the institution applies for as a whole (MSCA COFUND, Researchers' Night): not offered to researchers. */
export function isInstitutionLevel(c: Call): boolean {
  return c.aspect_basis === "institution_level" || !!c.fields.institution_level?.v;
}

const ELIG_ORDER ={ no_restriction_found: 0, check: 1, partner_only: 2, likely_ineligible: 3 };

/** Open (or planned) calls that accept every research field, with this researcher's
 * eligibility, most likely eligible first. Closed calls are left out. */
export function openFieldCallsFor(data: Funding, id: string): { call: Call; eligibility: Eligibility }[] {
  return data.calls
    .filter((c) => isOpenField(c) && c.fields.status.v !== "closed")
    .map((call) => {
      const [status, reason] = call.open_eligibility?.[id] ?? ["no_restriction_found", "none_found"];
      return { call, eligibility: { status, reason, evidence: call.eligibility_evidence?.[reason] ?? null } };
    })
    .sort((a, b) => ELIG_ORDER[a.eligibility.status] - ELIG_ORDER[b.eligibility.status]);
}

/** Programme family of a call (older exports have none). */
export function familyOf(c: Call): Family {
  return c.family ?? (c.source === "rcn" ? "nfr" : "other_eu");
}

/** Indicative rate used only to compare EUR and NOK amounts in the amount filter. */
export const EUR_NOK = 11.5;
export function amountNok(n: number | null | undefined, currency: string | null | undefined): number | null {
  if (n == null) return null;
  return currency === "EUR" ? n * EUR_NOK : n;
}

export function isStale(iso: string | null | undefined, days = 8): boolean {
  if (!iso) return true;
  return Date.now() - new Date(iso).getTime() > days * 864e5;
}
