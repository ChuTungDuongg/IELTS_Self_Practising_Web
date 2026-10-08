import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { getCurrentUser } from "@/lib/api/auth";
import { resetAuthRequestStateForTests } from "@/lib/api/client";
import { proxy } from "@/proxy";

afterEach(() => {
  resetAuthRequestStateForTests();
  vi.unstubAllGlobals();
  Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
});

it("a stale proxy access check cannot race the browser's locked one-time refresh", async () => {
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
  let browserCookiesRestored = false;
  let releaseProxyCheck!: (response: Response) => void;
  const staleProxyCheck = new Promise<Response>((resolve) => { releaseProxyCheck = resolve; });
  const lock = vi.fn(async (_name: string, callback: () => Promise<boolean>) => callback());
  Object.defineProperty(navigator, "locks", { configurable: true, value: { request: lock } });
  const rotations: string[] = [];
  vi.stubGlobal("fetch", vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const fromProxy = new Headers(init?.headers).has("cookie");
    if (url.endsWith("/auth/me")) {
      if (fromProxy) return staleProxyCheck;
      return Promise.resolve(browserCookiesRestored
        ? new Response(JSON.stringify(user))
        : new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 }));
    }
    if (url.endsWith("/auth/refresh")) {
      rotations.push(fromProxy ? "proxy" : "browser");
      if (fromProxy) return Promise.resolve(new Response(JSON.stringify({ code: "INVALID_REFRESH_TOKEN" }), { status: 401 }));
      browserCookiesRestored = true;
      releaseProxyCheck(new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 }));
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    throw new Error("Unexpected auth request");
  }));

  const page = proxy(new NextRequest("http://localhost:3000/library", {
    headers: { Cookie: "ielts_access=fictional-expired; ielts_refresh=fictional-original" },
  }));
  const [currentUser, pageResponse] = await Promise.all([getCurrentUser(), page]);
  expect(currentUser).toEqual(user);
  expect(lock).toHaveBeenCalledWith("ielts-auth-refresh", expect.any(Function));
  expect.soft(rotations).toEqual(["browser"]);
  expect.soft(pageResponse.headers.get("location")).toBe("http://localhost:3000/session/restore?next=%2Flibrary");
});
