// Funding calls saved for the Project builder (#/builder). Kept in this browser only
// (localStorage, like the researcher shortlist) and in step across open tabs. See
// builder-core.ts for what is stored and how changes are found.
import { createContext } from "preact";
import { useCallback, useContext, useEffect, useMemo, useState } from "preact/hooks";
import { addCall, parseSaved, refreshCall, type SavedCall } from "./builder-core";
import type { Call } from "./funding";

const KEY = "atlas-builder-calls";

function load(): SavedCall[] {
  try { return parseSaved(localStorage.getItem(KEY)); } catch { return []; }
}

export interface BuilderCallsValue {
  calls: SavedCall[];
  has: (id: string) => boolean;
  toggle: (call: Call) => void;
  remove: (id: string) => void;
  clear: () => void;
  /** Accept the call's current facts as checked. */
  refresh: (call: Call) => void;
}

export function useBuilderCallsState(): BuilderCallsValue {
  const [calls, setCalls] = useState<SavedCall[]>(load);
  const save = useCallback((next: SavedCall[]) => {
    setCalls(next);
    try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* storage unavailable: this visit only */ }
  }, []);
  // Another tab changed the list.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => { if (e.key === KEY) setCalls(parseSaved(e.newValue)); };
    addEventListener("storage", onStorage);
    return () => removeEventListener("storage", onStorage);
  }, []);
  return useMemo(() => {
    const now = () => new Date().toISOString();
    return {
      calls,
      has: (id) => calls.some((c) => c.id === id),
      toggle: (call) => save(calls.some((c) => c.id === call.id) ? calls.filter((c) => c.id !== call.id)
        : addCall(calls, call.id, call.fields, now())),
      remove: (id) => save(calls.filter((c) => c.id !== id)),
      clear: () => save([]),
      refresh: (call) => save(refreshCall(calls, call.id, call.fields, now())),
    };
  }, [calls, save]);
}

export const BuilderCallsContext = createContext<BuilderCallsValue>(null as unknown as BuilderCallsValue);
export const useBuilderCalls = () => useContext(BuilderCallsContext);
