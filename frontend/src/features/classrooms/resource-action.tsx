"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { useTranslation } from "@/lib/i18n/locale-provider";
export function ResourceAction({ action, children, disabled = false, className = "btn btn-secondary" }: {
  action: () => Promise<unknown>;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    if (pending)
      return;
    setPending(true);
    setError(null);
    try {
      await action();
      router.refresh();
    }
    catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("governance.error"));
    }
    finally {
      setPending(false);
    }
  }
  return <span>
    <button type="button" className={className} disabled={disabled || pending} onClick={() => void run()}>{children}</button>{error ? <p role="alert" className="notice notice-error">{error}</p> : null}</span>;
}
