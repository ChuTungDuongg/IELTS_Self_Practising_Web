import { PageHeading } from "@/components/ui/page-heading";
import { AnchorWorkspace } from "@/features/writing-anchors/anchor-workspace";

export default function WritingAnchorsPage() {
  return <div lang="vi">
    <PageHeading eyebrow="Quản trị" title="Kho bài Writing đã chấm bởi người" description="Quản lý các bài Writing đã được chấm thủ công để làm dữ liệu tham chiếu cho hệ thống chấm AI." />
    <AnchorWorkspace />
  </div>;
}
