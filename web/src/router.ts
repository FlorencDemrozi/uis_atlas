// Hash routing so the site works as plain static files and search URLs are shareable.
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

export const links = {
  search: (q?: string) => (q ? `#/?q=${encodeURIComponent(q)}` : "#/"),
  overview: "#/overview",
  network: "#/network",
  profile: (id: string) => `#/r/${encodeURIComponent(id)}`,
};
