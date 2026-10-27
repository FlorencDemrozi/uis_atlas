// Funding Intelligence data: loaded from public/data/funding.enc.json and decrypted
// in the browser once the user types the password (pipeline/export_funding.py).
// The password never appears in the code; only a key derived from it is kept for
// the browser session (sessionStorage), so the pages stay open while navigating.
import { createContext } from "preact";
import { useCallback, useContext, useMemo, useState } from "preact/hooks";

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
  competencies: { name: string; kind: string; rationale: string; evidence: string; verified?: boolean }[];
  interpretation: { problems: string; suitable_projects: string; competitive_teams: string;
    explicit_directions: string[]; plausible_directions: string[] };
  generated: string; model: string;
}

export interface Call {
  id: string;
  source: string;
  listing_group: string;
  tags: string[];
  fetched: string;
  fields: Record<string, Field<any>>;
  review: string[];
  listed: boolean;
  history: Change[];
  profile?: CallProfile;
  aspects?: Aspect[];
  aspect_basis?: "ai_profile" | "call_text" | "open_field";
  title_terms?: string[];
  /** Open-field calls: researchers with a restriction ([status, reason]); everyone else "no_restriction_found". */
  open_eligibility?: Record<string, [Eligibility["status"], string]>;
  eligibility_evidence?: Record<string, string | null>;
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
  collaborators: { id: string; fills: number[]; joint_papers: number; other_department: boolean }[];
}

export interface FundingMeta {
  generated: string;
  sources: { name: string; url: string }[];
  sync: { last_attempt: string | null; last_success: string | null; errors: { url: string; error: string }[] } | null;
  calls_extracted: string;
  profiles_generated: string | null;
  matches_generated: string;
  researchers_updated: string | null;
  papers_from_year: number;
  algorithm: string;
  weights: Record<string, number>;
  categories: Record<string, number>;
  has_ai_profiles: boolean;
}

export interface Funding {
  meta: FundingMeta;
  calls: Call[];
  byId: Map<string, Call>;
  matches: Record<string, Match[]>;
  /** Researcher id -> their call matches, best first. */
  byResearcher: Map<string, { call: Call; match: Match }[]>;
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

async function decrypt(file: EncryptedFile, raw: Uint8Array<ArrayBuffer>): Promise<Funding> {
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(file.cipher.iv) }, key, b64(file.data));
  const stream = new Blob([plain]).stream().pipeThrough(new DecompressionStream("gzip"));
  const data = JSON.parse(await new Response(stream).text()) as Omit<Funding, "byId" | "byResearcher">;
  const byId = new Map(data.calls.map((c) => [c.id, c]));
  const byResearcher = new Map<string, { call: Call; match: Match }[]>();
  for (const [cid, list] of Object.entries(data.matches)) {
    const call = byId.get(cid);
    if (!call) continue;
    for (const match of list) {
      const arr = byResearcher.get(match.id) ?? [];
      arr.push({ call, match });
      byResearcher.set(match.id, arr);
    }
  }
  for (const arr of byResearcher.values()) arr.sort((a, b) => b.match.score - a.match.score);
  return { ...data, byId, byResearcher };
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
  return c.aspect_basis === "open_field" || !!c.fields.open_field?.v;
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

export function isStale(iso: string | null | undefined, days = 8): boolean {
  if (!iso) return true;
  return Date.now() - new Date(iso).getTime() > days * 864e5;
}
