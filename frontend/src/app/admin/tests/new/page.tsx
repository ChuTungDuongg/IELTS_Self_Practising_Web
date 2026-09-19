import { PageHeading } from "@/components/ui/page-heading";
import { NewTestForm } from "@/features/test-builder/new-test-form";

export default function NewTestPage() {
  return (
    <>
      <PageHeading eyebrow="Builder · New test" title="Create a test" description="Start with the essentials. A logical test and its first editable draft version will be created together." />
      <NewTestForm />
    </>
  );
}
