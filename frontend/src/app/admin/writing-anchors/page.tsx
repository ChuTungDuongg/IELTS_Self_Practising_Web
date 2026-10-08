import { PageHeading } from "@/components/ui/page-heading";
import { AnchorWorkspace } from "@/features/writing-anchors/anchor-workspace";

export default function WritingAnchorsPage() {
  return <><PageHeading eyebrow="Administration" title="Human Writing anchors" description="Curate administrator-validated responses and four human criterion labels." /><AnchorWorkspace /></>;
}
