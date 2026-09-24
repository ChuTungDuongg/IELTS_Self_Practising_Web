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
const REFRESH_LOCK = "ielts-auth-refresh";

function canRefresh(path: string): boolean {
  return path === "/auth/me" || path === "/auth/profile" || path === "/auth/change-password" || !path.startsWith("/auth/");
}

function announceSessionExpired() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("ielts:session-expired"));
}

async function responseError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  return new ApiError(
    body?.code ?? "API_ERROR",
    body?.message ?? `Request failed with status ${response.status}.`,
    response.status,
    body,
  );
}

// This probe must bypass apiRequest: automatic refresh here would reacquire the lock.
async function probeCurrentSession(): Promise<boolean> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/me`, { cache: "no-store", credentials: "include" });
  } catch (error) {
    throw new ApiError("NETWORK_ERROR", "The API is not reachable.", 0, error);
  }
  if (response.ok) return true;
  if (response.status === 401) return false;
  const error = await responseError(response);
  if (error.code === "ACCOUNT_INACTIVE") announceSessionExpired();
  throw error;
}

async function rotateOrReconcile(): Promise<boolean> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      cache: "no-store",
      credentials: "include",
    });
  } catch {
    // The server may have committed the rotation before the connection failed.
    return probeCurrentSession();
  }
  if (response.ok) return true;
  if (response.status === 401) return probeCurrentSession();
  const error = await responseError(response);
  if (error.code === "ACCOUNT_INACTIVE") announceSessionExpired();
  throw error;
}

async function refreshAccessSession(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (!refreshInFlight) {
    const refresh = async () => {
      if (navigator.locks?.request) {
        return navigator.locks.request(REFRESH_LOCK, async () => {
          if (await probeCurrentSession()) return true;
          return rotateOrReconcile();
        });
      }
      return rotateOrReconcile();
    };
    refreshInFlight = refresh().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
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
  if (response.status === 401 && allowRefresh && canRefresh(path)) {
    if (await refreshAccessSession()) return requestResponse(path, init, false);
  }
  if (!response.ok) {
    const error = await responseError(response);
    if (error.code === "ACCOUNT_INACTIVE") announceSessionExpired();
    if (response.status === 401 && canRefresh(path)) {
      // A retry can still fail for a resource-specific reason while /auth/me is valid.
      if (allowRefresh || !await probeCurrentSession()) announceSessionExpired();
    }
    throw error;
  }
  return response;
}

export function resetAuthRequestStateForTests() {
  refreshInFlight = null;
}
