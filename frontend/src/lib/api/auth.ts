import { z } from "zod";
import { API_BASE_URL, apiRequest } from "./client";

export const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  display_name: z.string(),
  role: z.enum(["USER", "ADMIN"]),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  last_login_at: z.string().nullable(),
});

const sessionSchema = z.object({ user: userSchema, access_expires_at: z.string() });

export type AuthUser = z.infer<typeof userSchema>;
export type AuthSession = z.infer<typeof sessionSchema>;

export async function register(input: { email: string; display_name: string; password: string }) {
  return sessionSchema.parse(await apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  }));
}

export async function login(input: { email: string; password: string }) {
  return sessionSchema.parse(await apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  }));
}

export async function logout() {
  await apiRequest("/auth/logout", { method: "POST" });
}

export async function getCurrentUser() {
  return userSchema.parse(await apiRequest("/auth/me"));
}

export const googleLoginUrl = `${API_BASE_URL}/auth/oauth/google/start`;
