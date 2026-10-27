import { getAssignmentCalendar, type AssignmentCalendar } from "@/lib/api/assignment-scheduling";
export type CalendarEvent = AssignmentCalendar["items"][number];
export const eventKey = (event: CalendarEvent) => `${event.assignment_id}:${event.kind}:${event.at}`;

/** Fetch every bounded page for one visible range, atomically and with cancellation. */
export async function loadCalendarEvents(classroomId: string, start: string, end: string, signal: AbortSignal) {
  const events: CalendarEvent[] = [];
  let total: number | undefined;
  do {
    signal.throwIfAborted();
    const page = await getAssignmentCalendar(classroomId, start, end, events.length, signal);
    signal.throwIfAborted();
    total ??= page.total;
    if (page.total !== total || page.items.length !== Math.min(50, total - events.length)) throw new Error("Calendar changed while loading");
    events.push(...page.items);
  } while (events.length < total);
  if (new Set(events.map(eventKey)).size !== total) throw new Error("Calendar changed while loading");
  return events;
}
