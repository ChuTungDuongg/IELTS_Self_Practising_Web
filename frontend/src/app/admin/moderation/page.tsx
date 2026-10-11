import Link from "next/link";
import { ModerationFilters } from "@/features/classrooms/moderation-actions";
import { PageHeading } from "@/components/ui/page-heading";
import { listModeration } from "@/lib/api/content-governance";
import { serverApiRequest } from "@/lib/api/server-client";
import { UiText } from "@/lib/i18n/locale-provider";
import { moderationTranslationKeys } from "@/lib/i18n/translations";
import { GOVERNANCE_PAGE_SIZE, pageOffset } from "@/lib/api/pagination";
import { PageNavigation } from "@/features/classrooms/page-navigation";
export const dynamic = "force-dynamic";
export default async function ModerationQueuePage({ searchParams }: {
  searchParams?: Promise<{
    status?: string;
    offset?: string;
  }>;
}) {
  const statuses = ["PENDING", "APPROVED", "REJECTED", "CANCELLED", "REVOKED"] as const;
  const query = await searchParams;
  const requested = query?.status;
  const status = statuses.find(item => item === requested) ?? "PENDING";
  const offset = pageOffset(query?.offset);
  const page = await listModeration(serverApiRequest, status, { limit: GOVERNANCE_PAGE_SIZE + 1, offset });
  const items = page.slice(0, GOVERNANCE_PAGE_SIZE);
  return <>
    <PageHeading title={<UiText message="moderation.title" />} />
    <ModerationFilters status={status} />{items.length ? <div className="test-card-grid">{items.map(item => <article key={item.id} className="surface-card p-5">
      <h2>{item.test_title}</h2>
      <p>
        <UiText message="common.versionNumber" params={{ number: item.version_number ?? "—" }} /> · <UiText message={item.scope === "PUBLIC" ? "moderation.public" : "moderation.classroom"} /> · <UiText message={moderationTranslationKeys[item.status]} />
      </p>
      <Link className="btn btn-secondary mt-3" href={`/admin/moderation/${item.id}`}>
        <UiText message="common.open" />
      </Link>
    </article>)}</div> : <p>
      <UiText message="moderation.empty" />
    </p>}<PageNavigation path={`/admin/moderation?status=${status}`} offset={offset} hasNext={page.length > GOVERNANCE_PAGE_SIZE} /></>;
}
