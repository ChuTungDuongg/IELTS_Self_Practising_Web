import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { getAdminUser } from "@/lib/api/admin";
import { serverApiRequest } from "@/lib/api/server-client";
import { formatProjectDateTime } from "@/lib/date-time";
import { AdminUserActions } from "@/features/auth/admin-user-actions";

export const dynamic = "force-dynamic";

export default async function AdminUserPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = await params;
  const detail = await getAdminUser(userId, serverApiRequest).catch(() => null);
  if (!detail) notFound();
  return <>
    <PageHeading eyebrow="User learning record" title={detail.user.display_name} description={`${detail.user.email} · ${detail.user.role} · ${detail.user.is_active ? "Active" : "Inactive"}`} action={<AdminUserActions userId={detail.user.id} role={detail.user.role} isActive={detail.user.is_active} />} />
    <section className="admin-stat-grid"><AdminDetail label="Attempts" value={detail.history.total} /><AdminDetail label="Finalized" value={detail.analytics.total_finalized_attempts} /><AdminDetail label="Full Mocks" value={detail.analytics.completed_full_mocks} /><AdminDetail label="Last login" value={detail.user.last_login_at ? formatProjectDateTime(detail.user.last_login_at) : "Never"} /></section>
    <section className="admin-users surface-card profile-card"><h2 className="section-title">Profile</h2><div className="profile-grid">
      <ProfileDetail label="Phone" value={detail.user.phone_number} />
      <ProfileDetail label="Date of birth" value={detail.user.date_of_birth} />
      <ProfileDetail label="Country" value={detail.user.country} />
      <ProfileDetail label="City" value={detail.user.city} />
      <ProfileDetail label="Occupation" value={detail.user.occupation} />
      <ProfileDetail label="Institution" value={detail.user.institution} />
      <ProfileDetail label="Overall target band" value={detail.user.target_band} />
      <ProfileDetail label="Listening target band" value={detail.user.target_listening_band} />
      <ProfileDetail label="Reading target band" value={detail.user.target_reading_band} />
      <ProfileDetail label="Writing target band" value={detail.user.target_writing_band} />
      <ProfileDetail label="Speaking target band" value={detail.user.target_speaking_band} />
      <ProfileDetail label="Target test date" value={detail.user.target_test_date} />
      <ProfileDetail label="Bio" value={detail.user.bio} />
    </div></section>
    <section className="admin-users surface-card"><h2 className="section-title">Attempt history</h2>{detail.history.items.length ? <div className="admin-user-list">{detail.history.items.map((attempt) => <div key={attempt.attempt_id} className="admin-user-row"><span><strong>{attempt.test_title}</strong><small>Version {attempt.version_number}</small></span><span>{attempt.module}</span><span>{attempt.status}</span><span>{attempt.band_score ?? "—"}</span></div>)}</div> : <p className="notice">This user has no attempts.</p>}</section>
  </>;
}

function AdminDetail({ label, value }: { label: string; value: string | number }) {
  return <article className="analytics-metric"><span>{label}</span><strong>{value}</strong></article>;
}

function ProfileDetail({ label, value }: { label: string; value: string | number | null }) {
  return <div className="profile-detail"><span>{label}</span><strong>{value === null || value === "" ? "Not provided" : value}</strong></div>;
}
