// Light/dark mode. Starts from the saved choice, else the operating system setting;
// the choice is stored per browser. index.html applies it before first paint.
import { useEffect, useState } from "preact/hooks";

export type Theme = "light" | "dark";
const KEY = "atlas-theme";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* storage unavailable */ }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
  };
  return [theme, toggle];
}
