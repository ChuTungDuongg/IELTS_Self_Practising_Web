// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

function request(path: string, cookie = "") {
  return new NextRequest(`http://localhost:3000${path}`, { headers: cookie ? { Cookie: cookie } : undefined });
}

describe("protected route proxy", () => {
  beforeEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("keeps an existing cookie-backed session on protected navigation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const response = await proxy(request("/library", "ielts_access=valid; ielts_refresh=refresh"));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("cookie")).toBe("ielts_access=valid; ielts_refresh=refresh");
  });

  it("redirects only after me and refresh both return 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
    const response = await proxy(request("/admin/tests/new?builder=1"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/login?next=%2Fadmin%2Ftests%2Fnew%3Fbuilder%3D1");
  });

  it("forwards rotated cookies to the browser and the server component request", async () => {
    const access = "ielts_access=new-access; HttpOnly; Max-Age=900; Path=/; SameSite=lax";
    const refresh = "ielts_refresh=new-refresh; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response("{}", { status: 200, headers: [["Set-Cookie", "ielts_access=; Max-Age=0; Path=/api/v1"], ["Set-Cookie", "ielts_refresh=; Max-Age=0; Path=/api/v1/auth"], ["Set-Cookie", access], ["Set-Cookie", refresh]] }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const response = await proxy(request("/admin/tests/123/edit", "ielts_access=old; ielts_refresh=old-refresh"));
    expect(response.status).toBe(200);
    expect(response.headers.getSetCookie()).toEqual(expect.arrayContaining([access, refresh]));
    expect(response.headers.getSetCookie()).toHaveLength(4);
    expect(new Headers(fetchMock.mock.calls[2][1].headers).get("cookie")).toBe("ielts_access=new-access; ielts_refresh=new-refresh");
    expect(response.headers.get("x-middleware-request-cookie")).toBe("ielts_access=new-access; ielts_refresh=new-refresh");
  });

  it("surfaces backend 500 without trying refresh or redirecting", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(proxy(request("/history", "ielts_access=valid"))).rejects.toMatchObject({ status: 500 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces refresh backend failures instead of redirecting", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response("{}", { status: 503 })));
    await expect(proxy(request("/analytics", "ielts_refresh=valid"))).rejects.toMatchObject({ status: 503 });
  });
});
