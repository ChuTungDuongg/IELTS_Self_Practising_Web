import "server-only";

import { cookies } from "next/headers";
import { API_BASE_URL, ApiError } from "./client";

export async function serverApiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieStore = await cookies();
  const sessionCookies = cookieStore.getAll()
    .filter(({ name }) => name === "ielts_access" || name === "ielts_refresh")
    .map(({ name, value }) => `${name}=${encodeURIComponent(value)}`)
    .join("; ");
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
        ...(sessionCookies ? { Cookie: sessionCookies } : {}),
      },
    });
  } catch (error) {
    throw new ApiError("NETWORK_ERROR", "The API is not reachable.", 0, error);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      body?.code ?? "API_ERROR",
      body?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      body,
    );
  }
  return body as T;
}
