import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { userSchema } from "./auth";

export const profileFieldsSchema = userSchema.extend({
  email_verified: z.boolean(),
  phone_number: z.string().nullable(),
  date_of_birth: z.string().nullable(),
  country: z.string().nullable(),
  city: z.string().nullable(),
  occupation: z.string().nullable(),
  institution: z.string().nullable(),
  target_band: z.coerce.number().nullable(),
  target_listening_band: z.coerce.number().nullable(),
  target_reading_band: z.coerce.number().nullable(),
  target_writing_band: z.coerce.number().nullable(),
  target_speaking_band: z.coerce.number().nullable(),
  target_test_date: z.string().nullable(),
  bio: z.string().nullable(),
});

export const profileSchema = profileFieldsSchema.extend({ has_password: z.boolean() });

export type Profile = z.infer<typeof profileSchema>;
export type ProfileUpdate = Partial<Pick<Profile,
  "display_name" | "phone_number" | "date_of_birth" | "country" | "city" |
  "occupation" | "institution" | "target_band" | "target_listening_band" |
  "target_reading_band" | "target_writing_band" | "target_speaking_band" | "target_test_date" | "bio"
>>;

export async function getProfile(request: ApiRequester = apiRequest): Promise<Profile> {
  return profileSchema.parse(await request<unknown>("/auth/profile"));
}

export async function updateProfile(update: ProfileUpdate): Promise<Profile> {
  return profileSchema.parse(await apiRequest("/auth/profile", {
    method: "PATCH", body: JSON.stringify(update),
  }));
}
