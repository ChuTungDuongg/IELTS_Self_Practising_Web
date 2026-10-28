"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Classroom } from "@/lib/api/classrooms";
import { getAssignmentCalendar, type AssignmentCalendar } from "@/lib/api/assignment-scheduling";
import { listFeed, type ClassroomPost } from "@/lib/api/classroom-content";
import { calendarMonth, civilDate, dayKey, moveMonth } from "./scheduling/calendar-dates";

const labels = {
  vi: { choose: "Chọn lớp học", calendar: "Lịch lớp học", activity: "Hoạt động lớp học", previous: "Tháng trước", next: "Tháng sau", loading: "Đang tải...", error: "Không thể tải dữ liệu. Vui lòng mở lớp để thử lại.", emptyDay: "Không có sự kiện trong ngày này.", partialDay: "Không tìm thấy sự kiện ngày này trong phần đang hiển thị.", emptyFeed: "Chưa có hoạt động được xuất bản.", moreEvents: "Chỉ hiển thị 50 sự kiện đầu tiên trong tháng; mở lịch lớp để xem đầy đủ.", moreDay: "Mở lịch lớp để xem thêm sự kiện trong ngày.", scope: "Dữ liệu của lớp đã chọn; không phải tổng hợp tất cả lớp.", viewCalendar: "Xem lịch lớp", viewFeed: "Xem bảng tin", untitled: "Hoạt động lớp học", AVAILABLE: "Bắt đầu", DUE: "Hạn nộp", CUTOFF: "Hạn cuối" },
  en: { choose: "Choose classroom", calendar: "Classroom calendar", activity: "Classroom activity", previous: "Previous month", next: "Next month", loading: "Loading...", error: "Could not load data. Open the classroom to retry.", emptyDay: "No events on this day.", partialDay: "No events for this day in the displayed page.", emptyFeed: "No published activity yet.", moreEvents: "Only the first 50 events in this month are shown; open the classroom calendar for all events.", moreDay: "Open the classroom calendar for more events on this day.", scope: "Data for the selected classroom, not all classrooms.", viewCalendar: "View classroom calendar", viewFeed: "View classroom stream", untitled: "Classroom activity", AVAILABLE: "Available", DUE: "Due", CUTOFF: "Cutoff" },
} as const;

export function DirectorySidebar({ rooms, selectedId, onSelect, workspace, locale }: { rooms: Classroom[]; selectedId: string; onSelect: (id: string) => void; workspace: (room: Classroom) => string; locale: "vi" | "en" }) {
  const text = labels[locale], room = rooms.find(item => item.id === selectedId);
  const [selected, setSelected] = useState(() => dayKey(new Date()));
  const monthKey = selected.slice(0, 7) + "-01", range = calendarMonth(monthKey), today = dayKey(new Date());
  const [calendar, setCalendar] = useState<{ key: string; data?: AssignmentCalendar; error?: boolean }>({ key: "" });
  const [feed, setFeed] = useState<{ key: string; items?: ClassroomPost[]; error?: boolean }>({ key: "" });
  const calendarKey = `${selectedId}:${monthKey}`;
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController(), monthRange = calendarMonth(monthKey);
    void getAssignmentCalendar(selectedId, monthRange.first.toISOString(), monthRange.end.toISOString(), 0, controller.signal)
      .then(data => { if (!controller.signal.aborted) setCalendar({ key: calendarKey, data }); })
      .catch(() => { if (!controller.signal.aborted) setCalendar({ key: calendarKey, error: true }); });
    return () => controller.abort();
  }, [selectedId, monthKey, calendarKey]);
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    void listFeed(selectedId, { status: "PUBLISHED", signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setFeed({ key: selectedId, items: data.items.slice(0, 3) }); })
      .catch(() => { if (!controller.signal.aborted) setFeed({ key: selectedId, error: true }); });
    return () => controller.abort();
  }, [selectedId]);
  const data = calendar.key === calendarKey ? calendar.data : undefined;
  const daily = data?.items.filter(event => dayKey(new Date(event.at)) === selected) ?? [];
  const full = new Intl.DateTimeFormat(locale, { dateStyle: "full" }), month = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }), weekday = new Intl.DateTimeFormat(locale, { weekday: "short" }), dateTime = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  return <aside className="directory-sidebar">
    <section className="directory-side-panel directory-calendar"><h2>{text.calendar}</h2>
      {rooms.length ? <label className="directory-side-select">{text.choose}<select value={selectedId} onChange={event => onSelect(event.target.value)}>{rooms.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}
      <p>{text.scope}</p><div className="directory-calendar-heading"><button type="button" aria-label={text.previous} onClick={() => setSelected(moveMonth(selected, -1))}>‹</button><strong aria-live="polite">{month.format(range.first)}</strong><button type="button" aria-label={text.next} onClick={() => setSelected(moveMonth(selected, 1))}>›</button></div>
      <div className="directory-calendar-grid">{range.days.slice(0, 7).map(day => <span key={dayKey(day)}>{weekday.format(day)}</span>)}{range.days.map(day => { const key = dayKey(day), count = data?.items.filter(event => dayKey(new Date(event.at)) === key).length ?? 0; return <button type="button" key={key} aria-label={`${full.format(day)}${count ? ` · ${count} ${locale === "vi" ? "sự kiện hiển thị" : "displayed events"}` : ""}`} aria-pressed={key === selected} aria-current={key === today ? "date" : undefined} data-adjacent={day.getMonth() !== range.first.getMonth()} data-event={count > 0 || undefined} onClick={() => setSelected(key)}>{day.getDate()}</button>; })}</div>
      <p><strong>{full.format(civilDate(selected))}</strong></p>
      {room ? calendar.key !== calendarKey ? <p role="status">{text.loading}</p> : calendar.error ? <p role="alert">{text.error}</p> : daily.length ? <ul className="directory-side-list">{daily.slice(0, 3).map(event => <li key={`${event.assignment_id}:${event.kind}:${event.at}`}><Link href={`${workspace(room)}?assignment=${encodeURIComponent(event.assignment_id)}`}>{event.title || text.untitled}</Link><small>{text[event.kind]} · {dateTime.format(new Date(event.at))}</small></li>)}</ul> : <p>{data && data.total > data.items.length ? text.partialDay : text.emptyDay}</p> : null}
      {daily.length > 3 ? <p>{text.moreDay}</p> : null}{data && data.total > data.items.length ? <p>{text.moreEvents}</p> : null}
      {room ? <Link className="directory-side-link" href={`${workspace(room)}?tab=calendar`}>{text.viewCalendar} →</Link> : null}
    </section>
    <section className="directory-side-panel"><h2>{text.activity}</h2><p>{room?.name ? `${room.name} · ${text.scope}` : text.scope}</p>{room ? feed.key !== selectedId ? <p role="status">{text.loading}</p> : feed.error ? <p role="alert">{text.error}</p> : feed.items?.length ? <ul className="directory-side-list">{feed.items.map(item => <li key={`${item.kind}:${item.id}`}><Link href={item.kind === "ASSIGNMENT_ACTIVITY" ? `${workspace(room)}?assignment=${encodeURIComponent(item.assignment_id ?? item.id)}` : item.kind === "RESOURCE_ACTIVITY" ? `${workspace(room)}#classwork-resource-${encodeURIComponent(item.id)}` : `${workspace(room)}?post=${encodeURIComponent(item.id)}`}>{item.title || item.body || text.untitled}</Link><small>{item.author_name} · {dateTime.format(new Date(item.published_at || item.created_at))}</small></li>)}</ul> : <p>{text.emptyFeed}</p> : null}{room ? <Link className="directory-side-link" href={`${workspace(room)}?tab=stream`}>{text.viewFeed} →</Link> : null}</section>
  </aside>;
}
