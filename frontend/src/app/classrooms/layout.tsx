import { redirect } from "next/navigation";
import { serverApiRequest } from "@/lib/api/server-client";
import { ApiError } from "@/lib/api/client";
import { authRedirectPath } from "@/lib/auth-destination";
export default async function ClassroomsLayout({ children }: {
  children: React.ReactNode;
}) {
  try {
    await serverApiRequest("/auth/me");
  }
  catch (error) {
    if (error instanceof ApiError && error.status === 401)
      redirect(authRedirectPath("/session/restore", "/classrooms"));
    throw error;
  }
  return children;
}
