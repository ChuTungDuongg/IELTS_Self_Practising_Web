"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { useAuth } from "@/features/auth/auth-provider";
import { formatProjectDateTime } from "@/lib/date-time";
import { changePassword } from "@/lib/api/auth";
import { getProfile, updateProfile, type Profile, type ProfileUpdate } from "@/lib/api/profile";

const editable = ["display_name", "phone_number", "date_of_birth", "country", "city", "occupation", "institution", "target_band", "target_test_date", "bio"] as const;
type Editable = (typeof editable)[number];
type FormValues = Record<Editable, string>;

function valuesFromProfile(profile: Profile): FormValues {
  return Object.fromEntries(editable.map((key) => [key, profile[key] === null ? "" : String(profile[key])])) as FormValues;
}

export default function ProfilePage() {
  const { user, loading, sessionError, confirmSession } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [values, setValues] = useState<FormValues | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [saving, setSaving] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  useEffect(() => {
    if (!loading && !user && !sessionError) router.replace("/login?next=/profile");
  }, [loading, user, sessionError, router]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    getProfile().then((data) => {
      if (active) { setProfile(data); setValues(valuesFromProfile(data)); setError(null); }
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Profile could not be loaded."); });
    return () => { active = false; };
  }, [user?.id]);

  function field(key: Editable, label: string, type = "text", maxLength?: number) {
    return <label className="field-label" key={key}>{label}<input className="field" type={type} maxLength={maxLength} step={key === "target_band" ? "0.5" : undefined} min={key === "target_band" ? "0" : undefined} max={key === "target_band" ? "9" : undefined} value={values?.[key] ?? ""} onChange={(event) => setValues((current) => current ? { ...current, [key]: event.target.value } : current)} /></label>;
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
      if (key === "target_band") update.target_band = raw ? Number(raw) : null;
      else if (key === "display_name") update.display_name = raw;
      else update[key] = raw || null;
    }
    try {
      const saved = await updateProfile(update);
      setProfile(saved); setValues(valuesFromProfile(saved));
      await confirmSession();
      setSuccess(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Profile could not be saved.");
    } finally { setSaving(false); }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(null); setPasswordSuccess(false);
    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match.");
      return;
    }
    if (newPassword.length < 8 || newPassword.length > 256) {
      setPasswordError("New password must be 8–256 characters.");
      return;
    }
    setChangingPassword(true);
    try {
      await changePassword({ current_password: currentPassword, new_password: newPassword });
      await confirmSession();
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setPasswordSuccess(true);
    } catch (cause) {
      setPasswordError(cause instanceof Error ? cause.message : "Password could not be changed.");
    } finally { setChangingPassword(false); }
  }

  if (sessionError) return <p className="notice" role="alert">{sessionError}</p>;
  if (loading || !user || !profile || !values) return <p className="notice">{error ?? "Loading profile…"}</p>;

  return <>
    <PageHeading eyebrow="Profile" title="Your account" description="Your personal details and IELTS goals are optional. Update them whenever you like." />
    <form className="profile-form" onSubmit={(event) => void save(event)}>
      <section className="surface-card profile-card"><h2 className="section-title">Account information</h2><div className="profile-grid">
        <Detail label="Email" value={profile.email} /><Detail label="Role" value={profile.role} />
        <Detail label="Account status" value={profile.is_active ? "Active" : "Inactive"} />
        <Detail label="Member since" value={formatProjectDateTime(profile.created_at)} />
        <Detail label="Last login" value={profile.last_login_at ? formatProjectDateTime(profile.last_login_at) : "Never"} />
      </div></section>
      <section className="surface-card profile-card"><h2 className="section-title">Personal information</h2><div className="profile-grid">
        {field("display_name", "Display name", "text", 160)}
        {field("phone_number", "Phone", "tel", 32)}
        {field("date_of_birth", "Date of birth", "date")}
        {field("country", "Country", "text", 120)}
        {field("city", "City", "text", 120)}
        {field("occupation", "Occupation", "text", 160)}
        {field("institution", "Institution", "text", 200)}
      </div></section>
      <section className="surface-card profile-card"><h2 className="section-title">IELTS goals</h2><div className="profile-grid">
        {field("target_band", "Target band", "number")}
        {field("target_test_date", "Target test date", "date")}
      </div></section>
      <section className="surface-card profile-card"><h2 className="section-title">About</h2><label className="field-label">Bio<textarea className="textarea-field" maxLength={1000} value={values.bio} onChange={(event) => setValues({ ...values, bio: event.target.value })} /></label></section>
      {error ? <p className="notice" role="alert">{error}</p> : null}
      {success ? <p className="notice" role="status">Profile saved.</p> : null}
      <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save changes"}</button>
    </form>
    <section className="surface-card profile-card profile-security"><h2 className="section-title">Security</h2>
      {profile.has_password ? <form className="profile-form" onSubmit={(event) => void savePassword(event)}>
        <div className="profile-grid">
          <label className="field-label">Current password<input className="field" type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
          <label className="field-label">New password<input className="field" type="password" autoComplete="new-password" minLength={8} maxLength={256} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>
          <label className="field-label">Confirm new password<input className="field" type="password" autoComplete="new-password" minLength={8} maxLength={256} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
        </div>
        {passwordError ? <p className="notice" role="alert">{passwordError}</p> : null}
        {passwordSuccess ? <p className="notice" role="status">Password changed successfully.</p> : null}
        <button type="submit" className="btn btn-primary" disabled={changingPassword}>{changingPassword ? "Changing…" : "Change password"}</button>
      </form> : <p className="notice">This account signs in through Google and does not currently use a local password.</p>}
    </section>
  </>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="profile-detail"><span>{label}</span><strong>{value}</strong></div>;
}
