import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useEffect, useState, type ReactNode } from "react";
import { AuthProvider, useAuth } from "@/features/auth/auth-provider";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { GlobalHeader } from "@/components/ui/global-header";
import { apiRequest } from "@/lib/api/client";
import PersonalizationPage from "@/app/settings/personalization/page";
import { usePersonalization } from "@/features/personalization/personalization-provider";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api/client", async (original) => ({ ...await original<typeof import("@/lib/api/client")>(), apiRequest: vi.fn() }));

const user = { id: "00000000-0000-4000-8000-000000000001", email: "person@example.com", display_name: "Person", role: "USER", is_active: true, created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z", last_login_at: null };
let saved = { accent_color: "PURPLE", appearance: "LIGHT", locale: "EN" };
let currentUser = user;
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
const storageDescriptor = Object.getOwnPropertyDescriptor(window, "localStorage")!;

beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  document.documentElement.dataset.theme = "light";
  document.documentElement.dataset.accent = "purple";
  document.documentElement.lang = "en";
  saved = { accent_color: "PURPLE", appearance: "LIGHT", locale: "EN" };
  currentUser = user;
  vi.mocked(apiRequest).mockImplementation(async (path, init) => {
    if (path === "/auth/me") return currentUser as never;
    if (path === "/auth/logout") return undefined as never;
    if (path === "/me/preferences") {
      if (init?.method === "PATCH") saved = { ...saved, ...JSON.parse(String(init.body)) };
      return { ...saved } as never;
    }
    if (path === "/notifications/unread-count") return { unread_count: 0 } as never;
    if (path.startsWith("/notifications?")) return { items: [] } as never;
    throw new Error(`Unexpected request ${path}`);
  });
});
afterEach(() => { Object.defineProperty(window, "localStorage", storageDescriptor); vi.restoreAllMocks(); });

function Application({ children }: { children?: ReactNode }) {
  return <LocaleProvider><AuthProvider><GlobalHeader pathname={children ? "/settings/personalization" : "/"} />{children}</AuthProvider></LocaleProvider>;
}

function AccountControls() {
  const { confirmSession, logout } = useAuth();
  return <><button onClick={() => void confirmSession()}>Switch account</button><button onClick={() => void logout()}>Sign out</button></>;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function patches() { return vi.mocked(apiRequest).mock.calls.filter(([, init]) => init?.method === "PATCH"); }
async function settingsReady() {
  await screen.findByRole("group", { name: "Accent color" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Blue" })).toBeEnabled());
}

it("header theme changes persist to the authenticated account", async () => {
  render(<Application />);
  await screen.findByText("Person");
  await waitFor(() => expect(screen.getByRole("button", { name: "Use dark theme" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
  await waitFor(() => expect(saved.appearance).toBe("DARK"));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
});

it("backend account settings override another accounts stale browser cache", async () => {
  saved = { accent_color: "BLUE", appearance: "LIGHT", locale: "EN" };
  localStorage.setItem("ielts-accent", "PINK");
  localStorage.setItem("ielts-theme", "dark");
  localStorage.setItem("ielts-locale", "vi");
  render(<Application />);
  await screen.findByText("Person");
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("blue"));
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(document.documentElement.lang).toBe("en");
  expect(localStorage.getItem("ielts-accent")).toBe("BLUE");
  expect(localStorage.getItem("ielts-locale")).toBe("en");
});

it("authenticated header keeps theme, personalization, notifications, profile and logout in order", async () => {
  render(<Application />);
  await screen.findByText("Person");
  const header = within(screen.getByRole("banner"));
  const settings = header.getByRole("link", { name: "Personalization" });
  const profile = header.getByRole("link", { name: /^Person\s*User$/ });
  expect(settings).toHaveAttribute("href", "/settings/personalization");
  expect(settings).toHaveClass("icon-button");
  expect(profile).toHaveAttribute("href", "/profile");
  expect(Array.from(screen.getByRole("banner").querySelector(".header-actions")!.querySelectorAll("a[href], button"))).toEqual([
    header.getByRole("button", { name: "Use dark theme" }),
    settings,
    header.getByRole("button", { name: "Notifications (0 unread)" }),
    profile,
    header.getByRole("button", { name: "Logout" }),
  ]);
});

it("settings exposes exactly three groups, ten preset swatches and the Purple default", async () => {
  render(<Application><PersonalizationPage /></Application>);
  await settingsReady();
  expect(screen.getAllByRole("group").map(node => node.getAttribute("aria-label") ?? node.querySelector("legend")?.textContent)).toEqual(["Accent color", "Appearance", "Language"]);
  const palette = screen.getByRole("group", { name: "Accent color" });
  const buttons = within(palette).getAllByRole("button").filter(node => node.hasAttribute("aria-pressed"));
  expect(buttons.map(node => node.getAttribute("aria-label"))).toEqual(["Purple", "Indigo", "Blue", "Cyan", "Emerald", "Green", "Amber", "Orange", "Red", "Pink"]);
  expect(within(palette).getByRole("button", { name: "Purple" })).toHaveAttribute("aria-pressed", "true");
  expect(document.documentElement.dataset.accent).toBe("purple");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(patches()).toHaveLength(0);
});

it("Blue applies immediately, then persists a partial account patch", async () => {
  const response = deferred<unknown>();
  const normal = vi.mocked(apiRequest).getMockImplementation()!;
  vi.mocked(apiRequest).mockImplementation((path, init) => init?.method === "PATCH" ? response.promise as never : normal(path, init));
  render(<Application><PersonalizationPage /></Application>);
  await settingsReady();
  fireEvent.click(screen.getByRole("button", { name: "Blue" }));
  expect(document.documentElement.dataset.accent).toBe("blue");
  expect(localStorage.getItem("ielts-accent")).toBe("BLUE");
  expect(screen.getByRole("button", { name: "Blue" })).toHaveAttribute("aria-pressed", "true");
  expect(JSON.parse(String(patches()[0][1]?.body))).toEqual({ accent_color: "BLUE" });
  await act(async () => response.resolve({ accent_color: "BLUE", appearance: "LIGHT", locale: "EN" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("rapid clicks serialize and coalesce; an old response cannot replace the latest selection", async () => {
  const first = deferred<unknown>();
  const normal = vi.mocked(apiRequest).getMockImplementation()!;
  let writes = 0;
  vi.mocked(apiRequest).mockImplementation((path, init) => {
    if (init?.method === "PATCH" && ++writes === 1) return first.promise as never;
    return normal(path, init);
  });
  render(<Application><PersonalizationPage /></Application>);
  await settingsReady();
  for (const name of ["Blue", "Pink", "Green"]) fireEvent.click(screen.getByRole("button", { name }));
  expect(document.documentElement.dataset.accent).toBe("green");
  expect(patches()).toHaveLength(1);
  await act(async () => first.resolve({ accent_color: "BLUE", appearance: "LIGHT", locale: "EN" }));
  await waitFor(() => expect(saved.accent_color).toBe("GREEN"));
  expect(patches().map(([, init]) => JSON.parse(String(init?.body)))).toEqual([{ accent_color: "BLUE" }, { accent_color: "GREEN" }]);
  expect(document.documentElement.dataset.accent).toBe("green");
  expect(localStorage.getItem("ielts-accent")).toBe("GREEN");
});

it("failed saves restore confirmed values and show a localized error", async () => {
  saved = { accent_color: "BLUE", appearance: "DARK", locale: "VI" };
  const normal = vi.mocked(apiRequest).getMockImplementation()!;
  vi.mocked(apiRequest).mockImplementation((path, init) => init?.method === "PATCH" ? Promise.reject(new Error("network")) : normal(path, init));
  render(<Application><PersonalizationPage /></Application>);
  await screen.findByRole("group", { name: "Màu nhấn" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Đỏ" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Đỏ" }));
  expect(document.documentElement.dataset.accent).toBe("red");
  expect(await screen.findByRole("alert")).toHaveTextContent("Không lưu được tùy chọn");
  expect(document.documentElement.dataset.accent).toBe("blue");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(document.documentElement.lang).toBe("vi");
  expect(localStorage.getItem("ielts-accent")).toBe("BLUE");
});

it("a load failure disables unconfirmed edits and Retry reconciles to backend", async () => {
  const normal = vi.mocked(apiRequest).getMockImplementation()!;
  let failing = true;
  vi.mocked(apiRequest).mockImplementation((path, init) => path === "/me/preferences" && failing ? Promise.reject(new Error("offline")) : normal(path, init));
  render(<Application><PersonalizationPage /></Application>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load");
  expect(screen.getByRole("button", { name: "Blue" })).toBeDisabled();
  failing = false;
  saved = { accent_color: "PINK", appearance: "DARK", locale: "VI" };
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("pink"));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hồng" })).toBeEnabled();
  expect(patches()).toHaveLength(0);
});

it("settings switches both languages and persists locale while keeping header theme and root synchronized", async () => {
  render(<Application><PersonalizationPage /></Application>);
  await settingsReady();
  fireEvent.click(screen.getByRole("button", { name: "Dark" }));
  await waitFor(() => expect(saved.appearance).toBe("DARK"));
  expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
  const language = screen.getByRole("group", { name: "Language" });
  const english = within(language).getByRole("button", { name: "English" });
  const vietnamese = within(language).getByRole("button", { name: "Tiếng Việt" });
  expect(english).toHaveAttribute("lang", "en");
  expect(english).toHaveAttribute("aria-pressed", "true");
  expect(vietnamese).toHaveAttribute("lang", "vi");
  fireEvent.click(vietnamese);
  await waitFor(() => expect(saved.locale).toBe("VI"));
  expect(document.documentElement.lang).toBe("vi");
  expect(localStorage.getItem("ielts-locale")).toBe("vi");
  expect(vietnamese).toHaveAttribute("aria-pressed", "true");
  expect(english).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("heading", { name: "Cá nhân hóa" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Dùng giao diện sáng" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Ngôn ngữ" })).toBe(language);
  fireEvent.click(english);
  await waitFor(() => expect(saved.locale).toBe("EN"));
  expect(document.documentElement.lang).toBe("en");
  expect(localStorage.getItem("ielts-locale")).toBe("en");
  expect(english).toHaveAttribute("aria-pressed", "true");
  expect(vietnamese).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("heading", { name: "Personalization" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
  expect(patches().map(([, init]) => JSON.parse(String(init?.body)))).toEqual([{ appearance: "DARK" }, { locale: "VI" }, { locale: "EN" }]);
});

it("account switching reconciles all preferences without remounting working content", async () => {
  let mounts = 0;
  function Work() {
    const [answer, setAnswer] = useState("");
    useEffect(() => { mounts++; }, []);
    return <><input aria-label="Answer" value={answer} onChange={event => setAnswer(event.target.value)} /><audio aria-label="Recording" /></>;
  }
  saved = { accent_color: "PINK", appearance: "DARK", locale: "VI" };
  render(<Application><Work /><AccountControls /></Application>);
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("pink"));
  const answer = screen.getByRole("textbox", { name: "Answer" });
  const audio = screen.getByLabelText("Recording") as HTMLAudioElement;
  fireEvent.change(answer, { target: { value: "Keep this answer" } });
  audio.currentTime = 27; audio.volume = .4; audio.muted = true; audio.playbackRate = 1.25;
  currentUser = { ...user, id: "00000000-0000-4000-8000-000000000002", display_name: "Person B" };
  saved = { accent_color: "BLUE", appearance: "LIGHT", locale: "EN" };
  fireEvent.click(screen.getByRole("button", { name: "Switch account" }));
  await screen.findByText("Person B");
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("blue"));
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(document.documentElement.lang).toBe("en");
  expect(screen.getByRole("textbox", { name: "Answer" })).toBe(answer);
  expect(answer).toHaveValue("Keep this answer");
  expect(screen.getByLabelText("Recording")).toBe(audio);
  expect([audio.currentTime, audio.volume, audio.muted, audio.playbackRate]).toEqual([27, .4, true, 1.25]);
  expect(mounts).toBe(1);
  expect(patches()).toHaveLength(0);
});

it("a late account A load cannot overwrite account B", async () => {
  const old = deferred<unknown>();
  const normal = vi.mocked(apiRequest).getMockImplementation()!;
  let loads = 0;
  vi.mocked(apiRequest).mockImplementation((path, init) => path === "/me/preferences" && init?.method !== "PATCH" && ++loads === 1 ? old.promise as never : normal(path, init));
  render(<Application><AccountControls /></Application>);
  await screen.findByText("Person");
  await waitFor(() => expect(loads).toBe(1));
  currentUser = { ...user, id: "00000000-0000-4000-8000-000000000002", display_name: "Person B" };
  saved = { accent_color: "BLUE", appearance: "LIGHT", locale: "EN" };
  fireEvent.click(screen.getByRole("button", { name: "Switch account" }));
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("blue"));
  await act(async () => old.resolve({ accent_color: "PINK", appearance: "DARK", locale: "VI" }));
  expect(document.documentElement.dataset.accent).toBe("blue");
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(document.documentElement.lang).toBe("en");
  expect(localStorage.getItem("ielts-accent")).toBe("BLUE");
});

it("a late account A save and its queued writes never spill into account B", async () => {
  const old = deferred<unknown>();
  const normal = vi.mocked(apiRequest).getMockImplementation()!;
  vi.mocked(apiRequest).mockImplementation((path, init) => init?.method === "PATCH" ? old.promise as never : normal(path, init));
  render(<Application><PersonalizationPage /><AccountControls /></Application>);
  await settingsReady();
  fireEvent.click(screen.getByRole("button", { name: "Blue" }));
  fireEvent.click(screen.getByRole("button", { name: "Pink" }));
  currentUser = { ...user, id: "00000000-0000-4000-8000-000000000002", display_name: "Person B" };
  saved = { accent_color: "GREEN", appearance: "LIGHT", locale: "EN" };
  fireEvent.click(screen.getByRole("button", { name: "Switch account" }));
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("green"));
  expect(patches()[0][1]?.signal?.aborted).toBe(true);
  await act(async () => old.resolve({ accent_color: "BLUE", appearance: "DARK", locale: "VI" }));
  expect(document.documentElement.dataset.accent).toBe("green");
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(document.documentElement.lang).toBe("en");
  expect(patches()).toHaveLength(1);
});

it("same-account session revalidation preserves in-flight and queued preference changes", async () => {
  const first = deferred<unknown>();
  const normal = vi.mocked(apiRequest).getMockImplementation()!;
  let writes = 0;
  vi.mocked(apiRequest).mockImplementation((path, init) => init?.method === "PATCH" && ++writes === 1 ? first.promise as never : normal(path, init));
  render(<Application><PersonalizationPage /><AccountControls /></Application>);
  await settingsReady();
  fireEvent.click(screen.getByRole("button", { name: "Dark" }));
  fireEvent.click(screen.getByRole("button", { name: "Blue" }));
  fireEvent.click(screen.getByRole("button", { name: "Switch account" }));
  await waitFor(() => expect(router.refresh).toHaveBeenCalledOnce());
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(document.documentElement.dataset.accent).toBe("blue");
  expect(vi.mocked(apiRequest).mock.calls.filter(([path, init]) => path === "/me/preferences" && init?.method !== "PATCH")).toHaveLength(1);
  expect(patches()[0][1]?.signal?.aborted).toBe(false);
  saved.appearance = "DARK";
  await act(async () => first.resolve({ ...saved }));
  await waitFor(() => expect(saved.accent_color).toBe("BLUE"));
  expect(saved.appearance).toBe("DARK");
  expect(document.documentElement.dataset.theme).toBe("dark");
});

it("logout does not patch the account and subsequent guest controls only update local state", async () => {
  saved = { accent_color: "PINK", appearance: "DARK", locale: "EN" };
  render(<Application><AccountControls /></Application>);
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("pink"));
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByRole("link", { name: "Login" });
  fireEvent.click(screen.getByRole("button", { name: "Use light theme" }));
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(saved).toEqual({ accent_color: "PINK", appearance: "DARK", locale: "EN" });
  expect(patches()).toHaveLength(0);
});

function GuestControls() {
  const { accentColor, setAccentColor } = usePersonalization();
  return <><p>{accentColor}</p><button onClick={() => setAccentColor("BLUE")}>Choose Blue</button><ThemeToggle /></>;
}
it.each(["#ff0000", "blue", "INVALID", "", null])("invalid cached accents fall back to Purple (%s)", value => {
  if (value !== null) localStorage.setItem("ielts-accent", value);
  render(<LocaleProvider><GuestControls /></LocaleProvider>);
  expect(screen.getByText("PURPLE")).toBeInTheDocument();
  expect(document.documentElement.dataset.accent).toBe("purple");
});

it.each(["getter", "getItem", "setItem"] as const)("blocked local storage still allows all document controls (%s)", failure => {
  if (failure === "getter") Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new Error("blocked"); } });
  else vi.spyOn(Storage.prototype, failure).mockImplementation(() => { throw new Error("blocked"); });
  render(<LocaleProvider><GuestControls /></LocaleProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Choose Blue" }));
  fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
  expect(document.documentElement.dataset.accent).toBe("blue");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(patches()).toHaveLength(0);
});

it("settings hydrates deterministic markup then restores account preferences without warnings", async () => {
  localStorage.setItem("ielts-accent", "PINK");
  localStorage.setItem("ielts-theme", "dark");
  localStorage.setItem("ielts-locale", "vi");
  saved = { accent_color: "BLUE", appearance: "LIGHT", locale: "EN" };
  const read = vi.spyOn(Storage.prototype, "getItem");
  const tree = <Application><PersonalizationPage /></Application>;
  const markup = renderToString(tree);
  expect(markup).toContain("Use dark theme");
  expect(read).not.toHaveBeenCalled();
  expect(apiRequest).not.toHaveBeenCalled();
  const container = document.createElement("div");
  container.innerHTML = markup;
  document.body.append(container);
  const recoverable = vi.fn();
  let root!: ReturnType<typeof hydrateRoot>;
  await act(async () => { root = hydrateRoot(container, tree, { onRecoverableError: recoverable }); });
  await waitFor(() => expect(document.documentElement.dataset.accent).toBe("blue"));
  expect(recoverable).not.toHaveBeenCalled();
  expect(document.documentElement.lang).toBe("en");
  await act(async () => root.unmount());
  container.remove();
});
