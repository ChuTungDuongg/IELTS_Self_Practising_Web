import { PageHeading } from "@/components/ui/page-heading";
import { getModeration } from "@/lib/api/content-governance";
import { getBuilderVersion } from "@/lib/api/builder";
import { serverApiRequest } from "@/lib/api/server-client";
import { UiText } from "@/lib/i18n/locale-provider";
import { moderationTranslationKeys } from "@/lib/i18n/translations";
import { ModerationActions } from "@/features/classrooms/moderation-actions";
import { ModerationPreview } from "@/features/classrooms/moderation-preview";
export const dynamic = "force-dynamic";
export default async function ModerationDetailPage({ params }: {
  params: Promise<{
    requestId: string;
  }>;
}) {
  const { requestId } = await params;
  const request = await getModeration(requestId, serverApiRequest);
  const version = await getBuilderVersion(request.test_version_id, serverApiRequest);
  return <>
    <PageHeading title={request.test_title ?? version.test_title} description={<UiText message="moderation.title" />} />
    <p>
      <UiText message={request.scope === "PUBLIC" ? "moderation.public" : "moderation.classroom"} /> · <UiText message={moderationTranslationKeys[request.status]} />
    </p>
    <p>{request.submit_note}</p>
    <p>{request.review_note ?? request.revoke_reason}</p>
    <ModerationActions request={request} />
    <ModerationPreview version={version} requestId={requestId} />
  </>;
}
