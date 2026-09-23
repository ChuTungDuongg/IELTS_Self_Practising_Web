import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, resetAuthRequestStateForTests } from "@/lib/api/client";
import { exportTests, importTests } from "@/lib/api/transfer";

const firstId = "11111111-1111-4111-8111-111111111111";
const secondId = "22222222-2222-4222-8222-222222222222";

describe("Transfer API authentication", () => {
  beforeEach(() => {
    resetAuthRequestStateForTests();
    vi.unstubAllGlobals();
  });

  it("sends selected IDs with browser credentials and returns the named ZIP", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("PK\u0003\u0004fictional", {
      status: 200,
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": 'attachment; filename="ielts-tests-2026-09-23.zip"',
      },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await exportTests([firstId, secondId]);

    expect(result.filename).toBe("ielts-tests-2026-09-23.zip");
    expect(result.blob).toBeInstanceOf(Blob);
    expect(result.blob.size).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/transfer/export");
    expect(init).toMatchObject({ method: "POST", cache: "no-store", credentials: "include" });
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(init.headers).not.toHaveProperty("Authorization");
    expect(JSON.parse(String(init.body))).toEqual({ test_ids: [firstId, secondId] });
  });

  it("refreshes an expired access session once and retries the binary export", async () => {
    let exports = 0;
    const fetchMock = vi.fn((input: string | URL | Request, _init?: RequestInit) => {
      expect(_init?.credentials).toBe("include");
      if (String(input).endsWith("/auth/refresh")) return Promise.resolve(new Response(null, { status: 204 }));
      exports += 1;
      return Promise.resolve(exports === 1
        ? new Response(JSON.stringify({ code: "TOKEN_EXPIRED", message: "Expired" }), { status: 401 })
        : new Response("PK\u0003\u0004fictional", { status: 200, headers: { "Content-Type": "application/zip" } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await exportTests([firstId]);

    expect(result.blob.size).toBeGreaterThan(0);
    expect(exports).toBe(2);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);
    expect(fetchMock.mock.calls.every(([, init]) => init?.credentials === "include")).toBe(true);
  });

  it("preserves a genuine 401 as ApiError and announces the expired session", async () => {
    const onExpired = vi.fn();
    window.addEventListener("ielts:session-expired", onExpired);
    const fetchMock = vi.fn((input: string | URL | Request) => Promise.resolve(
      String(input).endsWith("/auth/refresh")
        ? new Response(JSON.stringify({ code: "INVALID_TOKEN" }), { status: 401 })
        : new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED", message: "Sign in to continue." }), { status: 401 }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    try {
      await expect(exportTests([firstId])).rejects.toMatchObject({
        name: "ApiError", code: "AUTHENTICATION_REQUIRED", status: 401,
      } satisfies Partial<ApiError>);
      expect(onExpired).toHaveBeenCalledOnce();
      expect(fetchMock).toHaveBeenCalledTimes(2);
    } finally {
      window.removeEventListener("ielts:session-expired", onExpired);
    }
  });

  it("keeps ADMIN_REQUIRED distinct from unauthenticated export", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "ADMIN_REQUIRED", message: "Administrator access is required.",
    }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(exportTests([firstId])).rejects.toMatchObject({ code: "ADMIN_REQUIRED", status: 403 });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("keeps import multipart FormData and browser credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      imported_tests: [{ test_id: firstId, title: "Fictional test" }],
      version_count: 1,
      asset_count: 0,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["PK"], "fictional.zip", { type: "application/zip" });

    const result = await importTests(file);

    expect(result.imported_tests[0].title).toBe("Fictional test");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/transfer/import");
    expect(init).toMatchObject({ method: "POST", cache: "no-store", credentials: "include" });
    expect(init.headers).not.toHaveProperty("Content-Type");
    expect(init.headers).not.toHaveProperty("Authorization");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
  });
});
