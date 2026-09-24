import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/ui/app-shell";
import { AdminGuard } from "@/features/auth/admin-guard";
import { AuthForm } from "@/features/auth/auth-form";
import { AuthProvider } from "@/features/auth/auth-provider";
import { apiRequest, resetAuthRequestStateForTests } from "@/lib/api/client";
import { getCurrentUser, login, logout, register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";

const navigation = vi.hoisted(() => ({ pathname: "/", push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: navigation.push, replace: navigation.replace, refresh: navigation.refresh }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/api/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/auth")>();
  return { ...actual, getCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn(), register: vi.fn() };
});

const baseUser = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "student@example.com",
  display_name: "Student",
  role: "USER" as const,
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  last_login_at: null,
};

describe("authentication UI", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    navigation.pathname = "/";
    vi.mocked(logout).mockResolvedValue(undefined);
  });

  it("shows login actions while logged out", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new ApiError("AUTHENTICATION_REQUIRED", "Sign in", 401));
    render(<AuthProvider><AppShell><p>Content</p></AppShell></AuthProvider>);
    expect(await screen.findByRole("link", { name: "Login" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Builder" })).not.toBeInTheDocument();
  });

  it("hides admin navigation for USER and shows it for ADMIN", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(baseUser);
    const first = render(<AuthProvider><AppShell><p>User content</p></AppShell></AuthProvider>);
    await screen.findByText("Student");
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Builder" })).not.toBeInTheDocument();
    first.unmount();

    vi.mocked(getCurrentUser).mockResolvedValue({ ...baseUser, role: "ADMIN" });
    render(<AuthProvider><AppShell><p>Admin content</p></AppShell></AuthProvider>);
    expect(await screen.findByRole("link", { name: "Admin" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Builder" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Transfer" })).toBeInTheDocument();
  });

  it("renders Forbidden for a USER admin guard", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(baseUser);
    render(<AuthProvider><AdminGuard><p>Secret admin workspace</p></AdminGuard></AuthProvider>);
    expect(await screen.findByRole("heading", { name: "Forbidden" })).toBeInTheDocument();
    expect(screen.queryByText("Secret admin workspace")).not.toBeInTheDocument();
  });

  it("allows an ADMIN through the client guard", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({ ...baseUser, role: "ADMIN" });
    render(<AuthProvider><AdminGuard><p>Secret admin workspace</p></AdminGuard></AuthProvider>);
    expect(await screen.findByText("Secret admin workspace")).toBeInTheDocument();
  });

  it("shows a session check error in the admin guard without redirecting", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new ApiError("API_ERROR", "Backend failed", 500));
    render(<AuthProvider><AdminGuard><p>Secret admin workspace</p></AdminGuard></AuthProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend failed");
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it("logout clears the authenticated shell state", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(baseUser);
    render(<AuthProvider><AppShell><p>Content</p></AppShell></AuthProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "Logout" }));
    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
    expect(await screen.findByRole("link", { name: "Login" })).toBeInTheDocument();
    expect(navigation.push).toHaveBeenCalledWith("/login");
  });

  it("updates the application shell after a successful login", async () => {
    vi.mocked(getCurrentUser)
      .mockRejectedValueOnce(new ApiError("AUTHENTICATION_REQUIRED", "Sign in", 401))
      .mockResolvedValueOnce(baseUser);
    vi.mocked(login).mockResolvedValue({ user: baseUser, access_expires_at: new Date().toISOString() });
    render(<AuthProvider><AuthForm mode="login" /><AppShell><p>Content</p></AppShell></AuthProvider>);

    await screen.findByRole("link", { name: "Login" });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "student@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "safe-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Student")).toBeInTheDocument();
    expect(login).toHaveBeenCalledWith({ email: "student@example.com", password: "safe-password" });
    expect(getCurrentUser).toHaveBeenCalledTimes(2);
    expect(navigation.push).toHaveBeenCalledWith("/");
  });

  it("does not accept a login response when the cookie-backed session cannot be read", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new ApiError("AUTHENTICATION_REQUIRED", "Sign in", 401));
    vi.mocked(login).mockResolvedValue({ user: baseUser, access_expires_at: new Date().toISOString() });
    render(<AuthProvider><AuthForm mode="login" /><AppShell><p>Content</p></AppShell></AuthProvider>);
    await screen.findByRole("link", { name: "Login" });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "student@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "safe-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Student")).not.toBeInTheDocument();
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("surfaces non-401 session errors without showing a logged-out shell", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new ApiError("API_ERROR", "Backend failed", 500));
    render(<AuthProvider><AppShell><p>Content</p></AppShell></AuthProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend failed");
    expect(screen.queryByRole("link", { name: "Login" })).not.toBeInTheDocument();
  });

  it("requires matching registration passwords and never offers a role choice", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new Error("unauthenticated"));
    vi.mocked(register).mockResolvedValue({ user: baseUser, access_expires_at: new Date().toISOString() });
    render(<AuthProvider><AuthForm mode="register" /></AuthProvider>);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Student" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "student@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "safe-password" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "different-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(register).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(/role/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "safe-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(register).toHaveBeenCalledWith({
      email: "student@example.com",
      display_name: "Student",
      password: "safe-password",
    }));
  });
});

describe("API refresh coordination", () => {
  beforeEach(() => {
    resetAuthRequestStateForTests();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
  });

  it("uses one refresh for concurrent 401 responses and retries both requests once", async () => {
    const attempts = new Map<string, number>();
    let resolveRefresh!: (response: Response) => void;
    const refreshResponse = new Promise<Response>((resolve) => { resolveRefresh = resolve; });
    const fetchMock = vi.fn((input: string | URL | Request, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/auth/refresh")) return refreshResponse;
      const count = (attempts.get(url) ?? 0) + 1;
      attempts.set(url, count);
      return Promise.resolve(count === 1
        ? new Response(JSON.stringify({ code: "TOKEN_EXPIRED", message: "Expired" }), { status: 401 })
        : new Response(JSON.stringify({ url, fresh: true }), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    const first = apiRequest<{ fresh: boolean }>("/resource-one");
    const second = apiRequest<{ fresh: boolean }>("/resource-two");
    await waitFor(() => expect(fetchMock.mock.calls.filter(([value]) => String(value).endsWith("/auth/refresh"))).toHaveLength(1));
    resolveRefresh(new Response(null, { status: 204 }));

    await expect(Promise.all([first, second])).resolves.toEqual([
      expect.objectContaining({ fresh: true }),
      expect.objectContaining({ fresh: true }),
    ]);
    expect(fetchMock.mock.calls.filter(([value]) => String(value).endsWith("/auth/refresh"))).toHaveLength(1);
    expect(fetchMock.mock.calls.every(([, init]) => init?.credentials === "include")).toBe(true);
  });

  it("announces unauthenticated state when refresh fails", async () => {
    const expired = vi.fn();
    window.addEventListener("ielts:session-expired", expired);
    vi.stubGlobal("fetch", vi.fn((input: string | URL | Request) => Promise.resolve(
      new Response(JSON.stringify({ code: "INVALID_TOKEN", message: `Invalid ${String(input)}` }), { status: 401 }),
    )));

    await expect(apiRequest("/protected")).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener("ielts:session-expired", expired);
  });

  it("uses a cross-tab lock and skips rotation after another tab recovers the cookies", async () => {
    const request = vi.fn(async (_name: string, callback: () => Promise<boolean>) => callback());
    Object.defineProperty(navigator, "locks", { configurable: true, value: { request } });
    let protectedCalls = 0;
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return Promise.resolve(new Response(JSON.stringify(baseUser)));
      if (url.endsWith("/auth/refresh")) throw new Error("rotation should be skipped");
      protectedCalls += 1;
      return Promise.resolve(protectedCalls === 1
        ? new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 })
        : new Response(JSON.stringify({ saved: true })));
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/protected")).resolves.toEqual({ saved: true });
    expect(request).toHaveBeenCalledWith("ielts-auth-refresh", expect.any(Function));
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(0);
    expect(protectedCalls).toBe(2);
  });

  it("recovers a losing refresh request when another tab has already updated cookies", async () => {
    const expired = vi.fn();
    window.addEventListener("ielts:session-expired", expired);
    let protectedCalls = 0;
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) return Promise.resolve(new Response(null, { status: 401 }));
      if (url.endsWith("/auth/me")) return Promise.resolve(new Response(JSON.stringify(baseUser)));
      protectedCalls += 1;
      return Promise.resolve(protectedCalls === 1
        ? new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 })
        : new Response(JSON.stringify({ saved: true })));
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      await expect(apiRequest("/protected")).resolves.toEqual({ saved: true });
      expect(expired).not.toHaveBeenCalled();
      expect(protectedCalls).toBe(2);
    } finally {
      window.removeEventListener("ielts:session-expired", expired);
    }
  });

  it("announces real expiration once after the lock probe and failure reconciliation", async () => {
    const request = vi.fn(async (_name: string, callback: () => Promise<boolean>) => callback());
    Object.defineProperty(navigator, "locks", { configurable: true, value: { request } });
    const expired = vi.fn();
    window.addEventListener("ielts:session-expired", expired);
    const fetchMock = vi.fn(() => Promise.resolve(new Response(
      JSON.stringify({ code: "AUTHENTICATION_REQUIRED", message: "Sign in" }), { status: 401 },
    )));
    vi.stubGlobal("fetch", fetchMock);

    try {
      await expect(apiRequest("/protected")).rejects.toMatchObject({ status: 401 });
      expect(expired).toHaveBeenCalledOnce();
      expect(fetchMock).toHaveBeenCalledTimes(4);
    } finally {
      window.removeEventListener("ielts:session-expired", expired);
    }
  });

  it("keeps a refresh network failure retryable when reconciliation also loses the network", async () => {
    const expired = vi.fn();
    window.addEventListener("ielts:session-expired", expired);
    const fetchMock = vi.fn((input: string | URL | Request) => {
      if (String(input).endsWith("/protected")) {
        return Promise.resolve(new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 }));
      }
      return Promise.reject(new TypeError("offline"));
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      await expect(apiRequest("/protected")).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
      expect(expired).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(3);
    } finally {
      window.removeEventListener("ielts:session-expired", expired);
    }
  });

  it("recovers when refresh loses its response but the shared cookies are valid", async () => {
    const expired = vi.fn();
    window.addEventListener("ielts:session-expired", expired);
    let protectedCalls = 0;
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) return Promise.reject(new TypeError("connection lost"));
      if (url.endsWith("/auth/me")) return Promise.resolve(new Response(JSON.stringify(baseUser)));
      protectedCalls += 1;
      return Promise.resolve(protectedCalls === 1
        ? new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 })
        : new Response(JSON.stringify({ saved: true })));
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      await expect(apiRequest("/protected")).resolves.toEqual({ saved: true });
      expect(expired).not.toHaveBeenCalled();
      expect(protectedCalls).toBe(2);
    } finally {
      window.removeEventListener("ielts:session-expired", expired);
    }
  });

  it("clears provider state on ACCOUNT_INACTIVE without refreshing", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(baseUser);
    render(<AuthProvider><AppShell><p>Content</p></AppShell></AuthProvider>);
    await screen.findByText("Student");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "ACCOUNT_INACTIVE", message: "This account is inactive.",
    }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/protected")).rejects.toMatchObject({ code: "ACCOUNT_INACTIVE", status: 403 });
    expect(await screen.findByRole("link", { name: "Login" })).toBeInTheDocument();
    expect(screen.queryByText("Student")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("leaves ADMIN_REQUIRED as a plain 403 without refreshing", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "ADMIN_REQUIRED", message: "Administrator access is required.",
    }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest("/admin/tests")).rejects.toMatchObject({ code: "ADMIN_REQUIRED", status: 403 });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("does not expire a valid session when a retried resource still returns 401", async () => {
    const expired = vi.fn();
    window.addEventListener("ielts:session-expired", expired);
    const fetchMock = vi.fn((input: string | URL | Request) => Promise.resolve(
      String(input).endsWith("/auth/me")
        ? new Response(JSON.stringify(baseUser))
        : String(input).endsWith("/auth/refresh")
          ? new Response(null, { status: 204 })
          : new Response(JSON.stringify({ code: "RESOURCE_DENIED" }), { status: 401 }),
    ));
    vi.stubGlobal("fetch", fetchMock);

    try {
      await expect(apiRequest("/protected")).rejects.toMatchObject({ code: "RESOURCE_DENIED", status: 401 });
      expect(expired).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(4);
    } finally {
      window.removeEventListener("ielts:session-expired", expired);
    }
  });

  it("refreshes an expired auth/me request before hydrating the session", async () => {
    let meCalls = 0;
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) return Promise.resolve(new Response(null, { status: 204 }));
      meCalls += 1;
      return Promise.resolve(meCalls === 1
        ? new Response(JSON.stringify({ code: "TOKEN_EXPIRED", message: "Expired" }), { status: 401 })
        : new Response(JSON.stringify(baseUser), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/auth/me")).resolves.toEqual(baseUser);
    expect(fetchMock.mock.calls.filter(([value]) => String(value).endsWith("/auth/refresh"))).toHaveLength(1);
    expect(meCalls).toBe(2);
  });
});
