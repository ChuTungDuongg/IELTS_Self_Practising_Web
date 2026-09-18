import { PageHeading } from "@/components/ui/page-heading";
import { NewTestForm } from "@/features/test-builder/new-test-form";

export default function NewTestPage() {
  return (
    <>
      <PageHeading title="Create a test" description="A logical test and its first empty draft version will be created together." />
      <NewTestForm />
    </>
  );
}
