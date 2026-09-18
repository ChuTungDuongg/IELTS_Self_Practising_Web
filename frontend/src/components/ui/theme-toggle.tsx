"use client";

type Theme = "light" | "dark";
const STORAGE_KEY = "ielts-theme";

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function ThemeToggle() {
  function toggle() {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem(STORAGE_KEY, next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="inline-flex min-w-24 items-center justify-center gap-2 rounded-md border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--muted)] hover:bg-[var(--surface-soft)]"
      aria-label="Toggle color theme"
      title="Toggle light and dark mode"
    >
      <span className="theme-light-label" aria-hidden="true">☾ Dark</span>
      <span className="theme-dark-label" aria-hidden="true">☀ Light</span>
    </button>
  );
}
