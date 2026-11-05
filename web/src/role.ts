// Role categories for the researcher filter, from the Norwegian position title in the
// UiS employee directory (always filled when there is a position; the English title is
// sometimes missing or untranslated). Same idea as POSITION_KINDS in
// pipeline/match_funding.py, with finer academic levels.
import type { Researcher } from "./data";

export const ROLES = ["professor", "associate", "assistant", "adjunct", "postdoc", "phd", "researcher",
  "emeritus", "other", "unknown"] as const;
export type Role = typeof ROLES[number];

// The first matching rule wins: emeritus and adjunct ("Professor II") before the titles.
const RULES: [RegExp, Role][] = [
  [/\bem\.|pensjonert/, "emeritus"],
  [/\bii\b/, "adjunct"],
  [/^stipendiat/, "phd"],
  [/^postdoktor/, "postdoc"],
  [/^(professor|dosent)/, "professor"],
  [/^(førsteamanuensis|førstelektor)/, "associate"],
  [/^(universitetslektor|universitetslærer|amanuensis)/, "assistant"],
  [/^forsker/, "researcher"],
];

/** "unknown": no position in the directory (e.g. found in Scopus only). */
export function roleOf(r: Researcher): Role {
  const p = (r.position?.nb ?? "").trim().toLowerCase();
  if (!p) return "unknown";
  return RULES.find(([re]) => re.test(p))?.[1] ?? "other";
}

export const isRole = (x: string | null): x is Role => !!x && (ROLES as readonly string[]).includes(x);
