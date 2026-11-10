// What's new: researchers (changes.json, public ids only) and funding calls (the
// encrypted funding index, meta.new_calls) first seen in recent weekly runs
// (pipeline/build_changes.py). The browser remembers the date of the last update the
// visitor has looked at ("atlas-news-seen"), so the header can count what is unseen.
// Nothing leaves the browser.
import { createContext } from "preact";
import { useCallback, useContext, useEffect, useMemo, useState } from "preact/hooks";
import type { Funding } from "./funding";

export interface Batch { date: string; ids: string[] }
export interface Changes { generated: string; since: string; days: number; researchers: Batch[] }

const KEY = "atlas-news-seen";

function readSeen(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

/** New calls that are still in the funding data (and not closed since). */
export function callBatches(data: Funding): Batch[] {
  return (data.meta.new_calls ?? [])
    .map((b) => ({ date: b.date, ids: b.ids.filter((id) => { const c = data.byId.get(id); return c && !c.closed_by_date; }) }))
    .filter((b) => b.ids.length);
}

/** Items in batches after `seen`; with nothing seen yet, the latest batch only. */
export function unseen(batches: Batch[], seen: string | null): number {
  const latest = batches.reduce((m, b) => (b.date > m ? b.date : m), "");
  const counts = (b: Batch) => (seen ? b.date > seen : b.date === latest);
  return batches.filter(counts).reduce((n, b) => n + b.ids.length, 0);
}

export interface NewsValue {
  changes: Changes | null;
  /** Date of the last update the visitor has seen (null: never opened the page). */
  seen: string | null;
  markSeen: (date: string) => void;
}

export const NewsContext = createContext<NewsValue>(null as unknown as NewsValue);
export const useNews = () => useContext(NewsContext);

export function useNewsState(): NewsValue {
  const [changes, setChanges] = useState<Changes | null>(null);
  const [seen, setSeen] = useState<string | null>(readSeen);
  useEffect(() => {
    // Optional file (older exports have none): no news is not an error.
    fetch("./data/changes.json").then((r) => (r.ok ? r.json() : null)).then(setChanges).catch(() => setChanges(null));
  }, []);
  const markSeen = useCallback((date: string) => {
    setSeen((old) => {
      if (old && old >= date) return old;
      try { localStorage.setItem(KEY, date); } catch { /* storage unavailable */ }
      return date;
    });
  }, []);
  return useMemo(() => ({ changes, seen, markSeen }), [changes, seen, markSeen]);
}
