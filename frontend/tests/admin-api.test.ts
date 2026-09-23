import { describe, expect, it, vi } from "vitest";
import { deleteAdminUser, getAdminUsers } from "@/lib/api/admin";
import type { ApiRequester } from "@/lib/api/client";

const emptyList = { items: [], total: 0, offset: 0, limit: 50 };

describe("admin user API", () => {
  it("requests only the selected status and sends search to the server", async () => {
    const request = vi.fn().mockResolvedValue(emptyList) as unknown as ApiRequester;

    await getAdminUsers({ isActive: false, search: "  Ada + B  " }, request);

    expect(request).toHaveBeenCalledWith("/admin/users?is_active=false&search=Ada%20%2B%20B");
  });

  it("sends the selected page offset to the server", async () => {
    const request = vi.fn().mockResolvedValue({ ...emptyList, offset: 25 }) as unknown as ApiRequester;
    await getAdminUsers({ isActive: false, offset: 25 }, request);
    expect(request).toHaveBeenCalledWith("/admin/users?is_active=false&offset=25");
  });

  it("deletes a user through the authenticated API requester", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    try {
      await deleteAdminUser("user/one");
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/admin/users/user%2Fone",
        expect.objectContaining({ method: "DELETE", credentials: "include", cache: "no-store" }),
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
