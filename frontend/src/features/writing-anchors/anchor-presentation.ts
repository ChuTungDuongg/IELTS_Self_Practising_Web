import type { AnchorCoverage, AnchorSet } from "@/lib/api/writing-anchors";

export const bankLabels: Record<AnchorSet["status"], string> = {
  DRAFT: "Bản nháp",
  ACTIVE: "Đang sử dụng",
  RETIRED: "Đã lưu trữ",
};

export const readinessLabels: Record<AnchorCoverage["production_task1"][number]["readiness"], string> = {
  EMPTY: "Chưa có dữ liệu",
  PARTIAL: "Chưa đủ anchor",
  PAIRWISE_USABLE: "Có thể dùng TACS",
  RECOMMENDED_COVERAGE: "Đã đạt mức khuyến nghị",
};

export const criterionNames = {
  cc: "Coherence & Cohesion",
  lr: "Lexical Resource",
  gra: "Grammatical Range & Accuracy",
};

// Presentation only: keep the server's enums, fields and recommendations intact.
const recommendationLabels: Record<string, string> = {
  "Technical minimum: one human anchor at two adjacent whole bands.": "Mức tối thiểu kỹ thuật: mỗi band nguyên trong hai band liền nhau có ít nhất một bài tham chiếu.",
  "Pilot: approximately two anchors per band at 6, 7 and 8 for CC/LR/GRA.": "Mục tiêu ban đầu: khoảng 2 bài ở mỗi Band 6, 7 và 8 cho từng tiêu chí CC, LR và GRA.",
  "Mature: approximately three per band at 5–9, with extra density at 6–8.": "Khi mở rộng: khoảng 3 bài ở mỗi Band 5–9, bổ sung nhiều hơn ở Band 6–8.",
  "Initial practical target: 20–30 carefully human-labelled Task 1 responses; similar Task 2 data later.": "Mục tiêu thực tế ban đầu: 20–30 bài Task 1 được chấm thủ công cẩn thận; bổ sung dữ liệu Task 2 tương tự sau đó.",
  "Recommendations are operational guidance, not IELTS rules or statistical guarantees.": "Các mức khuyến nghị là hướng dẫn xây dựng dữ liệu, không phải quy định IELTS hay bảo đảm thống kê. Bản nháp ít dữ liệu vẫn có thể kích hoạt.",
  "TA labels are evaluation data; Task 2 anchors are for evaluation/future TACS.": "Điểm TA là dữ liệu đánh giá; anchor Task 2 phục vụ đánh giá và khả năng triển khai TACS trong tương lai.",
};

export function recommendationLabel(text: string) {
  return recommendationLabels[text] ?? text;
}
