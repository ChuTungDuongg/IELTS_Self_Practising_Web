import { redirect } from "next/navigation";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { ApiError } from "@/lib/api/client";
import { authRedirectPath } from "@/lib/auth-destination";
import { UiText } from "@/lib/i18n/locale-provider";
export default async function TeacherLayout({ children }: {
  children: React.ReactNode;
}) {
  let user;
  try {
    user = userSchema.parse(await serverApiRequest<unknown>("/auth/me"));
  }
  catch (error) {
    if (error instanceof ApiError && error.status === 401)
      redirect(authRedirectPath("/session/restore", "/teacher/tests"));
    throw error;
  }
  if (user.role !== "TEACHER")
    return <section className="empty-state">
      <h1>
        <UiText message="admin.forbidden" />
      </h1>
      <p>
        <UiText message="teacher.only" />
      </p>
    </section>;
  return children;
}
