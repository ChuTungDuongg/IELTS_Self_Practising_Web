import type { Metadata } from "next";
import Script from "next/script";
import { AppShell } from "@/components/ui/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "IELTS Studio",
  description: "Local IELTS test authoring and practice",
};

export const themeInitializationScript = `(function(){try{var saved=localStorage.getItem("ielts-theme");var theme=saved==="light"||saved==="dark"?saved:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.dataset.theme=theme}catch(e){document.documentElement.dataset.theme="light"}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <body>
        <Script id="theme-initialization" strategy="beforeInteractive">{themeInitializationScript}</Script>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
