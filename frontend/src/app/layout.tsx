import type { Metadata } from "next";
import { AppShell } from "@/components/ui/app-shell";
import { AuthProvider } from "@/features/auth/auth-provider";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "IELTS Studio",
  description: "A focused IELTS learning, practice, and authoring workspace",
};

export const themeInitializationScript = `(function(){try{var saved=localStorage.getItem("ielts-theme");document.documentElement.dataset.theme=saved==="light"||saved==="dark"?saved:"light"}catch(e){document.documentElement.dataset.theme="light"}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <body>
        <script
          id="theme-initialization"
          dangerouslySetInnerHTML={{ __html: themeInitializationScript }}
        />
        <LocaleProvider><AuthProvider><AppShell currentYear={new Date().getFullYear()}>{children}</AppShell></AuthProvider></LocaleProvider>
      </body>
    </html>
  );
}
