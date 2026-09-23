import { redirect } from "next/navigation";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { ApiError } from "@/lib/api/client";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  let user;
  try {
    user = userSchema.parse(await serverApiRequest<unknown>("/auth/me"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?next=/admin");
    throw error;
  }
  if (user.role !== "ADMIN") return <section className="empty-state"><h1>Forbidden</h1><p>This workspace is available to administrators only.</p></section>;
  return children;
}
