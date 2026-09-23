import "server-only";

import { cookies } from "next/headers";
import { API_BASE_URL, ApiError } from "./client";

export async function serverApiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieStore = await cookies();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        Cookie: cookieStore.toString(),
        ...init?.headers,
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
