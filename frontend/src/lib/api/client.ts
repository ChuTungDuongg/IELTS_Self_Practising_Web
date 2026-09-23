export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ApiRequester = <T>(path: string, init?: RequestInit) => Promise<T>;

let refreshInFlight: Promise<boolean> | null = null;

function canRefresh(path: string): boolean {
  return path === "/auth/me" || !path.startsWith("/auth/");
}

async function refreshAccessSession(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      cache: "no-store",
      credentials: "include",
    }).then((response) => response.ok).catch(() => false).finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function announceSessionExpired() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("ielts:session-expired"));
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiResponse(path, init);
  return await response.json().catch(() => null) as T;
}

export async function apiResponse(path: string, init?: RequestInit): Promise<Response> {
  return requestResponse(path, init, true);
}

async function requestResponse(path: string, init: RequestInit | undefined, allowRefresh: boolean): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch (error) {
    throw new ApiError("NETWORK_ERROR", "The API is not reachable.", 0, error);
  }
  if (
    response.status === 401
    && allowRefresh
    && canRefresh(path)
    && await refreshAccessSession()
  ) {
    return requestResponse(path, init, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401 && canRefresh(path)) announceSessionExpired();
    throw new ApiError(
      body?.code ?? "API_ERROR",
      body?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      body,
    );
  }
  return response;
}

export function resetAuthRequestStateForTests() {
  refreshInFlight = null;
}
