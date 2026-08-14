import { useEffect, useState } from "react";

const STORAGE_KEY = "coverline-theme";

/**
 * Light/dark theme toggle. Initial state reads whatever class the anti-flash
 * inline script in `__root.tsx` already applied to `<html>` before hydration,
 * so there's no mismatch flash. Toggling flips the `dark` class and persists
 * the choice to localStorage.
 */
export function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    typeof document !== "undefined" && document.documentElement.classList.contains("dark")
      ? "dark"
      : "light",
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // localStorage unavailable (private browsing, etc.) — theme just won't persist.
    }
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  return { theme, toggleTheme };
}
