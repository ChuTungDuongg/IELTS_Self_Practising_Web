// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

function request(path: string, cookie = "") {
  return new NextRequest(`http://localhost:3000${path}`, { headers: cookie ? { Cookie: cookie } : undefined });
}

describe("protected route proxy", () => {
  beforeEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("uses the internal FastAPI origin when the browser API URL is relative", async () => {
    vi.stubEnv("API_INTERNAL_BASE_URL", "http://127.0.0.1:9001/api/v1");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    try {
      await proxy(request("/history", "ielts_access=valid"));
      expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:9001/api/v1/auth/me");
    } finally { vi.unstubAllEnvs(); }
  });

  it("keeps an existing cookie-backed session on protected navigation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const response = await proxy(request("/library", "ielts_access=valid; ielts_refresh=refresh"));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("cookie")).toBe("ielts_access=valid; ielts_refresh=refresh");
  });

  it("sends expired access to browser restoration without rotating refresh cookies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    const response = await proxy(request("/admin/tests/new?builder=1"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/session/restore?next=%2Fadmin%2Ftests%2Fnew%3Fbuilder%3D1");
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/auth\/me$/);
    expect(response.headers.getSetCookie()).toHaveLength(0);
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("leaves restoration and public auth pages unguarded", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const path of ["/session/restore?next=/library", "/login", "/register", "/"]) {
      expect((await proxy(request(path))).headers.get("location")).toBeNull();
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("checks a fresh authenticated navigation after an unauthenticated prefetch redirect", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const prefetch = request("/library");
    prefetch.headers.set("Next-Router-Prefetch", "1");
    expect((await proxy(prefetch)).headers.get("location")).toContain("/session/restore?");
    const navigation = await proxy(request("/library", "ielts_access=new-session"));
    expect(navigation.status).toBe(200);
    expect(navigation.headers.get("location")).toBeNull();
    expect(fetchMock.mock.calls[1][1].cache).toBe("no-store");
    expect(new Headers(fetchMock.mock.calls[1][1].headers).get("cookie")).toBe("ielts_access=new-session");
  });

  it("surfaces backend 500 without trying refresh or redirecting", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(proxy(request("/history", "ielts_access=valid"))).rejects.toMatchObject({ status: 500 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces an offline auth check without trying refresh or redirecting", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(proxy(request("/analytics", "ielts_refresh=valid"))).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
