"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/auth-provider";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { accentLabelKey, accentPresets } from "./accent-palette";
import { usePersonalization } from "./personalization-provider";

export function PersonalizationError() {
  const { error, retry, saving } = usePersonalization();
  const { t } = useTranslation();
  if (!error) return null;
  return <div className="personalization-error" role="alert">
    <p>{t(error === "load" ? "personalization.loadFailed" : "personalization.saveFailed")}</p>
    <button type="button" className="btn btn-secondary" disabled={saving} onClick={retry}>{t("personalization.retry")}</button>
  </div>;
}

export function PersonalizationSettings() {
  const { user, loading: authLoading, sessionError, confirmSession } = useAuth();
  const { accentColor, appearance, locale, loading, saving, canUpdate, setAccentColor, setAppearance, setLocale } = usePersonalization();
  const { t } = useTranslation();
  const router = useRouter();
  useEffect(() => {
    if (!authLoading && !user && !sessionError) router.replace("/login?next=/settings/personalization");
  }, [authLoading, user, sessionError, router]);
  if (sessionError) return <div role="alert"><p>{sessionError}</p><button type="button" className="btn btn-secondary" onClick={() => void confirmSession().catch(() => undefined)}>{t("personalization.retry")}</button></div>;
  if (authLoading || !user) return <p role="status">{t("common.loading")}</p>;
  return <div className="personalization-settings">
    <div className="page-heading"><div><h1>{t("personalization.title")}</h1><p className="page-description">{t("personalization.description")}</p></div></div>
    <PersonalizationError />
    {loading ? <p role="status">{t("personalization.loading")}</p> : null}
    <fieldset className="surface-card personalization-card" disabled={!canUpdate}>
      <legend>{t("personalization.accentColor")}</legend>
      <div className="accent-options">
        {accentPresets.map(accent => <button key={accent} type="button" className="accent-option" aria-label={t(accentLabelKey(accent))} aria-pressed={accentColor === accent} onClick={() => setAccentColor(accent)}>
          <span className="accent-swatch" data-accent={accent.toLowerCase()} aria-hidden="true">{accentColor === accent ? "✓" : ""}</span>
          <span>{t(accentLabelKey(accent))}</span>
        </button>)}
      </div>
      <div className="personalization-preview"><span>{t("personalization.preview")}</span><span className="btn btn-primary">{t("personalization.sectionPreview")}</span></div>
    </fieldset>
    <fieldset className="surface-card personalization-card" disabled={!canUpdate}>
      <legend>{t("personalization.appearance")}</legend>
      <div className="personalization-options">
        <button type="button" className="btn btn-secondary" aria-pressed={appearance === "LIGHT"} onClick={() => setAppearance("LIGHT")}>{t("personalization.light")}</button>
        <button type="button" className="btn btn-secondary" aria-pressed={appearance === "DARK"} onClick={() => setAppearance("DARK")}>{t("personalization.dark")}</button>
      </div>
    </fieldset>
    <fieldset className="surface-card personalization-card" disabled={!canUpdate}>
      <legend>{t("personalization.language")}</legend>
      <div className="personalization-options">
        <button type="button" className="btn btn-secondary" lang="en" aria-pressed={locale === "en"} onClick={() => setLocale("en")}>English</button>
        <button type="button" className="btn btn-secondary" lang="vi" aria-pressed={locale === "vi"} onClick={() => setLocale("vi")}>Tiếng Việt</button>
      </div>
    </fieldset>
    <p className="personalization-save-status" role="status">{saving ? t("personalization.saving") : ""}</p>
  </div>;
}
