"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
export function ResourceAction({ action, children, disabled = false, className = "btn btn-secondary", confirm }: {
  action: () => Promise<unknown>;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
  confirm?: { title: string; description: string };
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  async function run() {
    if (pending)
      return;
    setPending(true);
    setError(null);
    try {
      await action();
      setOpen(false);
      router.refresh();
    }
    catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("governance.error"));
    }
    finally {
      setPending(false);
    }
  }
  return <span className="classroom-action">
    <button type="button" className={className} disabled={disabled || pending} onClick={() => confirm ? setOpen(true) : void run()}>{pending ? t("common.working") : children}</button>{error && !open ? <p role="alert" className="notice notice-error">{error}</p> : null}{confirm ? <ConfirmDialog open={open} title={confirm.title} description={confirm.description} confirmLabel={typeof children === "string" ? children : t("common.archive")} pending={pending} errorMessage={error ?? undefined} onCancel={() => setOpen(false)} onConfirm={() => void run()} /> : null}</span>;
}
