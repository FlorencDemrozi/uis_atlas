// Hash routing so the site works as plain static files and search URLs are shareable.
// The faculty/department selection (?org=…) travels with every link and address update.
import { useEffect, useState } from "preact/hooks";

export type View = "search" | "overview" | "network" | "profile" | "shortlist" | "funding" | "call" | "feedback" | "builder"
  | "news" | "privacy";
export interface Route { view: View; id?: string; params: URLSearchParams }

/** decodeURIComponent that keeps a malformed escape (e.g. "%E0%A4") as typed instead of throwing. */
function safeDecode(s: string): string {
  try { return decodeURIComponent(s); } catch { return s; }
}

export function parseHash(hash: string): Route {
  const [path, qs = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(qs);
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "overview") return { view: "overview", params };
  if (parts[0] === "network") return { view: "network", params };
  if (parts[0] === "shortlist") return { view: "shortlist", params };
  if (parts[0] === "feedback") return { view: "feedback", params };
  if (parts[0] === "new") return { view: "news", params };
  if (parts[0] === "privacy") return { view: "privacy", params };
  // "team": the address of the page before it became the Project builder (2026-11-06).
  if (parts[0] === "builder" || parts[0] === "team") return { view: "builder", params };
  if (parts[0] === "funding" && parts[1]) return { view: "call", id: safeDecode(parts[1]), params };
  if (parts[0] === "funding") return { view: "funding", params };
  if (parts[0] === "r" && parts[1]) return { view: "profile", id: safeDecode(parts[1]), params };
  return { view: "search", params };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash));
    addEventListener("hashchange", onChange);
    return () => removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

// Current ?org= value, set by the app whenever the selection changes.
let org = "";
export function setOrgParam(value: string) { org = value; }

function build(path: string, params?: URLSearchParams | Record<string, string>) {
  const p = new URLSearchParams(params);
  p.delete("org");
  if (org) p.set("org", org);
  const qs = p.toString().replace(/%2C/g, ",");
  return `#${path}${qs ? `?${qs}` : ""}`;
}

/** Update the address without a history entry or a hashchange event. */
export function replaceHash(path: string, params?: URLSearchParams) {
  const hash = build(path, params);
  if (location.hash !== hash) history.replaceState(null, "", hash);
}

export const links = {
  search: (q?: string) => build("/", q ? { q } : undefined),
  get overview() { return build("/overview"); },
  get network() { return build("/network"); },
  get feedback() { return build("/feedback"); },
  get builder() { return build("/builder"); },
  get news() { return build("/new"); },
  get privacy() { return build("/privacy"); },
  networkFocus: (id: string) => build("/network", { focus: id }),
  profile: (id: string) => build(`/r/${encodeURIComponent(id)}`),
  shortlist: (ids?: string[]) => build("/shortlist", ids?.length ? { ids: ids.join(",") } : undefined),
  funding: (params?: URLSearchParams) => build("/funding", params),
  call: (id: string) => build(`/funding/${encodeURIComponent(id)}`),
};
