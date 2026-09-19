"use client";

import { useLayoutEffect } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "ielts-theme";

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function ThemeToggle() {
  useLayoutEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "light" || saved === "dark") {
        document.documentElement.dataset.theme = saved;
      }
    } catch {
      // The deterministic server default remains active when storage is unavailable.
    }
  }, []);

  function toggle() {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The theme still changes for this document even if persistence is unavailable.
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="theme-toggle"
      aria-label="Toggle color theme"
      title="Toggle light and dark mode"
    >
      <span className="theme-light-label" aria-hidden="true"><span className="theme-icon">☾</span><span className="theme-text">Dark</span></span>
      <span className="theme-dark-label" aria-hidden="true"><span className="theme-icon">☀</span><span className="theme-text">Light</span></span>
    </button>
  );
}
