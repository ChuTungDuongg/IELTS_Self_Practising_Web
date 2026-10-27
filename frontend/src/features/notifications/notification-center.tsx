"use client";


import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { listNotifications, getUnreadNotificationCount, markNotificationRead, markAllNotificationsRead, type Notification } from "@/lib/api/notifications";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationFunction } from "@/lib/i18n/types";
import { GOVERNANCE_PAGE_SIZE } from "@/lib/api/pagination";
function notificationText(item: Notification, t: TranslationFunction) {
  const name = String(item.payload_json.classroom_name ?? item.payload_json.test_title ?? "");
  if (item.type === "CLASSROOM_INVITED")
    return t("notifications.invited", { name });
  if (item.type === "CLASSROOM_INVITATION_ACCEPTED")
    return t("notifications.accepted", { name });
  if (item.type === "CLASSROOM_INVITATION_DECLINED")
    return t("notifications.declined", { name });
  if (item.type === "CLASSROOM_ARCHIVED")
    return t("notifications.archived", { name });
  if (item.type === "CLASSROOM_ANNOUNCEMENT_PUBLISHED")
    return t("notifications.announcement", { name });
  if (item.type.startsWith("ASSIGNMENT_")) {
    const key = item.type === "ASSIGNMENT_CREATED" ? "notifications.assignmentCreated" : item.type === "ASSIGNMENT_SCHEDULE_CHANGED" ? "notifications.assignmentChanged" : item.type === "ASSIGNMENT_EXTENSION_GRANTED" ? "notifications.assignmentExtension" : item.type === "ASSIGNMENT_OVERDUE" ? "notifications.assignmentOverdue" : "notifications.assignmentDue";
    return t(key, { name: String(item.payload_json.assignment_title ?? "") });
  }
  if (/^TEST_(CLASSROOM|PUBLIC)_(APPROVED|REJECTED)$/.test(item.type)) {
    return t(item.type.endsWith("APPROVED") ? "notifications.approved" : "notifications.rejected", { name, scope: t(item.type.includes("PUBLIC") ? "moderation.public" : "moderation.classroom") });
  }
  return t("notifications.update");
}
function notificationHref(item: Notification) {
  if (item.entity_type === "CLASSROOM_ASSIGNMENT") {
    const room = item.payload_json.classroom_id, assignment = item.payload_json.assignment_id;
    return typeof room === "string" && typeof assignment === "string" ? `/classrooms/${encodeURIComponent(room)}?assignment=${encodeURIComponent(assignment)}` : "/classrooms";
  }
  if (item.entity_type === "CLASSROOM_POST") {
    const classroomId = item.payload_json.classroom_id;
    return typeof classroomId === "string" && classroomId
      ? `/classrooms/${encodeURIComponent(classroomId)}?post=${encodeURIComponent(item.entity_id)}`
      : "/classrooms";
  }
  if (item.entity_type === "INVITATION") return "/classrooms";
  if (item.entity_type === "CLASSROOM") return `/classrooms/${encodeURIComponent(item.entity_id)}`;
  return "/teacher/tests";
}
export function NotificationCenter({ userId }: {
  userId?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [failed, setFailed] = useState(false);
  const [pending, setPending] = useState(false);
  const refresh = useCallback(async () => {
    const [list, count] = await Promise.all([
      listNotifications(undefined, { limit: GOVERNANCE_PAGE_SIZE, offset: 0 }),
      getUnreadNotificationCount(),
    ]);
    setItems(list);
    setHasMore(list.length === GOVERNANCE_PAGE_SIZE);
    setNextOffset(list.length);
    setUnread(count);
    setFailed(false);
  }, []);
  useEffect(() => {
    if (!userId)
      return;
    let disposed = false;
    Promise.all([
      listNotifications(undefined, { limit: GOVERNANCE_PAGE_SIZE, offset: 0 }),
      getUnreadNotificationCount(),
    ]).then(([list, count]) => {
      if (!disposed) {
        setItems(list);
        setHasMore(list.length === GOVERNANCE_PAGE_SIZE);
        setNextOffset(list.length);
        setUnread(count);
      }
    }).catch(() => {
      if (!disposed)
        setFailed(true);
    });
    return () => {
      disposed = true;
    };
  }, [userId]);
  if (!userId)
    return null;
  async function read(id?: string) {
    if (pending)
      return;
    setPending(true);
    try {
      if (id)
        await markNotificationRead(id);
      else
        await markAllNotificationsRead();
      const readAt = new Date().toISOString();
      setItems(current => current.map(item => !id || item.id === id ? { ...item, read_at: item.read_at ?? readAt } : item));
      setUnread(await getUnreadNotificationCount());
      setFailed(false);
    }
    catch {
      setFailed(true);
    }
    finally {
      setPending(false);
    }
  }
  async function loadMore() {
    if (pending)
      return;
    setPending(true);
    try {
      const older = await listNotifications(undefined, { limit: GOVERNANCE_PAGE_SIZE, offset: nextOffset });
      setItems(current => {
        const known = new Set(current.map(item => item.id));
        return [...current, ...older.filter(item => !known.has(item.id))];
      });
      setHasMore(older.length === GOVERNANCE_PAGE_SIZE);
      setNextOffset(current => current + older.length);
      setFailed(false);
    }
    catch {
      setFailed(true);
    }
    finally {
      setPending(false);
    }
  }
  return <div className="notification-center">
    <button type="button" className="btn btn-ghost" aria-label={t("notifications.bell", { count: unread })} aria-expanded={open} onClick={() => {
      setOpen(value => !value);
      if (!open)
        void refresh().catch(() => setFailed(true));
    }}>
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
      </svg>{unread > 0 ? <span>{unread}</span> : null}
    </button>
    {open ? <section className="notification-panel surface-card" aria-label={t("notifications.title")}>
      <div className="flex items-center justify-between gap-2">
        <h2>{t("notifications.title")}</h2>
        <button type="button" className="btn btn-ghost" disabled={pending || unread === 0} onClick={() => void read()}>{t("notifications.readAll")}</button>
      </div>
      {failed ? <p role="alert">{t("governance.error")}</p> : null}
      {items.length ? <ul>{items.map(item => <li key={item.id} className="border-t border-[var(--line)] py-3">
        <p>{notificationText(item, t)}</p>
        <div className="flex gap-2">
          <Link href={notificationHref(item)}>{t("common.open")}</Link>{!item.read_at ? <button type="button" className="btn btn-ghost" disabled={pending} onClick={() => void read(item.id)}>{t("notifications.read")}</button> : null}</div>
      </li>)}</ul> : <p>{t("notifications.empty")}</p>}
      {hasMore ? <button type="button" className="btn btn-ghost" disabled={pending} onClick={() => void loadMore()}>{t("pagination.loadMore")}</button> : null}
    </section> : null}
  </div>;
}
