import type { Metadata } from "next";
import { AppShell } from "@/components/ui/app-shell";
import { AuthProvider } from "@/features/auth/auth-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "IELTS Studio",
  description: "A focused IELTS learning, practice, and authoring workspace",
};

export const themeInitializationScript = `(function(){try{var saved=localStorage.getItem("ielts-theme");var theme=saved==="light"||saved==="dark"?saved:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.dataset.theme=theme}catch(e){document.documentElement.dataset.theme="light"}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <body>
        <script
          id="theme-initialization"
          dangerouslySetInnerHTML={{ __html: themeInitializationScript }}
        />
        <AuthProvider><AppShell>{children}</AppShell></AuthProvider>
      </body>
    </html>
  );
}
