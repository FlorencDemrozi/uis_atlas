// Saved project ideas (Project builder, milestone 3). Kept in this browser only
// (localStorage) and independent of the shortlist and saved calls, so changing those never
// removes an idea. In step across open tabs.
import { useCallback, useEffect, useState } from "preact/hooks";
import { mergeIdeas, parseIdeasFile, IDEAS_FORMAT, type Idea } from "./ideas-core";

const KEY = "atlas-project-ideas";

/** Stored as { ideas: Idea[] }; each idea is checked again on load, as an imported file is. */
function fromStore(raw: string | null): Idea[] {
  if (!raw) return [];
  let list: unknown[];
  try { list = (JSON.parse(raw) as { ideas?: unknown[] }).ideas ?? []; } catch { return []; }
  return list.flatMap((x) => {
    const i = (x ?? {}) as Partial<Idea>;
    try {
      return parseIdeasFile(JSON.stringify({ format: IDEAS_FORMAT, version: 1, generated: i.generated, model: i.model,
        prefs: i.prefs, answer_language: i.answer_language, data_dates: i.data_dates, ideas: [x] }));
    } catch { return []; }
  });
}

function load(): Idea[] {
  try { return fromStore(localStorage.getItem(KEY)); } catch { return []; }
}

export interface IdeasValue {
  ideas: Idea[];
  /** "storage" when the browser would not keep the ideas (full or blocked). */
  error: string;
  /** Adds a file's ideas (same id: replaced); returns how many. Throws when the file is not valid. */
  importFile: (text: string) => number;
  remove: (id: string) => void;
}

export function useProjectIdeas(): IdeasValue {
  const [ideas, setIdeas] = useState<Idea[]>(load);
  const [error, setError] = useState("");
  const save = useCallback((next: Idea[]) => {
    try { localStorage.setItem(KEY, JSON.stringify({ ideas: next })); setError(""); }
    catch { setError("storage"); }   // kept for this visit only
    setIdeas(next);
  }, []);
  useEffect(() => {
    const onStorage = (e: StorageEvent) => { if (e.key === KEY) setIdeas(fromStore(e.newValue)); };
    addEventListener("storage", onStorage);
    return () => removeEventListener("storage", onStorage);
  }, []);
  return {
    ideas, error,
    importFile: (text) => {
      const added = parseIdeasFile(text);
      save(mergeIdeas(ideas, added));
      return added.length;
    },
    remove: (id) => save(ideas.filter((i) => i.id !== id)),
  };
}
