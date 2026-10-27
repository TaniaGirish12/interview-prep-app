import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

function isDark() {
  return document.documentElement.classList.contains("dark");
}

export function setTheme(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
  try {
    localStorage.setItem("theme", dark ? "dark" : "light");
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l());
}

export function useTheme() {
  const dark = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    isDark,
    () => false,
  );
  return { dark, toggle: () => setTheme(!dark) };
}
