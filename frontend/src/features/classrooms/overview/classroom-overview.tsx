"use client";

import Link from "next/link";
import { AnalyticsIcon, CheckIcon, HistoryIcon, LibraryIcon, ReadingIcon } from "@/components/ui/icons";
import type { Classroom, ClassroomAssignment } from "@/lib/api/classrooms";
import type { ClassroomPost } from "@/lib/api/classroom-content";
import type { LearningDashboard } from "@/lib/api/classroom-learning";
import type { AssignmentCalendar } from "@/lib/api/assignment-scheduling";
import { useLocale } from "@/lib/i18n/locale-provider";
import { ClassroomForm } from "../classroom-form";
import { ClassroomMembershipActions } from "../classroom-management";
import type { classroomPermissions } from "../classroom-permissions";
import "./classroom-overview.css";

type Props = {
  classroom: Classroom; permissions: ReturnType<typeof classroomPermissions>; directory: string; workspace: string;
  assignments: ClassroomAssignment[] | null; posts: ClassroomPost[] | null;
  calendar: AssignmentCalendar | null; dashboard: LearningDashboard | null; members?: { user_id: string; display_name: string }[] | null;
};

export function ClassroomOverview({ classroom, permissions, directory, workspace, assignments, posts, calendar, dashboard, members = null }: Props) {
  const { locale } = useLocale();
  const vi = locale === "vi";
  const text = (v: string, e: string) => vi ? v : e;
  const date = (value: string, withTime = false) => new Date(value).toLocaleString(vi ? "vi-VN" : "en-US", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
  const activeAssignments = assignments?.filter(item => item.status === "ACTIVE") ?? null;
  const completed = dashboard ? (dashboard.counts.SUBMITTED_ON_TIME ?? 0) + (dashboard.counts.SUBMITTED_LATE ?? 0) : null;
  // The calendar is authorization-aware and filters archived assignments at the source.
  // When assignment metadata is available, also guard against a stale cross-request result.
  const upcoming = calendar?.items.filter(event => event.kind === "DUE" && (!activeAssignments || activeAssignments.some(item => item.id === event.assignment_id))).slice(0, 3) ?? [];
  const metrics = [
    { label: text("Học viên", "Students"), value: classroom.active_member_count ?? "—", icon: <LibraryIcon /> },
    { label: text("Bài tập", "Assignments"), value: activeAssignments?.length ?? "—", icon: <ReadingIcon /> },
    { label: text("Đã nộp hợp lệ", "Accepted submissions"), value: completed ?? "—", icon: <CheckIcon /> },
    { label: text("Nộp muộn", "Late submissions"), value: dashboard?.counts.SUBMITTED_LATE ?? (dashboard ? 0 : "—"), icon: <HistoryIcon /> },
    { label: text("Tỷ lệ hoàn thành", "Completion rate"), value: dashboard?.completion_rate == null ? "—" : `${dashboard.completion_rate.toFixed(1)}%`, icon: <AnalyticsIcon /> },
  ];
  return <div className="room-overview" data-ui>
    <nav className="room-overview-breadcrumb" aria-label={text("Đường dẫn", "Breadcrumb")}><Link href={directory}>{text("Lớp học", "Classrooms")}</Link><span aria-hidden="true">›</span><span aria-current="page">{classroom.name}</span></nav>
    <header className="room-overview-header">
      <div className="room-overview-identity"><span className="room-overview-icon" aria-hidden="true"><LibraryIcon /></span><div><div className="room-overview-title"><h1>{classroom.name}</h1><span className="room-overview-status" data-active={classroom.status === "ACTIVE"}>{classroom.status === "ACTIVE" ? text("Đang hoạt động", "Active") : text("Đã lưu trữ", "Archived")}</span>{permissions.isObserver ? <span className="room-overview-readonly">{text("Chỉ xem", "Read only")}</span> : null}</div><p>{text("Giáo viên", "Teacher")}: {classroom.teacher_name ?? "—"} · {classroom.active_member_count ?? "—"} {text("học viên", "students")} · {text("Tạo ngày", "Created")} {date(classroom.created_at)}</p></div></div>
      <div className="room-overview-actions"><Link className="btn btn-primary" href={workspace}>{permissions.isObserver ? text("Xem lớp", "View classroom") : text("Vào lớp học", "Enter classroom")}</Link>{permissions.canManageClassroom && classroom.status === "ACTIVE" ? <details className="room-overview-edit"><summary className="btn btn-secondary">{text("Chỉnh sửa lớp", "Edit classroom")}</summary><ClassroomForm classroom={classroom} returnTo={`${workspace}/overview`} /></details> : null}{permissions.canManageClassroom ? <details className="room-overview-manage"><summary className="btn btn-secondary">{text("Quản lý", "Manage")}</summary><ClassroomMembershipActions classroom={classroom} isAdmin={permissions.isObserver} canManage={permissions.canManageClassroom} isStaff={permissions.isStaff} /></details> : null}</div>
    </header>
    <div className="room-overview-grid"><div className="room-overview-main">
      <section aria-label={text("Tổng quan lớp học", "Class overview")}><div className="room-overview-metrics">{metrics.map(metric => <div className="room-overview-metric" key={metric.label}><span className="room-overview-metric-icon" aria-hidden="true">{metric.icon}</span><span>{metric.label}</span><strong>{metric.value}</strong></div>)}</div><p className="room-overview-note">{text("Tỷ lệ dựa trên các yêu cầu đủ điều kiện hiện tại.", "Completion uses current eligible requirements.")}</p></section>
      <section className="room-overview-panel"><div className="room-overview-panel-heading"><div><h2>{text("Hoạt động gần đây", "Recent activity")}</h2><p>{text("Các cập nhật mới nhất của lớp.", "Latest classroom updates.")}</p></div><Link href={workspace}>{text("Xem tất cả", "View all")} →</Link></div>
        {posts === null ? <p role="status">{text("Không thể tải hoạt động.", "Activity could not be loaded.")}</p> : posts.length ? <ul className="room-overview-activity">{posts.map(post => <li key={`${post.kind}:${post.id}`}><Link href={post.kind === "ASSIGNMENT_ACTIVITY" ? `${workspace}?assignment=${encodeURIComponent(post.assignment_id ?? post.id)}` : post.kind === "RESOURCE_ACTIVITY" ? `${workspace}#classwork-resource-${encodeURIComponent(post.id)}` : `${workspace}?post=${encodeURIComponent(post.id)}`}><span className="room-overview-item-icon" aria-hidden="true"><ReadingIcon /></span><span><strong>{post.title || post.body}</strong><small>{post.author_name}</small></span><time dateTime={post.published_at ?? post.created_at}>{date(post.published_at ?? post.created_at, true)}</time></Link></li>)}</ul> : <p className="room-overview-empty">{text("Chưa có hoạt động trong các cập nhật gần nhất.", "No published activity in the latest updates.")}</p>}
      </section>
      <section className="room-overview-panel"><div className="room-overview-panel-heading"><div><h2>{text("Tiến độ chung theo kỹ năng", "IELTS skill overview")}</h2><p>{text("Kết quả hợp lệ trong khoảng thời gian phân tích.", "Eligible results in the analytics period.")}</p></div>{permissions.canViewAnalytics ? <Link href={`${workspace}?tab=analytics`}>{text("Xem chi tiết", "View details")} →</Link> : null}</div><div className="room-overview-skills">{["READING", "LISTENING", "WRITING", "SPEAKING"].map(name => { const skill = dashboard?.skills.find(item => item.skill === name); return <div key={name}><span aria-hidden="true">{name[0]}</span><strong>{name[0] + name.slice(1).toLowerCase()}</strong><b>{skill?.average == null ? "—" : skill.average.toFixed(1)}</b><small>{dashboard ? `${skill?.sample_size ?? 0} ${text("kết quả hợp lệ", "eligible results")}` : text("Không có dữ liệu", "Data unavailable")}</small></div>; })}</div></section>
    </div><aside className="room-overview-sidebar">
      <section className="room-overview-panel"><div className="room-overview-panel-heading"><h2>{text("Thông tin lớp học", "Class information")}</h2></div><dl className="room-overview-info"><div><dt>{text("Tên lớp học", "Class name")}</dt><dd>{classroom.name}</dd></div><div><dt>{text("Mô tả", "Description")}</dt><dd>{classroom.description || "—"}</dd></div><div><dt>{text("Giáo viên", "Teacher")}</dt><dd>{classroom.teacher_name ?? "—"}</dd></div><div><dt>{text("Ngày tạo", "Created")}</dt><dd>{date(classroom.created_at)}</dd></div><div><dt>{text("Trạng thái", "Status")}</dt><dd>{classroom.status === "ACTIVE" ? text("Đang hoạt động", "Active") : text("Đã lưu trữ", "Archived")}</dd></div></dl></section>
      <section className="room-overview-panel"><div className="room-overview-panel-heading"><h2>{text("Bài tập sắp đến hạn", "Upcoming assignments")}</h2><Link href={`${workspace}?tab=calendar`}>{text("Xem tất cả", "View all")} →</Link></div>{calendar === null ? <p role="status">{text("Không thể tải lịch.", "Calendar could not be loaded.")}</p> : upcoming.length ? <ul className="room-overview-upcoming">{upcoming.map(event => { const assignment = activeAssignments?.find(item => item.id === event.assignment_id); return <li key={`${event.assignment_id}:${event.at}`}><Link href={`${workspace}?assignment=${encodeURIComponent(event.assignment_id)}`}><span className="room-overview-item-icon" aria-hidden="true"><ReadingIcon /></span><span><strong>{event.title || assignment?.title || assignment?.version?.test_title || text("Bài tập", "Assignment")}</strong><small>{assignment?.target?.module ?? ""}</small></span><time dateTime={event.at}>{date(event.at, true)}</time></Link></li>; })}</ul> : <p className="room-overview-empty">{calendar.total > calendar.items.length ? text("Xem lịch để xem thêm sự kiện.", "See the calendar for more events.") : text("Không có hạn nộp sắp tới trong 90 ngày.", "No deadlines in the next 90 days.")}</p>}</section>
      <section className="room-overview-panel"><div className="room-overview-panel-heading"><h2>{text("Thành viên lớp", "Class members")}</h2>{permissions.canViewRoster ? <Link href={`${workspace}?tab=people`}>{text("Xem tất cả", "View all")} →</Link> : null}</div><div className="room-overview-member"><span>{(classroom.teacher_name ?? "?").slice(0, 1).toUpperCase()}</span><div><strong>{classroom.teacher_name ?? "—"}</strong><small>{text("Giáo viên chủ lớp", "Class owner")}</small></div></div>{permissions.canViewRoster && members === null ? <p role="status">{text("Không thể tải thành viên.", "Members could not be loaded.")}</p> : null}{members?.filter(member => member.user_id !== classroom.teacher_id).map(member => <div className="room-overview-member" key={member.user_id}><span>{member.display_name.slice(0, 1).toUpperCase()}</span><div><strong>{member.display_name}</strong><small>{text("Học viên", "Student")}</small></div></div>)}</section>
    </aside></div>
  </div>;
}
