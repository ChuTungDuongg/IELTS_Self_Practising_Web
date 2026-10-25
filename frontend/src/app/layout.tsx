import type { Metadata } from "next";
import { AppShell } from "@/components/ui/app-shell";
import { AuthProvider } from "@/features/auth/auth-provider";
import { PersonalizationProvider } from "@/features/personalization/personalization-provider";
import { accentPresets } from "@/features/personalization/accent-palette";
import "./globals.css";
import "./design-system.css";

export const metadata: Metadata = {
  title: "BandPilot — IELTS Practice & AI Feedback",
  description: "An independent IELTS practice platform for Reading, Listening, Writing and Speaking, with structured mock tests, advisory feedback and learning tools.",
};

export const themeInitializationScript = `(function(){var root=document.documentElement;root.dataset.theme="light";root.dataset.accent="purple";try{var saved=localStorage.getItem("ielts-theme");root.dataset.theme=saved==="dark"?"dark":"light";var accent=localStorage.getItem("ielts-accent");root.dataset.accent=${JSON.stringify(accentPresets)}.indexOf(accent)!==-1?accent.toLowerCase():"purple"}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" data-accent="purple" data-design="editorial" suppressHydrationWarning>
      <body>
        <script
          id="theme-initialization"
          dangerouslySetInnerHTML={{ __html: themeInitializationScript }}
        />
        <PersonalizationProvider><AuthProvider><AppShell currentYear={new Date().getFullYear()}>{children}</AppShell></AuthProvider></PersonalizationProvider>
      </body>
    </html>
  );
}
