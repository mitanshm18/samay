// Theme preference: "light", "dark" or "system" (follow the operating system).
// The choice is saved in localStorage; index.html applies it before the first paint,
// so the page never flashes the wrong theme.

import { useCallback, useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";
export type Theme = "light" | "dark";

export const THEME_KEY = "samay-theme";
const PREFS: readonly ThemePref[] = ["light", "dark", "system"];

export function readPref(): ThemePref {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    return PREFS.includes(saved as ThemePref) ? (saved as ThemePref) : "system";
  } catch {
    return "system";
  }
}

export function savePref(pref: ThemePref): void {
  try {
    window.localStorage.setItem(THEME_KEY, pref);
  } catch {
    // Private windows can refuse storage; the theme still applies for this visit.
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function resolveTheme(pref: ThemePref): Theme {
  return pref === "system" ? systemTheme() : pref;
}

export function applyTheme(pref: ThemePref): Theme {
  const theme = resolveTheme(pref);
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.themePref = pref;
  return theme;
}

export function useTheme(): { pref: ThemePref; theme: Theme; setPref: (pref: ThemePref) => void } {
  const [pref, setPrefState] = useState<ThemePref>(readPref);
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(pref));

  useEffect(() => {
    setTheme(applyTheme(pref));
    if (pref !== "system" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-color-scheme: light)");
    const follow = () => setTheme(applyTheme("system"));
    query.addEventListener?.("change", follow);
    return () => query.removeEventListener?.("change", follow);
  }, [pref]);

  const setPref = useCallback((next: ThemePref) => {
    savePref(next);
    setPrefState(next);
  }, []);

  return { pref, theme, setPref };
}
