import type { Metadata } from "next";
import { AppShell } from "@/components/ui/app-shell";
import { AuthProvider } from "@/features/auth/auth-provider";
import { PersonalizationProvider } from "@/features/personalization/personalization-provider";
import { themeInitializationScript } from "@/features/personalization/theme-initialization";
import "@fontsource-variable/raleway";
import "./globals.css";
import "./design-system.css";
import "./gravity-home.css";
import "./gravity-product.css";

export const metadata: Metadata = {
  title: "BandPilot — IELTS Practice & AI Feedback",
  description: "An independent IELTS practice platform for Reading, Listening, Writing and Speaking, with structured mock tests, advisory feedback and learning tools.",
};

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
