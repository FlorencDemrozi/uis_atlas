// The visitor's shortlist of researchers (e.g. for a proposal team). Kept in this
// browser only (localStorage, a per-viewer convenience) and shared as a link:
// #/shortlist?ids=<scopus id>,<scopus id>.
import { createContext } from "preact";
import { useCallback, useContext, useMemo, useState } from "preact/hooks";

const KEY = "atlas-shortlist";

function load(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch { return []; }
}

export interface ShortlistValue {
  ids: string[];
  has: (id: string) => boolean;
  toggle: (id: string) => void;
  remove: (id: string) => void;
  set: (ids: string[]) => void;
}

export function useShortlistState(): ShortlistValue {
  const [ids, setIds] = useState<string[]>(load);
  const set = useCallback((next: string[]) => {
    const unique = [...new Set(next)];
    setIds(unique);
    try { localStorage.setItem(KEY, JSON.stringify(unique)); } catch { /* storage unavailable */ }
  }, []);
  return useMemo(() => ({
    ids,
    has: (id) => ids.includes(id),
    toggle: (id) => set(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]),
    remove: (id) => set(ids.filter((x) => x !== id)),
    set,
  }), [ids, set]);
}

export const ShortlistContext = createContext<ShortlistValue>(null as unknown as ShortlistValue);
export const useShortlist = () => useContext(ShortlistContext);
