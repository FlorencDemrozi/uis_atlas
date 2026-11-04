// External partner institutions (data/public/partners.json, pipeline/build_partners.py):
// per researcher, the institutions outside UiS of their co-authors and the countries,
// with the number of shared papers. Loaded only by the views that show it.
import { useEffect, useState } from "preact/hooks";
import type { Lang } from "./i18n";

export interface Institution { afid: string; name: string; city: string | null; country: string | null }

export interface ResearcherPartners {
  /** [afid, papers], most first */
  institutions: [string, number][];
  /** [Scopus country name, papers], most first; a paper counts once per country */
  countries: [string, number][];
}

export interface Partners {
  institutions: Map<string, Institution>;
  byResearcher: Map<string, ResearcherPartners>;
}

interface Stored {
  institutions: Record<string, [string, string | null, string | null]>;
  researchers: Record<string, { i: [string, number][]; c: [string, number][] }>;
}

let pending: Promise<Partners> | null = null;

export function loadPartners(): Promise<Partners> {
  pending ??= fetch("./data/partners.json")
    .then((res) => {
      if (!res.ok) throw new Error(`Could not load partners.json (${res.status})`);
      return res.json() as Promise<Stored>;
    })
    .then((s) => ({
      institutions: new Map(Object.entries(s.institutions).map(([afid, [name, city, country]]) =>
        [afid, { afid, name, city, country }])),
      byResearcher: new Map(Object.entries(s.researchers).map(([id, r]) =>
        [id, { institutions: r.i, countries: r.c }])),
    }))
    .catch((e) => { pending = null; throw e; });
  return pending;
}

/** Partner data once loaded (null while loading or when `enabled` is false). */
export function usePartners(enabled = true): { data: Partners | null; error: string | null } {
  const [data, setData] = useState<Partners | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || data) return;
    let live = true;
    loadPartners().then((d) => live && setData(d), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [enabled]);
  return { data, error };
}

export const scopusAffiliationUrl = (afid: string) => `https://www.scopus.com/affil/profile.uri?afid=${afid}`;

// Scopus country names whose region code Intl cannot find from the English name.
const REGION: Record<string, string> = {
  "Bosnia and Herzegovina": "BA", "Czech Republic": "CZ", "Russian Federation": "RU", "Viet Nam": "VN",
  "Syrian Arab Republic": "SY", "Hong Kong": "HK", "Macao": "MO", "Brunei Darussalam": "BN",
  "Palestine": "PS", "Congo": "CG", "Democratic Republic Congo": "CD", "Turkey": "TR",
  "Trinidad and Tobago": "TT", "Antigua and Barbuda": "AG", "Cote d'Ivoire": "CI", "Myanmar": "MM",
  "Laos": "LA", "Lao People's Democratic Republic": "LA", "Saint Kitts and Nevis": "KN",
  "Saint Vincent and the Grenadines": "VC", "Sao Tome and Principe": "ST", "Micronesia": "FM",
  "Curacao": "CW", "Reunion": "RE", "Holy See (Vatican City State)": "VA",
};

let regionOf: Map<string, string> | null = null;

/** Region code (e.g. "NO") of a Scopus country name, or null. */
function region(name: string): string | null {
  if (REGION[name]) return REGION[name];
  if (!regionOf) {
    regionOf = new Map();
    try {
      const en = new Intl.DisplayNames(["en"], { type: "region" });
      for (let a = 65; a <= 90; a++) {
        for (let b = 65; b <= 90; b++) {
          const code = String.fromCharCode(a, b);
          const n = en.of(code);
          if (n && n !== code) regionOf.set(n.toLowerCase(), code);
        }
      }
    } catch { /* old browser: English names are shown */ }
  }
  return regionOf.get(name.toLowerCase()) ?? null;
}

const names = new Map<Lang, Intl.DisplayNames | null>();

/** A Scopus country name in the page language (Scopus's English name as fallback). */
export function countryName(name: string, lang: Lang): string {
  if (!names.has(lang)) {
    try { names.set(lang, new Intl.DisplayNames([lang === "nb" ? "nb" : "en"], { type: "region" })); }
    catch { names.set(lang, null); }
  }
  const code = region(name);
  const dn = names.get(lang);
  return (code && dn?.of(code)) || name;
}
