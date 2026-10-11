"use client";

import { useState } from "react";
import { DraftPreview } from "@/features/test-builder/draft-preview";
import type { BuilderVersion } from "@/lib/api/builder";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
export function ModerationPreview({ version, requestId }: {
  version: BuilderVersion;
  requestId: string;
}) {
  const { t } = useTranslation();
  const [module, setModule] = useState(version.modules[0]?.module_type ?? "READING");
  return <section aria-label={t("moderation.preview")}>
    <h2 className="section-title mt-6">{t("moderation.preview")}</h2>
    <div className="flex gap-2 my-3" role="tablist" aria-label={t("moderation.preview")}>{version.modules.map(item => <button type="button" key={item.id} role="tab" aria-selected={item.module_type === module} onClick={() => setModule(item.module_type)} className="btn btn-secondary">{t(moduleTranslationKeys[item.module_type])}</button>)}</div>
    <DraftPreview key={module} version={version} moduleType={module} backHref={`/admin/moderation/${requestId}`} />
  </section>;
}
