import { UiText } from "@/lib/i18n/locale-provider";
import { PageHeading } from "@/components/ui/page-heading";
import { NewTestForm } from "@/features/test-builder/new-test-form";

export default function NewTestPage() {
  return (
    <>
      <PageHeading eyebrow={<UiText message="builder.newEyebrow" />} title={<UiText message="builder.createTest" />} description={<UiText message="builder.createDescription" />} />
      <NewTestForm />
    </>
  );
}
