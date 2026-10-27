"use client";

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ArrowIcon } from "@/components/ui/icons";
import { scheduleError, useScheduleText } from "./messages";
import { ProgressSummary } from "./progress-summary";
import { useAssignmentProgress } from "./progress-provider";
import { AssignmentTargetSummary } from "../assignment-target";
import { addDays, calendarMonth, civilDate, dayKey, moveMonth, weekStart } from "./calendar-dates";
import { eventKey, loadCalendarEvents, type CalendarEvent } from "./calendar-data";

type View = "month" | "week" | "list";
type Filter = "ALL" | CalendarEvent["kind"];
export function AssignmentCalendarPanel({ classroomId, onOpenAssignment, revision = 0 }: {
  classroomId: string; onOpenAssignment: (id: string) => void; revision?: number | string;
}) {
  const { st, locale } = useScheduleText(), progress = useAssignmentProgress();
  const formats = useMemo(() => ({
    month: new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }),
    full: new Intl.DateTimeFormat(locale, { dateStyle: "full" }),
    short: new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }),
    weekday: new Intl.DateTimeFormat(locale, { weekday: "long" }),
    weekdayShort: new Intl.DateTimeFormat(locale, { weekday: "short" }),
    weekDate: new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric" }),
    timestamp: new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }),
  }), [locale]);
  const date = (value: string) => formats.timestamp.format(new Date(value));
  const [selected, setSelected] = useState(() => dayKey(new Date()));
  const [view, setView] = useState<View>("month"), [filter, setFilter] = useState<Filter>("ALL");
  const [data, setData] = useState<CalendarEvent[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  const [detailFocus, setDetailFocus] = useState(0);
  const [keyboardDate, setKeyboardDate] = useState<string | null>(null);
  const sequence = useRef(0), detail = useRef<HTMLHeadingElement>(null), titleId = useId();
  const month = selected.slice(0, 7) + "-01", range = useMemo(() => calendarMonth(month), [month]);
  const start = range.start.toISOString(), end = range.gridEnd.toISOString();
  useEffect(() => { if (detailFocus) detail.current?.focus({ preventScroll: true }); }, [detailFocus]);
  useEffect(() => { if (keyboardDate) document.getElementById(`${titleId}-${keyboardDate}`)?.focus(); }, [keyboardDate, titleId]);
  useEffect(() => {
    const controller = new AbortController(), current = ++sequence.current;
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      setLoading(true); setError(null); setData([]);
      try {
        const next = await loadCalendarEvents(classroomId, start, end, controller.signal);
        if (!controller.signal.aborted && current === sequence.current) setData(next);
      } catch (caught) { if (!controller.signal.aborted && current === sequence.current) setError(caught); }
      finally { if (!controller.signal.aborted && current === sequence.current) setLoading(false); }
    });
    return () => controller.abort();
  }, [classroomId, start, end, revision, retry]);
  const events = useMemo(() => data.filter(event => filter === "ALL" || event.kind === filter), [data, filter]);
  const assignmentById = useMemo(() => new Map(progress?.assignments.map(item => [item.id, item]) ?? []), [progress?.assignments]);
  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const event of events) { const key = dayKey(new Date(event.at)); const values = map.get(key) ?? []; values.push(event); map.set(key, values); }
    return map;
  }, [events]);
  const monthEvents = events.filter(event => { const at = new Date(event.at); return at >= range.first && at < range.end; });
  const selectedEvents = byDay.get(selected) ?? [], selectedDate = civilDate(selected);
  const week = weekStart(selectedDate), weekDays = Array.from({ length: 7 }, (_, index) => addDays(week, index));
  const monthLabel = formats.month.format(range.first);
  const fullDate = (value: Date) => formats.full.format(value);
  const shortDate = (value: Date) => formats.short.format(value);
  const today = dayKey(new Date());
  function choose(key: string, focusDetails = false) { setSelected(key); if (focusDetails) setDetailFocus(value => value + 1); }
  function navigate(delta: number) { setSelected(value => view === "week" ? dayKey(addDays(civilDate(value), delta * 7)) : moveMonth(value, delta)); }
  function navigateDate(event: KeyboardEvent<HTMLButtonElement>, day: Date) {
    const offset = ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -((day.getDay() + 6) % 7), End: 6 - ((day.getDay() + 6) % 7) } as Record<string, number>)[event.key];
    if (offset === undefined) return;
    event.preventDefault(); const key = dayKey(addDays(day, offset)); choose(key); setKeyboardDate(key);
  }
  function eventList(items: CalendarEvent[]) {
    return items.length ? <ol className="calendar-event-list">{items.map(event => {
      const assignment = assignmentById.get(event.assignment_id);
      return <li key={eventKey(event)} data-kind={event.kind}>
        <strong>{event.title || st("detail")}</strong>
        <p><span>{st(event.kind)}</span> · <time dateTime={event.at}>{date(event.at)}</time></p>
        {assignment?.target ? <AssignmentTargetSummary assignment={assignment} /> : null}
        {!progress?.staff && event.progress ? <ProgressSummary assignmentId={event.assignment_id} value={event.progress} /> : null}
        <button type="button" className="classroom-text-button" onClick={() => onOpenAssignment(event.assignment_id)}>{st("detail")}</button>
      </li>;
    })}</ol> : <p className="classroom-meta">{st("emptyDay")}</p>;
  }
  function dayCells(days: Date[]) {
    return <div className={`calendar-grid${view === "week" ? " calendar-week" : ""}`} role="group" aria-label={view === "week" ? st("week") : monthLabel}>
      {view === "month" ? days.slice(0, 7).map(day => <span key={dayKey(day)} className="calendar-weekday"><abbr title={formats.weekday.format(day)}>{formats.weekdayShort.format(day)}</abbr></span>) : null}
      {days.map(day => {
        const key = dayKey(day), daily = byDay.get(key) ?? [];
        return <div key={key} className="calendar-day" data-adjacent={day.getMonth() !== range.first.getMonth()} data-selected={key === selected}>
          <button id={`${titleId}-${key}`} type="button" className="calendar-date" aria-label={fullDate(day)} aria-pressed={key === selected} aria-current={key === today ? "date" : undefined} onKeyDown={event => navigateDate(event, day)} onClick={() => choose(key)}>{view === "week" ? formats.weekDate.format(day) : day.getDate()}</button>
          {daily.slice(0, 3).map(event => <button type="button" className="calendar-event-chip" key={eventKey(event)} data-kind={event.kind} aria-label={`${event.title || st("detail")} · ${st(event.kind)} · ${date(event.at)}`} title={`${event.title} · ${st(event.kind)} · ${date(event.at)}`} onClick={() => choose(key, true)}>
            <span>{event.title || st("detail")}</span><small>{st(event.kind)}</small>
          </button>)}
          {daily.length > 3 ? <button type="button" className="calendar-more" onClick={() => choose(key, true)}>+{daily.length - 3} <span>{st("moreEvents")}</span></button> : null}
        </div>;
      })}
    </div>;
  }
  return <section className="assignment-calendar" aria-labelledby={titleId} aria-busy={loading}>
    <div className="classroom-section-heading"><div><h2 id={titleId}>{st("calendar")}</h2><p className="classroom-meta">{st("timezone")} · {Intl.DateTimeFormat().resolvedOptions().timeZone}</p></div>
      <div className="calendar-view-switch" role="group" aria-label={st("calendarView")}>{(["month", "week", "list"] as const).map(mode => <button type="button" key={mode} aria-pressed={view === mode} onClick={() => setView(mode)}>{st(mode)}</button>)}</div>
    </div>
    <div className="calendar-layout">
      <div className="calendar-surface">
        <div className="calendar-toolbar"><div className="calendar-period"><button type="button" className="icon-button" aria-label={st(view === "week" ? "previousWeek" : "previousMonth")} onClick={() => navigate(-1)}><ArrowIcon width={18} height={18} style={{ transform: "rotate(180deg)" }} /></button><h3 aria-live="polite">{view === "week" ? `${shortDate(week)} – ${shortDate(addDays(week, 6))}` : monthLabel}</h3><button type="button" className="icon-button" aria-label={st(view === "week" ? "nextWeek" : "nextMonth")} onClick={() => navigate(1)}><ArrowIcon width={18} height={18} /></button></div><button type="button" className="btn btn-secondary" onClick={() => choose(today)}>{st("today")}</button></div>
        <div className="calendar-filter-row"><label className="calendar-filter field-label">{st("eventFilter")}<select className="select-field" value={filter} onChange={event => setFilter(event.target.value as Filter)}>{(["ALL", "AVAILABLE", "DUE", "CUTOFF"] as const).map(kind => <option key={kind} value={kind}>{st(kind === "ALL" ? "allEvents" : kind)}</option>)}</select></label>
        <button type="button" className="classroom-text-button calendar-refresh" disabled={loading} onClick={() => setRetry(value => value + 1)}>{st("refreshCalendar")}</button></div>
        {loading ? <p className="calendar-message" role="status">{st("loadingCalendar")}</p> : error ? <div className="calendar-message"><p role="alert">{scheduleError(error, key => key === "error" ? st("calendarError") : st(key))}</p><button type="button" className="btn btn-secondary" onClick={() => setRetry(value => value + 1)}>{st("retry")}</button></div> : null}
        {view === "list" ? <div className="calendar-agenda">{monthEvents.length ? eventList(monthEvents) : !loading && !error ? <p>{st("emptyCalendar")}</p> : null}</div> : dayCells(view === "week" ? weekDays : range.days)}
      </div>
      <aside className="calendar-details" aria-label={st("dayDetails")}>
        <h3 ref={detail} tabIndex={-1}>{fullDate(selectedDate)}</h3>
        <p className="classroom-meta">{selectedEvents.length} {st("events")}</p>
        {!loading && !error ? eventList(selectedEvents) : null}
        {!loading && !error ? <div className="calendar-summary"><h3>{st("monthSummary")} · {monthLabel}</h3><dl><div><dt>{st("scheduledAssignments")}</dt><dd>{new Set(monthEvents.map(event => event.assignment_id)).size}</dd></div>{(["AVAILABLE", "DUE", "CUTOFF"] as const).map(kind => <div key={kind}><dt>{st(kind)}</dt><dd>{monthEvents.filter(event => event.kind === kind).length}</dd></div>)}</dl></div> : null}
      </aside>
    </div>
  </section>;
}
