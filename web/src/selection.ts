// Which faculties and departments the visitor is looking at. Shared by all views
// and kept in the address as ?org=tn,hv-folkehelse (a faculty code means the
// whole faculty). An empty selection means all of UiS.
import { createContext } from "preact";
import { useContext } from "preact/hooks";
import { DEPARTMENTS, FACULTIES, dept, type Faculty, unitByCode } from "./org";

export type Selection = ReadonlySet<string>;   // department keys (incl. "not stated" keys)
export type Level = "faculty" | "department";

export function decodeOrg(param: string | null): Set<string> {
  const sel = new Set<string>();
  for (const code of (param ?? "").split(",").map((c) => c.trim()).filter(Boolean)) {
    const u = unitByCode(code);
    const f = FACULTIES.find((x) => x.key === u?.key);
    if (f) f.depts.forEach((d) => sel.add(d.key));
    else if (u) sel.add(u.key);
  }
  return sel;
}

export function encodeOrg(sel: Selection): string {
  if (!sel.size || isAll(sel)) return "";
  const codes: string[] = [];
  for (const f of FACULTIES) {
    const picked = f.depts.filter((d) => sel.has(d.key));
    if (picked.length === f.depts.length) codes.push(f.code);
    else picked.forEach((d) => codes.push(d.code));
  }
  return codes.join(",");
}

export const isAll = (sel: Selection) => sel.size === 0 || DEPARTMENTS.every((d) => sel.has(d.key));
export const inScope = (sel: Selection, deptKey: string) => isAll(sel) || sel.has(deptKey);

/** Faculties with at least one selected department (all faculties if nothing is selected). */
export function facultiesIn(sel: Selection): Faculty[] {
  return isAll(sel) ? FACULTIES : FACULTIES.filter((f) => f.depts.some((d) => sel.has(d.key)));
}

/** Group by faculty when the scope spans several faculties, else by department. */
export function naturalLevel(sel: Selection): Level {
  return facultiesIn(sel).length > 1 ? "faculty" : "department";
}

/** The key a researcher's department counts under at the given level. */
export function unitKey(deptKey: string, level: Level): string {
  return level === "faculty" ? dept(deptKey).faculty : deptKey;
}

export interface SelectionValue { sel: Selection; setSel: (s: Selection) => void }
export const SelectionContext = createContext<SelectionValue>({ sel: new Set(), setSel: () => {} });
export const useSelection = () => useContext(SelectionContext);
