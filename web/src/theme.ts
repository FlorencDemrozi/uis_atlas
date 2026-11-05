// Colour theme: light, dark or sepia ("paper"). Starts from the saved choice, else the
// operating system's light/dark setting; the choice is stored per browser under
// "atlas-theme". index.html applies it before first paint, so no theme ever flashes.
import { useEffect, useState } from "preact/hooks";

export type Theme = "light" | "dark" | "sepia";
export const THEMES: Theme[] = ["light", "dark", "sepia"];   // order of the switch button
const KEY = "atlas-theme";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (THEMES.includes(saved as Theme)) return saved as Theme;
  } catch { /* storage unavailable */ }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function nextTheme(theme: Theme): Theme {
  return THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const cycle = () => {
    const next = nextTheme(theme);
    setTheme(next);
    try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
  };
  return [theme, cycle];
}
