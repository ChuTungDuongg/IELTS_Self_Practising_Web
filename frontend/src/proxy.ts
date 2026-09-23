import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL } from "@/lib/api/client";

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
  let authenticated = await checkSession(incomingCookies);
  let refreshedCookies: string[] = [];

  if (!authenticated) {
    const refresh = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      cache: "no-store",
      headers: incomingCookies ? { Cookie: incomingCookies } : undefined,
    }).catch(() => null);
    if (refresh?.ok) {
      refreshedCookies = refresh.headers.getSetCookie();
      authenticated = await checkSession(mergeCookieHeader(incomingCookies, refreshedCookies));
    }
  }

  if (!authenticated) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(login);
  }

  const requestHeaders = new Headers(request.headers);
  if (refreshedCookies.length) {
    requestHeaders.set("cookie", mergeCookieHeader(incomingCookies, refreshedCookies));
  }
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  refreshedCookies.forEach((cookie) => response.headers.append("set-cookie", cookie));
  return response;
}

async function checkSession(cookieHeader: string): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    cache: "no-store",
    headers: cookieHeader ? { Cookie: cookieHeader } : undefined,
  }).catch(() => null);
  return response?.ok === true;
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
