import { NewTestForm } from "@/features/test-builder/new-test-form";
import { PageHeading } from "@/components/ui/page-heading";
import { UiText } from "@/lib/i18n/locale-provider";
export default function TeacherNewTestPage() {
  return <>
    <PageHeading title={<UiText message="builder.createDraft" />} />
    <NewTestForm namespace="teacher" />
  </>;
}
