import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import "./globals.css";

export const metadata: Metadata = {
  title: "IELTS Practice",
  description: "Local IELTS test authoring and practice",
};

const navItems = [
  ["Dashboard", "/"],
  ["Library", "/library"],
  ["History", "/history"],
  ["Builder", "/admin/tests"],
] as const;

export const themeInitializationScript = `(function(){try{var saved=localStorage.getItem("ielts-theme");var theme=saved==="light"||saved==="dark"?saved:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.dataset.theme=theme}catch(e){document.documentElement.dataset.theme="light"}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <body>
        <Script id="theme-initialization" strategy="beforeInteractive">{themeInitializationScript}</Script>
        <header className="border-b border-[var(--line)] bg-[var(--surface)]">
          <div className="mx-auto flex min-h-16 max-w-6xl items-center justify-between px-5">
            <Link href="/" className="font-semibold tracking-tight">
              IELTS Practice
            </Link>
            <div className="flex items-center gap-2">
              <nav aria-label="Primary" className="flex gap-1 text-sm text-[var(--muted)]">
                {navItems.map(([label, href]) => (
                  <Link key={href} href={href} className="rounded-md px-3 py-2 hover:bg-[var(--surface-soft)]">
                    {label}
                  </Link>
                ))}
              </nav>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-5 py-10">{children}</main>
      </body>
    </html>
  );
}
