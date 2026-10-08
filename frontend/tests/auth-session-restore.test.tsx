import { act, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SessionRestorePage from "@/app/session/restore/page";
import { AuthProvider, useAuth } from "@/features/auth/auth-provider";
import { resetAuthRequestStateForTests } from "@/lib/api/client";

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.search),
  useRouter: () => ({ refresh: navigation.refresh, push: navigation.push }),
}));

const user = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "student@example.com",
  display_name: "Student",
  role: "USER",
  is_active: true,
  created_at: "2026-09-23T00:00:00Z",
  updated_at: "2026-09-23T00:00:00Z",
  last_login_at: null,
};

function SessionUser() {
  return <p>{useAuth().user?.display_name}</p>;
}

describe("browser session restoration", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.unstubAllGlobals();
    resetAuthRequestStateForTests();
    navigation.search = "next=%2Flibrary%3Fmodule%3DWRITING";
    const currentWindow = window;
    vi.stubGlobal("window", new Proxy(currentWindow, {
      get: (target, property) => property === "location"
        ? { replace: navigation.replace }
        : Reflect.get(target, property, target),
    }));
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: { request: vi.fn(async (_name: string, callback: () => Promise<boolean>) => callback()) },
    });
  });

  afterEach(() => {
    resetAuthRequestStateForTests();
    vi.unstubAllGlobals();
    Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
  });

  it.each(["/library?module=WRITING", "/history"])("restores expired access with one browser rotation before replacing to %s", async (destination) => {
    navigation.search = new URLSearchParams({ next: destination }).toString();
    let restored = false;
    const fetchMock = vi.fn((input: string | URL | Request) => {
      if (String(input).endsWith("/auth/refresh")) {
        restored = true;
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      return Promise.resolve(restored
        ? new Response(JSON.stringify(user))
        : new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<StrictMode><AuthProvider><SessionRestorePage /></AuthProvider></StrictMode>);
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith(destination));
    expect(navigation.replace).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);
    expect(navigator.locks.request).toHaveBeenCalledWith("ielts-auth-refresh", expect.any(Function));
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("preserves a safe next destination when the refresh session is invalid", async () => {
    const fetchMock = vi.fn((_input: string | URL | Request) => {
      void _input;
      return Promise.resolve(new Response(JSON.stringify({ code: "INVALID_REFRESH_TOKEN" }), { status: 401 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AuthProvider><SessionRestorePage /></AuthProvider>);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/login?next=%2Flibrary%3Fmodule%3DWRITING"));
    expect(navigation.replace).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it("rechecks expired cookies even when the persistent shell already holds a user", async () => {
    let validAccess = true;
    const fetchMock = vi.fn((input: string | URL | Request) => {
      if (String(input).endsWith("/auth/refresh")) {
        validAccess = true;
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      return Promise.resolve(validAccess
        ? new Response(JSON.stringify(user))
        : new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const page = render(<AuthProvider><SessionUser /></AuthProvider>);
    await screen.findByText("Student");
    validAccess = false;
    page.rerender(<AuthProvider><SessionUser /><SessionRestorePage /></AuthProvider>);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/library?module=WRITING"));
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it("keeps refresh-service failures visible without treating them as an invalid session", async () => {
    const fetchMock = vi.fn((input: string | URL | Request) => Promise.resolve(
      String(input).endsWith("/auth/refresh")
        ? new Response(JSON.stringify({ code: "API_ERROR", message: "Refresh temporarily unavailable" }), { status: 503 })
        : new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    render(<SessionRestorePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh temporarily unavailable");
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it.each([0, 500, 403])("surfaces transient/non-auth status %i without navigating or starting a loop", async (status) => {
    const fetchMock = vi.fn(() => status === 0
      ? Promise.reject(new TypeError("offline"))
      : Promise.resolve(new Response(JSON.stringify({ code: "API_ERROR", message: "Session check failed" }), { status })));
    vi.stubGlobal("fetch", fetchMock);
    render(<SessionRestorePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(status === 0 ? "The API is not reachable." : "Session check failed");
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("treats an inactive account as invalid rather than restoring indefinitely", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ code: "ACCOUNT_INACTIVE" }), { status: 403 }))));
    render(<SessionRestorePage />);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/login?next=%2Flibrary%3Fmodule%3DWRITING"));
  });

  it.each(["//evil.example", "https://evil.example", "javascript:alert(1)", "/\\evil.example", "/session/restore?next=/library", "/login", "/%6cogin", "/foo/../session/restore"])("rejects unsafe or looping next=%s", async (next) => {
    navigation.search = new URLSearchParams({ next }).toString();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(user)))));
    render(<SessionRestorePage />);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/"));
  });

  it("does not navigate after the restore page is unmounted", async () => {
    let resolve!: (response: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((done) => { resolve = done; }));
    vi.stubGlobal("fetch", fetchMock);
    const page = render(<SessionRestorePage />);
    expect(fetchMock).toHaveBeenCalledOnce();
    page.unmount();
    await act(async () => { resolve(new Response(JSON.stringify(user))); });
    expect(navigation.replace).not.toHaveBeenCalled();
  });
});
