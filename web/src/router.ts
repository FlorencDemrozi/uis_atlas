// Hash routing so the site works as plain static files and search URLs are shareable.
// The faculty/department selection (?org=…) travels with every link and address update.
import { useEffect, useState } from "preact/hooks";

export type View = "search" | "overview" | "network" | "profile";
export interface Route { view: View; id?: string; params: URLSearchParams }

export function parseHash(hash: string): Route {
  const [path, qs = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(qs);
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "overview") return { view: "overview", params };
  if (parts[0] === "network") return { view: "network", params };
  if (parts[0] === "r" && parts[1]) return { view: "profile", id: decodeURIComponent(parts[1]), params };
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
  networkFocus: (id: string) => build("/network", { focus: id }),
  profile: (id: string) => build(`/r/${encodeURIComponent(id)}`),
};
