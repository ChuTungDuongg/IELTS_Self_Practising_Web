"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowIcon, LibraryIcon, PlusIcon, SearchIcon } from "@/components/ui/icons";
import { useLocale } from "@/lib/i18n/locale-provider";
import type { Classroom, ClassroomInvitation } from "@/lib/api/classrooms";
import { ClassroomForm } from "./classroom-form";
import { InvitationInbox } from "./invitation-inbox";
import { StaffInvitationInbox } from "./lms/staff-management";
import { DirectorySidebar } from "./directory-sidebar";
import "./classroom-directory.css";

const copy = {
  vi: { title: "Lớp học", subtitle: "Quản lý và theo dõi các lớp học bạn đang tham gia hoặc giảng dạy.", create: "Tạo lớp học", close: "Đóng", total: "Tổng số lớp học", teaching: "Lớp bạn giảng dạy", attending: "Lớp bạn tham gia", search: "Tìm lớp học theo tên, mô tả hoặc giáo viên...", all: "Tất cả", active: "Đang hoạt động", archived: "Đã lưu trữ", newest: "Mới nhất", oldest: "Cũ nhất", sort: "Sắp xếp", students: "học viên", teacher: "Giáo viên", created: "Ngày tạo", overview: "Xem tổng quan", enter: "Vào lớp học", empty: "Không tìm thấy lớp học nào.", invitations: "Lời mời", calendar: "Lịch lớp học", previous: "Tháng trước", next: "Tháng sau", calendarUnavailable: "Lịch tổng hợp chưa có sẵn. Mở lịch trong từng lớp để xem hạn nộp.", activity: "Hoạt động gần đây", activityUnavailable: "Hoạt động tổng hợp chưa có sẵn. Xem bảng tin trong từng lớp.", page: "Trang", previousPage: "Trang trước", nextPage: "Trang sau", noDescription: "Chưa có mô tả", unknown: "Chưa có thông tin" },
  en: { title: "Classrooms", subtitle: "Manage and follow the classrooms you teach or attend.", create: "Create classroom", close: "Close", total: "Total classrooms", teaching: "Classrooms you teach", attending: "Classrooms you attend", search: "Search by classroom, description or teacher...", all: "All", active: "Active", archived: "Archived", newest: "Newest", oldest: "Oldest", sort: "Sort", students: "students", teacher: "Teacher", created: "Created", overview: "View overview", enter: "Enter classroom", empty: "No classrooms found.", invitations: "Invitations", calendar: "Classroom calendar", previous: "Previous month", next: "Next month", calendarUnavailable: "A combined calendar is not available. Open a classroom calendar to see deadlines.", activity: "Recent activity", activityUnavailable: "Combined activity is not available. Open a classroom stream to see updates.", page: "Page", previousPage: "Previous page", nextPage: "Next page", noDescription: "No description", unknown: "Not available" },
} as const;
type Filter = "ALL" | Classroom["status"];

export function ClassroomDirectory({ items, invitations, user }: { items: Classroom[]; invitations: ClassroomInvitation[]; user: { id: string; role: string } }) {
  const { locale } = useLocale(), text = copy[locale], router = useRouter();
  const [query, setQuery] = useState(""), [filter, setFilter] = useState<Filter>("ALL"), [sort, setSort] = useState("newest"), [page, setPage] = useState(1), [creating, setCreating] = useState(false), [sideRoom, setSideRoom] = useState(items[0]?.id ?? "");
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (creating && dialog.current && !dialog.current.open) dialog.current.showModal(); }, [creating]);
  const visible = useMemo(() => {
    const term = query.trim().toLocaleLowerCase(locale);
    return items.filter(item => (filter === "ALL" || item.status === filter) && [item.name, item.description, item.teacher_name].some(value => value?.toLocaleLowerCase(locale).includes(term)))
      .sort((a, b) => (sort === "newest" ? -1 : 1) * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()));
  }, [items, query, filter, sort, locale]);
  const pageCount = Math.max(1, Math.ceil(visible.length / 8)), currentPage = Math.min(page, pageCount);
  const teaching = items.filter(item => item.teacher_id === user.id || item.classroom_role === "CO_TEACHER").length;
  const attending = items.filter(item => item.classroom_role === "STUDENT" && item.membership_active === true).length;
  const pending = invitations.filter(item => item.status === "PENDING").length;
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium" });
  const workspace = (item: Classroom) => `${item.teacher_id === user.id ? "/teacher/classrooms" : "/classrooms"}/${item.id}`;
  return <div className="directory-page">
    <header className="directory-header"><div className="directory-heading"><span className="directory-heading-icon"><LibraryIcon width={27} height={27} /></span><div><h1>{text.title}</h1><p>{text.subtitle}</p></div></div>{user.role === "TEACHER" ? <button className="btn btn-primary" onClick={() => setCreating(true)}><PlusIcon width={17} height={17} /> {text.create}</button> : null}</header>
    <div className="directory-invitations"><StaffInvitationInbox />{pending ? <details><summary>{text.invitations} ({pending})</summary><InvitationInbox invitations={invitations} /></details> : null}</div>
    <div className="directory-layout"><div className="directory-main">
      <section className="directory-metrics" aria-label={text.title}><div><span className="directory-metric-icon"><LibraryIcon width={21} height={21} /></span><p><strong>{items.length}</strong><small>{text.total}</small></p></div>{user.role === "TEACHER" ? <div><span className="directory-metric-icon green"><LibraryIcon width={21} height={21} /></span><p><strong>{teaching}</strong><small>{text.teaching}</small></p></div> : null}<div><span className="directory-metric-icon blue"><LibraryIcon width={21} height={21} /></span><p><strong>{attending}</strong><small>{text.attending}</small></p></div></section>
      <div className="directory-controls"><label className="directory-search"><SearchIcon width={18} height={18} /><span className="directory-sr-only">{text.search}</span><input value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} placeholder={text.search} /></label><div className="directory-filters" role="group" aria-label={text.title}>{(["ALL", "ACTIVE", "ARCHIVED"] as const).map(value => <button key={value} type="button" aria-pressed={filter === value} onClick={() => { setFilter(value); setPage(1); }}>{text[value === "ALL" ? "all" : value === "ACTIVE" ? "active" : "archived"]} ({value === "ALL" ? items.length : items.filter(item => item.status === value).length})</button>)}</div><label><span className="directory-sr-only">{text.sort}</span><select value={sort} onChange={event => { setSort(event.target.value); setPage(1); }}><option value="newest">{text.newest}</option><option value="oldest">{text.oldest}</option></select></label></div>
      {visible.length ? <div className="directory-cards">{visible.slice((currentPage - 1) * 8, currentPage * 8).map(item => <article className="directory-card" key={item.id}><div className={`directory-banner directory-banner-${item.id.charCodeAt(0) % 3}`}><span><LibraryIcon width={22} height={22} /></span><strong className={item.status === "ACTIVE" ? "active" : "archived"}>{item.status === "ACTIVE" ? text.active : text.archived}</strong></div><div className="directory-card-body"><h2>{item.name}</h2><p className="directory-description">{item.description || text.noDescription}</p><div className="directory-card-meta"><span>{item.active_member_count == null ? "—" : item.active_member_count} {text.students}</span><span><time dateTime={item.created_at}>{date.format(new Date(item.created_at))}</time><small>{text.created}</small></span></div><p className="directory-teacher"><span>{(item.teacher_name || "?").slice(0, 1).toUpperCase()}</span><span><strong>{item.teacher_name || text.unknown}</strong><small>{text.teacher}</small></span></p><div className="directory-card-actions"><Link className="btn btn-primary" href={`${workspace(item)}/overview`}>{text.overview} <ArrowIcon width={16} height={16} /></Link><Link className="btn btn-secondary" href={workspace(item)}>{text.enter}</Link></div></div></article>)}</div> : <p className="directory-empty">{text.empty}</p>}
      {pageCount > 1 ? <nav className="directory-pagination" aria-label={text.page}><button disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>{text.previousPage}</button><span>{text.page} {currentPage} / {pageCount}</span><button disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>{text.nextPage}</button></nav> : null}
    </div><DirectorySidebar rooms={items} selectedId={sideRoom} onSelect={setSideRoom} workspace={workspace} locale={locale} /></div>
    <dialog ref={dialog} className="directory-dialog" aria-labelledby="directory-create-title" onClose={() => setCreating(false)}><div className="directory-dialog-heading"><h2 id="directory-create-title">{text.create}</h2><button type="button" onClick={() => dialog.current?.close()} aria-label={text.close}>×</button></div><ClassroomForm onCreated={room => { dialog.current?.close(); router.push(`/teacher/classrooms/${room.id}/overview`); }} /></dialog>
  </div>;
}
