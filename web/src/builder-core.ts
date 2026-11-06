// Project builder: saved funding calls and how they changed since they were saved.
// No imports, so tests/test_builder.py can run this file directly with Node.
//
// Only the call id, the date it was saved and a few key facts are kept in the browser
// (no titles or texts: the call data itself is password-protected and is read from the
// unlocked funding export each time).

/** The facts compared to flag a change, from the funding index (export_funding.INDEX_FIELDS). */
export const FACTS = ["status", "deadline", "preliminary_deadline", "full_proposal_deadline", "opening_date",
  "rolling", "min_amount", "max_amount", "total_budget", "currency", "min_duration_months", "max_duration_months"] as const;
export type Fact = (typeof FACTS)[number];

export interface SavedCall {
  id: string;
  /** ISO date and time the call was saved (or last marked as checked). */
  saved: string;
  /** FACTS as strings ("" when absent), at that time. */
  facts: Partial<Record<Fact, string>>;
}

type Fields = Record<string, { v: unknown } | undefined>;

const asText = (v: unknown) => (v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v));

export function callFacts(fields: Fields): Partial<Record<Fact, string>> {
  const out: Partial<Record<Fact, string>> = {};
  for (const k of FACTS) out[k] = asText(fields[k]?.v);
  return out;
}

/** The facts that differ from when the call was saved (facts saved by an older version count as unchanged). */
export function changedFacts(saved: SavedCall, fields: Fields): Fact[] {
  const now = callFacts(fields);
  return FACTS.filter((k) => k in saved.facts && saved.facts[k] !== now[k]);
}

/** Closed: by status, or every known deadline has passed (and it is not rolling). */
export function isClosed(fields: Fields, today: string): boolean {
  if (fields.status?.v === "closed") return true;
  if (fields.rolling?.v) return false;
  const dates = ["preliminary_deadline", "deadline", "full_proposal_deadline"]
    .map((k) => fields[k]?.v).filter((d): d is string => typeof d === "string" && d.length >= 10);
  return dates.length > 0 && dates.every((d) => d.slice(0, 10) < today);
}

/** Parse what localStorage holds: anything malformed is dropped, ids are unique, order kept. */
export function parseSaved(raw: string | null): SavedCall[] {
  let v: unknown;
  try { v = JSON.parse(raw ?? "[]"); } catch { return []; }
  if (!Array.isArray(v)) return [];
  const seen = new Set<string>();
  const out: SavedCall[] = [];
  for (const x of v) {
    if (!x || typeof x !== "object") continue;
    const { id, saved, facts } = x as Record<string, unknown>;
    if (typeof id !== "string" || !id || seen.has(id) || typeof saved !== "string") continue;
    const clean: Partial<Record<Fact, string>> = {};
    if (facts && typeof facts === "object") {
      for (const k of FACTS) {
        const f = (facts as Record<string, unknown>)[k];
        if (typeof f === "string") clean[k] = f;
      }
    }
    seen.add(id);
    out.push({ id, saved, facts: clean });
  }
  return out;
}

export function addCall(list: SavedCall[], id: string, fields: Fields, now: string): SavedCall[] {
  return list.some((c) => c.id === id) ? list : [...list, { id, saved: now, facts: callFacts(fields) }];
}

/** "Mark as checked": the call's current facts become the saved ones. */
export function refreshCall(list: SavedCall[], id: string, fields: Fields, now: string): SavedCall[] {
  return list.map((c) => (c.id === id ? { id, saved: now, facts: callFacts(fields) } : c));
}
