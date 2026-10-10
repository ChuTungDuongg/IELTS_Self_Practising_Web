import { act, fireEvent, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LocaleProvider, UiText, useLocale } from "@/lib/i18n/locale-provider";
import { LocaleControls, renderWithLocale } from "./locale-test-utils";

function Copy() { return <><UiText message="runner.pause" /><p><UiText message="runner.question" params={{ number: 2 }} /></p></>; }
const storageDescriptor = Object.getOwnPropertyDescriptor(window, "localStorage")!;

beforeEach(() => { window.localStorage.clear(); document.documentElement.lang = "en"; });
afterEach(() => { Object.defineProperty(window, "localStorage", storageDescriptor); vi.restoreAllMocks(); });

describe("LocaleProvider", () => {
  it("locale starts in English without render-time storage", async () => {
    window.localStorage.setItem("ielts-locale", "vi");
    const read = vi.spyOn(Storage.prototype, "getItem");
    const write = vi.spyOn(Storage.prototype, "setItem");
    const tree = <LocaleProvider><Copy /></LocaleProvider>;
    const markup = renderToString(tree);
    expect(markup).toContain("Pause");
    expect(markup).toContain("Question 2");
    expect(read).not.toHaveBeenCalled();
    expect(write).not.toHaveBeenCalled();
    const container = document.createElement("div");
    container.innerHTML = markup;
    document.body.append(container);
    const recoverable = vi.fn();
    let root: ReturnType<typeof hydrateRoot>;
    await act(async () => { root = hydrateRoot(container, tree, { onRecoverableError: recoverable }); });
    expect(container).toHaveTextContent("Tạm dừng");
    expect(container).toHaveTextContent("Câu hỏi 2");
    expect(document.documentElement.lang).toBe("vi");
    expect(recoverable).not.toHaveBeenCalled();
    expect(write.mock.calls.some(([key, value]) => key === "ielts-locale" && value === "en")).toBe(false);
    await act(async () => root!.unmount());
    container.remove();
  });

  it.each(["en", "vi", "VI", "fr", "", null])("restores only en or vi after mount (%s)", (saved) => {
    if (saved !== null) window.localStorage.setItem("ielts-locale", saved);
    render(<LocaleProvider><Copy /></LocaleProvider>);
    expect(screen.getByText(saved === "vi" ? "Tạm dừng" : "Pause")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe(saved === "vi" ? "vi" : "en");
  });

  it.each(["getter", "getItem", "setItem"])("locale storage failures are non-fatal (%s)", (failure) => {
    if (failure === "getter") Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new Error("blocked"); } });
    else vi.spyOn(Storage.prototype, failure).mockImplementation(() => { throw new Error("blocked"); });
    expect(() => renderWithLocale(<Copy />)).not.toThrow();
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(screen.getByText("Tạm dừng")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("vi");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not read even a throwing storage getter during SSR", () => {
    Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new Error("SSR access"); } });
    expect(renderToString(<LocaleProvider><Copy /></LocaleProvider>)).toContain("Pause");
  });

  it("preserves child identity across locale toggles and escapes UiText parameters", () => {
    let mounts = 0;
    function Child() { useEffect(() => { mounts += 1; }, []); return <UiText message="runner.question" params={{ number: "<img>" }} />; }
    const { container } = renderWithLocale(<Child />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(container).toHaveTextContent("Câu hỏi <img>");
    fireEvent.click(screen.getByRole("button", { name: "Switch to English" }));
    expect(container).toHaveTextContent("Question <img>");
    expect(container.querySelector("img")).toBeNull();
    expect(mounts).toBe(1);
    expect(window.localStorage.getItem("ielts-locale")).toBe("en");
  });

  it("provides an English no-op fallback outside a provider", () => {
    function Isolated() { const { locale, setLocale } = useLocale(); return <button onClick={() => setLocale("vi")}>{locale}<UiText message="runner.pause" /></button>; }
    render(<><Isolated /><LocaleControls /></>);
    fireEvent.click(screen.getByRole("button", { name: "enPause" }));
    expect(screen.getByRole("button", { name: "enPause" })).toBeInTheDocument();
  });
});
