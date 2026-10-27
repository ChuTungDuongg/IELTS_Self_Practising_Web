"use client";
import { useLocale } from "@/lib/i18n/locale-provider";
const en = {
  title: "Assignments", description: "Create, assign and manage classroom practice. Students can find their assignments here.",
  search: "Search assignments", placeholder: "Search assignments…", clear: "Clear assignment search", filter: "Assignment status",
  all: "All assignments", active: "Active assignments", archived: "Archived assignments", activeDescription: "Practice currently assigned to your students.",
  archiveDescription: "Archived assignments no longer appear as active student work.", count: "assignments", countOne: "assignment", empty: "No assignments yet.", noMatches: "No assignments match this search or filter.",
  new: "Create a new assignment", createDescription: "Choose a test and set up the assignment.", create: "Create assignment", choose: "Choose a test", saved: "Assignment created.",
  details: "View details", close: "Close details", more: "More actions", results: "Results", available: "Available", due: "Due", cutoff: "Cut-off", archivedOn: "Archived", noDates: "No scheduled dates", open: "Active", scheduled: "Scheduled", archive: "Archived", flexible: "Flexible skill selection",
  submitError: "Could not create this assignment. Check the selected target and schedule, then try again.", syncError: "The assignment was created, but the list could not be refreshed. Retry loading; do not submit it again.", retry: "Retry loading", note: "Optional notes / instructions", namePlaceholder: "Assignment title", notePlaceholder: "Add instructions for students…",
};
const vi: Record<keyof typeof en, string> = {
  title: "Bài tập", description: "Tạo, giao và quản lý bài tập cho lớp học. Học viên sẽ thấy bài tập tại đây.",
  search: "Tìm kiếm bài tập", placeholder: "Tìm kiếm bài tập…", clear: "Xóa tìm kiếm bài tập", filter: "Trạng thái bài tập",
  all: "Tất cả bài tập", active: "Bài tập đang hoạt động", archived: "Bài tập đã lưu trữ", activeDescription: "Các bài tập đang được giao cho học viên.",
  archiveDescription: "Các bài tập trong mục này không hiển thị là bài đang hoạt động với học viên.", count: "bài", countOne: "bài", empty: "Chưa có bài tập.", noMatches: "Không có bài tập phù hợp với tìm kiếm hoặc bộ lọc.",
  new: "Tạo bài tập mới", createDescription: "Chọn đề thi và thiết lập thông tin giao bài.", create: "Tạo bài tập", choose: "Chọn đề thi", saved: "Đã tạo bài tập.",
  details: "Xem chi tiết", close: "Đóng chi tiết", more: "Thao tác khác", results: "Kết quả", available: "Mở bài", due: "Hạn nộp", cutoff: "Hạn chót", archivedOn: "Đã lưu trữ", noDates: "Chưa đặt lịch", open: "Đang hoạt động", scheduled: "Chưa mở", archive: "Đã lưu trữ", flexible: "Chọn kỹ năng khi làm bài",
  submitError: "Không thể tạo bài tập. Kiểm tra phạm vi được giao và lịch rồi thử lại.", syncError: "Bài tập đã tạo nhưng chưa tải lại được danh sách. Hãy thử tải lại, không cần tạo lần nữa.", retry: "Thử tải lại", note: "Ghi chú / hướng dẫn (tùy chọn)", namePlaceholder: "Tên bài tập", notePlaceholder: "Thêm hướng dẫn cho học viên…",
};
export function useAssignmentsText() { const { locale } = useLocale(); return { at: (key: keyof typeof en) => (locale === "vi" ? vi : en)[key], locale }; }
