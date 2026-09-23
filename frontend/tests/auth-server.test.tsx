import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import AdminLayout from "@/app/admin/layout";
import TransferLayout from "@/app/transfer/layout";
import { serverApiRequest } from "@/lib/api/server-client";

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: vi.fn() }));
vi.mock("next/navigation", () => ({
  redirect: vi.fn((path: string) => { throw new Error(`REDIRECT:${path}`); }),
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

describe("server auth requests and layouts", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(cookies).mockResolvedValue({
      getAll: () => [
        { name: "ielts_access", value: "access-token" },
        { name: "ielts_refresh", value: "refresh-token" },
        { name: "theme", value: "dark" },
      ],
    } as never);
  });

  it("forwards browser session cookies to FastAPI for server component requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(user), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(serverApiRequest("/auth/me")).resolves.toEqual(user);
    const forwarded = new Headers(fetchMock.mock.calls[0][1].headers).get("cookie");
    expect(forwarded).toBe("ielts_access=access-token; ielts_refresh=refresh-token");
  });

  it.each([
    ["admin", AdminLayout, "/login?next=/admin"],
    ["transfer", TransferLayout, "/login?next=/transfer"],
  ])("redirects a 401 from %s to login", async (_name, layout, target) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED" }), { status: 401 })));
    await expect(layout({ children: <p>Protected</p> })).rejects.toThrow(`REDIRECT:${target}`);
    expect(redirect).toHaveBeenCalledWith(target);
  });

  it.each([
    ["admin", AdminLayout],
    ["transfer", TransferLayout],
  ])("renders Forbidden for an authenticated USER on %s", async (_name, layout) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(user), { status: 200 })));
    render(await layout({ children: <p>Protected</p> }));
    expect(screen.getByRole("heading", { name: "Forbidden" })).toBeInTheDocument();
    expect(screen.queryByText("Protected")).not.toBeInTheDocument();
    expect(redirect).not.toHaveBeenCalled();
  });

  it("lets an authenticated ADMIN reach nested Builder content", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...user, role: "ADMIN" }), { status: 200 })));
    render(await AdminLayout({ children: <p>Builder workspace</p> }));
    expect(screen.getByText("Builder workspace")).toBeInTheDocument();
  });

  it.each([500, 403])("surfaces backend status %i instead of redirecting to login", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "BACKEND_ERROR" }), { status })));
    await expect(AdminLayout({ children: <p>Protected</p> })).rejects.toMatchObject({ status });
    expect(redirect).not.toHaveBeenCalled();
  });

  it("surfaces a malformed user response instead of redirecting to login", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ role: "ADMIN" }), { status: 200 })));
    await expect(AdminLayout({ children: <p>Protected</p> })).rejects.toThrow();
    expect(redirect).not.toHaveBeenCalled();
  });
});
