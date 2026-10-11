import { z } from "zod";
import { accentPresets } from "@/features/personalization/accent-palette";
import { apiRequest, type ApiRequester } from "./client";

export const preferencesSchema = z.object({
  accent_color: z.enum(accentPresets),
  appearance: z.enum(["LIGHT", "DARK"]),
  locale: z.enum(["EN", "VI"]),
});
export type Preferences = z.infer<typeof preferencesSchema>;
export type PreferencesUpdate = Partial<Preferences>;

export async function getPreferences(signal?: AbortSignal, request: ApiRequester = apiRequest): Promise<Preferences> {
  return preferencesSchema.parse(await request<unknown>("/me/preferences", { signal }));
}

export async function updatePreferences(update: PreferencesUpdate, signal?: AbortSignal): Promise<Preferences> {
  return preferencesSchema.parse(await apiRequest<unknown>("/me/preferences", {
    method: "PATCH", body: JSON.stringify(update), signal,
  }));
}
