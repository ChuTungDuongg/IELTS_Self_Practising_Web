import { renderToStaticMarkup } from "react-dom/server";
import { Children, type ReactElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";
import Script from "next/script";
import RootLayout, { themeInitializationScript } from "@/app/layout";

describe("RootLayout theme initialization", () => {
  it("renders a deterministic server theme and a static beforeInteractive script", () => {
    const markup = renderToStaticMarkup(<RootLayout><p>content</p></RootLayout>);
    expect(markup).toContain('data-theme="light"');
    const layout = RootLayout({ children: <p>content</p> }) as ReactElement<{ children: ReactNode }>;
    const body = layout.props.children as ReactElement<{ children: ReactNode }>;
    const initialization = Children.toArray(body.props.children)[0] as ReactElement<{ id: string; strategy: string }>;
    expect(initialization.type).toBe(Script);
    expect(initialization.props).toMatchObject({ id: "theme-initialization", strategy: "beforeInteractive" });
    expect(themeInitializationScript).toContain('localStorage.getItem("ielts-theme")');
    expect(themeInitializationScript).not.toContain("Date.now");
  });

  it("does not execute localStorage while rendering on the server", () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    Object.defineProperty(globalThis, "localStorage", { configurable: true, get: () => { throw new Error("server localStorage access"); } });
    expect(() => renderToStaticMarkup(<RootLayout><p>content</p></RootLayout>)).not.toThrow();
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
  });
});
