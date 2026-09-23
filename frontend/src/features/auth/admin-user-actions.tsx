"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { updateAdminUser } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";

export function AdminUserActions({
  userId,
  role,
  isActive,
}: {
  userId: string;
  role: "USER" | "ADMIN";
  isActive: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function update(change: { role?: "USER" | "ADMIN"; is_active?: boolean }) {
    setPending(true);
    setError(null);
    try {
      await updateAdminUser(userId, change);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The user could not be updated.");
    } finally {
      setPending(false);
    }
  }

  return <div className="admin-user-actions" aria-label="User administration">
    <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => void update({ role: role === "ADMIN" ? "USER" : "ADMIN" })}>
      {role === "ADMIN" ? "Demote to User" : "Promote to Admin"}
    </button>
    <button type="button" className="btn btn-ghost" disabled={pending} onClick={() => void update({ is_active: !isActive })}>
      {isActive ? "Deactivate account" : "Reactivate account"}
    </button>
    {error ? <p role="alert" className="notice">{error}</p> : null}
  </div>;
}
