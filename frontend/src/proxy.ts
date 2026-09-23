import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, ApiError } from "@/lib/api/client";

const protectedRoutes = [
  "/admin",
  "/analytics",
  "/attempt",
  "/history",
  "/library",
  "/review",
  "/test-session",
  "/transfer",
];

export async function proxy(request: NextRequest) {
  if (!protectedRoutes.some((prefix) => request.nextUrl.pathname === prefix || request.nextUrl.pathname.startsWith(`${prefix}/`))) {
    return NextResponse.next();
  }

  const incomingCookies = request.headers.get("cookie") ?? "";
  let session = await checkSession(incomingCookies);
  let refreshedCookies: string[] = [];

  if (session.status === 401) {
    const refresh = await authFetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      cache: "no-store",
      headers: incomingCookies ? { Cookie: incomingCookies } : undefined,
    });
    if (refresh.ok) {
      refreshedCookies = refresh.headers.getSetCookie();
      if (!refreshedCookies.some((cookie) => cookie.startsWith("ielts_access=") && !cookie.startsWith("ielts_access=;"))) {
        throw new ApiError("REFRESH_COOKIES_MISSING", "The API did not return refreshed session cookies.", 502);
      }
      session = await checkSession(mergeCookieHeader(incomingCookies, refreshedCookies));
    } else if (refresh.status !== 401) {
      throw await responseError(refresh);
    }
  }

  if (session.status === 401) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(login);
  }
  if (!session.ok) throw await responseError(session);

  const requestHeaders = new Headers(request.headers);
  if (refreshedCookies.length) {
    requestHeaders.set("cookie", mergeCookieHeader(incomingCookies, refreshedCookies));
  }
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  refreshedCookies.forEach((cookie) => response.headers.append("set-cookie", cookie));
  return response;
}

async function checkSession(cookieHeader: string): Promise<Response> {
  return authFetch(`${API_BASE_URL}/auth/me`, {
    cache: "no-store",
    headers: cookieHeader ? { Cookie: cookieHeader } : undefined,
  });
}

async function authFetch(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (error) {
    throw new ApiError("NETWORK_ERROR", "The API is not reachable.", 0, error);
  }
}

async function responseError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  return new ApiError(body?.code ?? "API_ERROR", body?.message ?? `Request failed with status ${response.status}.`, response.status, body);
}

export function mergeCookieHeader(current: string, setCookies: string[]): string {
  const cookies = new Map<string, string>();
  current.split(";").forEach((entry) => {
    const separator = entry.indexOf("=");
    if (separator > 0) cookies.set(entry.slice(0, separator).trim(), entry.slice(separator + 1).trim());
  });
  setCookies.forEach((entry) => {
    const pair = entry.split(";", 1)[0];
    const separator = pair.indexOf("=");
    if (separator > 0) cookies.set(pair.slice(0, separator).trim(), pair.slice(separator + 1).trim());
  });
  return [...cookies].map(([name, value]) => `${name}=${value}`).join("; ");
}

export const config = {
  matcher: [
    "/admin/:path*",
    "/analytics/:path*",
    "/attempt/:path*",
    "/history/:path*",
    "/library/:path*",
    "/review/:path*",
    "/test-session/:path*",
    "/transfer/:path*",
  ],
};
