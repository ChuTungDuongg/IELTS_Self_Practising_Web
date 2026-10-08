import { NextRequest, NextResponse } from "next/server";
import { API_BASE_URL, ApiError } from "@/lib/api/client";
import { authRedirectPath } from "@/lib/auth-destination";

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
  const session = await checkSession(incomingCookies);

  if (session.status === 401) {
    // Browser apiRequest owns rotation and coordinates it with Web Locks.
    const restore = new URL(authRedirectPath("/session/restore", `${request.nextUrl.pathname}${request.nextUrl.search}`), request.url);
    const response = NextResponse.redirect(restore);
    response.headers.set("Cache-Control", "private, no-store");
    return response;
  }
  if (!session.ok) throw await responseError(session);

  return NextResponse.next();
}

async function checkSession(cookieHeader: string): Promise<Response> {
  return authFetch(`${process.env.API_INTERNAL_BASE_URL ?? API_BASE_URL}/auth/me`, {
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
