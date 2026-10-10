"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { TranslationKey } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useRouter } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { useAuth } from "@/features/auth/auth-provider";
import { formatProjectDateTime } from "@/lib/date-time";
import { changePassword } from "@/lib/api/auth";
import { getProfile, updateProfile, type Profile, type ProfileUpdate } from "@/lib/api/profile";

const bandFields = ["target_listening_band", "target_reading_band", "target_writing_band", "target_speaking_band"] as const;
const editable = ["display_name", "phone_number", "date_of_birth", "country", "city", "occupation", "institution", ...bandFields, "target_test_date", "bio"] as const;
type Editable = (typeof editable)[number];
type FormValues = Record<Editable, string>;

function isBandField(key: Editable): key is (typeof bandFields)[number] {
  return (bandFields as readonly string[]).includes(key);
}

function valuesFromProfile(profile: Profile): FormValues {
  return Object.fromEntries(editable.map((key) => [key, profile[key] === null ? "" : String(profile[key])])) as FormValues;
}

export default function ProfilePage() {
  const { t } = useTranslation();
  const { user, loading, sessionError, confirmSession } = useAuth();
  const userId = user?.id;
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [values, setValues] = useState<FormValues | null>(null);
  const [error, setError] = useState<string | { message: TranslationKey } | null>(null);
  const [success, setSuccess] = useState(false);
  const [saving, setSaving] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | { message: TranslationKey } | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  useEffect(() => {
    if (!loading && !user && !sessionError) router.replace("/login?next=/profile");
  }, [loading, user, sessionError, router]);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    getProfile().then((data) => {
      if (active) { setProfile(data); setValues(valuesFromProfile(data)); setError(null); }
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : { message: "profile.loadFailed" }); });
    return () => { active = false; };
  }, [userId]);

  function field(key: Editable, label: string, type = "text", maxLength?: number) {
    return <label className="field-label" key={key}>{label}<input className="field" type={type} maxLength={maxLength} step={type === "number" ? "0.5" : undefined} min={type === "number" ? "0" : undefined} max={type === "number" ? "9" : undefined} value={values?.[key] ?? ""} onChange={(event) => setValues((current) => current ? { ...current, [key]: event.target.value } : current)} /></label>;
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile || !values) return;
    setSaving(true); setError(null); setSuccess(false);
    const update: ProfileUpdate = {};
    for (const key of editable) {
      const raw = values[key].trim();
      const previous = profile[key] === null ? "" : String(profile[key]);
      if (raw === previous) continue;
      if (isBandField(key)) update[key] = raw ? Number(raw) : null;
      else if (key === "display_name") update.display_name = raw;
      else update[key] = raw || null;
    }
    try {
      const saved = await updateProfile(update);
      setProfile(saved); setValues(valuesFromProfile(saved));
      await confirmSession();
      setSuccess(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : { message: "profile.saveFailed" });
    } finally { setSaving(false); }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(null); setPasswordSuccess(false);
    if (newPassword !== confirmPassword) {
      setPasswordError({ message: "profile.mismatch" });
      return;
    }
    if (newPassword.length < 8 || newPassword.length > 256) {
      setPasswordError({ message: "profile.passwordLength" });
      return;
    }
    setChangingPassword(true);
    try {
      await changePassword({ current_password: currentPassword, new_password: newPassword });
      await confirmSession();
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setPasswordSuccess(true);
    } catch (cause) {
      setPasswordError(cause instanceof Error ? cause.message : { message: "profile.passwordFailed" });
    } finally { setChangingPassword(false); }
  }

  if (sessionError) return <p className="notice" role="alert">{sessionError}</p>;
  if (loading || !user || !profile || !values) return <p className="notice">{error ? typeof error === "string" ? error : t(error.message) : t("profile.loading")}</p>;

  return <>
    <PageHeading eyebrow={t("profile.profile")} title={t("profile.account")} description={t("profile.description")} />
    <form className="profile-form" onSubmit={(event) => void save(event)}>
      <section className="surface-card profile-card"><h2 className="section-title">{t("profile.accountInformation")}</h2><div className="profile-grid">
        <Detail label={t("profile.email")} value={profile.email} /><Detail label={t("profile.role")} value={t(profile.role === "ADMIN" ? "shell.roleAdmin" : "shell.roleUser")} />
        <Detail label={t("profile.status")} value={profile.is_active ? t("profile.active") : t("profile.inactive")} />
        <Detail label={t("profile.memberSince")} value={formatProjectDateTime(profile.created_at)} />
        <Detail label={t("profile.lastLogin")} value={profile.last_login_at ? formatProjectDateTime(profile.last_login_at) : t("profile.never")} />
      </div></section>
      <section className="surface-card profile-card"><h2 className="section-title">{t("profile.personal")}</h2><div className="profile-grid">
        {field("display_name", t("profile.displayName"), "text", 160)}
        {field("phone_number", t("profile.phone"), "tel", 32)}
        {field("date_of_birth", t("profile.birth"), "date")}
        {field("country", t("profile.country"), "text", 120)}
        {field("city", t("profile.city"), "text", 120)}
        {field("occupation", t("profile.occupation"), "text", 160)}
        {field("institution", t("profile.institution"), "text", 200)}
      </div></section>
      <section className="surface-card profile-card"><h2 className="section-title">{t("profile.goals")}</h2>
        <div className="profile-overall-target"><div><span>{t("profile.overall")}</span><strong>{profile.target_band === null ? "—" : profile.target_band.toFixed(1)}</strong></div><p>{t("profile.overallHelp")}</p></div>
        <div className="profile-grid profile-goals-grid">
          {field("target_listening_band", t("profile.listening"), "number")}
          {field("target_reading_band", t("profile.reading"), "number")}
          {field("target_writing_band", t("profile.writing"), "number")}
          {field("target_speaking_band", t("profile.speaking"), "number")}
          {field("target_test_date", t("profile.targetDate"), "date")}
        </div></section>
      <section className="surface-card profile-card"><h2 className="section-title">{t("profile.about")}</h2><label className="field-label">{t("profile.bio")}<textarea className="textarea-field" maxLength={1000} value={values.bio} onChange={(event) => setValues({ ...values, bio: event.target.value })} /></label></section>
      {error ? <p className="notice" role="alert">{typeof error === "string" ? error : error ? t(error.message) : null}</p> : null}
      {success ? <p className="notice" role="status">{t("profile.saved")}</p> : null}
      <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? t("profile.saving") : t("profile.save")}</button>
    </form>
    <section className="surface-card profile-card profile-security"><h2 className="section-title">{t("profile.security")}</h2>
      {profile.has_password ? <form className="profile-form" onSubmit={(event) => void savePassword(event)}>
        <div className="profile-grid">
          <label className="field-label">{t("profile.currentPassword")}<input className="field" type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
          <label className="field-label">{t("profile.newPassword")}<input className="field" type="password" autoComplete="new-password" minLength={8} maxLength={256} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>
          <label className="field-label">{t("profile.confirmPassword")}<input className="field" type="password" autoComplete="new-password" minLength={8} maxLength={256} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
        </div>
        {passwordError ? <p className="notice" role="alert">{typeof passwordError === "string" ? passwordError : passwordError ? t(passwordError.message) : null}</p> : null}
        {passwordSuccess ? <p className="notice" role="status">{t("profile.passwordChanged")}</p> : null}
        <button type="submit" className="btn btn-primary" disabled={changingPassword}>{changingPassword ? t("profile.changing") : t("profile.changePassword")}</button>
      </form> : <p className="notice">{t("profile.googleOnly")}</p>}
    </section>
  </>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="profile-detail"><span>{label}</span><strong>{value}</strong></div>;
}
