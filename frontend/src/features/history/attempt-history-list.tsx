"use client";

import Link from "next/link";
import type { TranslationKey } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { HistoryIcon } from "@/components/ui/icons";
import { ModuleBadge } from "@/components/ui/module-badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatDuration } from "@/features/exam/timer";
import { deleteAttempt, resumeAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { deleteStandaloneTestHistory, type HistoryGroup, type HistoryItem, type HistoryResponse, type MockHistoryGroup } from "@/lib/api/history";
import { deleteTestSession } from "@/lib/api/test-sessions";
import { formatProjectDateTime } from "@/lib/date-time";
import { moduleTranslationKeys, statusTranslationKeys } from "@/lib/i18n/translations";
import { accuracyLabel, focusedUnitLabel } from "@/features/exam/focused-attempt";

type HistoryMode = "skill" | "focused" | "test" | "mock";

export function AttemptHistoryList({ initialHistory }: { initialHistory: HistoryResponse }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [mode, setMode] = useState<HistoryMode>("skill");
  const [deletedAttemptIds, setDeletedAttemptIds] = useState<Set<string>>(() => new Set());
  const [deletedSessionIds, setDeletedSessionIds] = useState<Set<string>>(() => new Set());
  const [hiddenVersions, setHiddenVersions] = useState<{ source: HistoryResponse; ids: Set<string> } | null>(null);
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [selectedSession, setSelectedSession] = useState<MockHistoryGroup | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<HistoryGroup | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | { message: TranslationKey }>();

  const deletedVersionIds = hiddenVersions?.source === initialHistory ? hiddenVersions.ids : new Set<string>();
  const items = initialHistory.items.filter((item) =>
    !deletedAttemptIds.has(item.attempt_id)
    && (item.test_session_id
      ? !deletedSessionIds.has(item.test_session_id)
      : !deletedVersionIds.has(item.test_version_id)),
  );
  const sessions = (initialHistory.sessions ?? []).filter((session) => !deletedSessionIds.has(session.session_id));
  const groups = initialHistory.groups.filter((group) => !deletedVersionIds.has(group.test_version_id));
  const skillItems = items.filter((item) => item.scope !== "FOCUSED_UNIT");
  const focusedItems = items.filter((item) => item.scope === "FOCUSED_UNIT");

  function chooseAttempt(item: HistoryItem) {
    setSelected(item);
    setSelectedSession(null);
    setSelectedGroup(null);
    setError(undefined);
  }

  function chooseSession(session: MockHistoryGroup) {
    setSelectedSession(session);
    setSelected(null);
    setSelectedGroup(null);
    setError(undefined);
  }

  function chooseGroup(group: HistoryGroup) {
    setSelectedGroup(group);
    setSelected(null);
    setSelectedSession(null);
    setError(undefined);
  }

  function cancelDelete() {
    if (pending) return;
    setSelected(null);
    setSelectedSession(null);
    setSelectedGroup(null);
    setError(undefined);
  }

  async function confirmDelete() {
    if ((!selected && !selectedSession && !selectedGroup) || pending) return;
    setPending(true);
    setError(undefined);
    try {
      if (selectedSession) {
        await deleteTestSession(selectedSession.session_id);
        setDeletedSessionIds((current) => new Set(current).add(selectedSession.session_id));
      } else if (selectedGroup) {
        await deleteStandaloneTestHistory(selectedGroup.test_version_id);
        setHiddenVersions((current) => ({
          source: initialHistory,
          ids: new Set(current?.source === initialHistory ? current.ids : []).add(selectedGroup.test_version_id),
        }));
      } else if (selected) {
        await deleteAttempt(selected.attempt_id);
        setDeletedAttemptIds((current) => new Set(current).add(selected.attempt_id));
      }
      setSelected(null);
      setSelectedSession(null);
      setSelectedGroup(null);
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : { message: "history.deleteFailed" },
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <div className="history-tabs" role="tablist" aria-label={t("history.view")}>
        {(["skill", "focused", "test", "mock"] as const).map((view) => (
          <button
            key={view}
            type="button"
            id={`history-tab-${view}`}
            role="tab"
            aria-selected={mode === view}
            aria-controls={`history-by-${view}`}
            className={mode === view ? "btn btn-primary" : "btn btn-secondary"}
            onClick={() => setMode(view)}
          >
            {view === "skill" ? t("history.bySkill") : view === "focused" ? t("history.focused") : view === "test" ? t("history.byTest") : t("history.byMock")}
          </button>
        ))}
      </div>

      {mode === "skill" ? (
        <div id="history-by-skill" role="tabpanel" aria-labelledby="history-tab-skill">
          {skillItems.length ? (
            <ul className="history-list">
              {skillItems.map((item) => (
                <HistoryRow key={item.attempt_id} item={item} pending={pending} onDelete={chooseAttempt} />
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={<HistoryIcon className="size-6" />}
              title={t("history.emptySkill")}
              description={t("history.emptySkillDescription")}
            />
          )}
        </div>
      ) : mode === "focused" ? (
        <div id="history-by-focused" role="tabpanel" aria-labelledby="history-tab-focused">
          {focusedItems.length ? <ul className="history-list">
            {focusedItems.map((item) => <HistoryRow key={item.attempt_id} item={item} pending={pending} onDelete={chooseAttempt} />)}
          </ul> : <><EmptyState icon={<HistoryIcon className="size-6" />} title={t("history.emptyFocused")} description={t("history.emptyFocusedDescription")} /><Link href="/practice" className="btn btn-primary m-4">{t("history.openPractice")}</Link></>}
        </div>
      ) : mode === "test" ? (
        <div id="history-by-test" role="tabpanel" aria-labelledby="history-tab-test">
          {groups.length ? (
            <ul className="history-group-grid">
              {groups.map((group) => (
                <HistoryGroupCard key={group.test_version_id} group={group} pending={pending} onDelete={chooseGroup} />
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={<HistoryIcon className="size-6" />}
              title={t("history.emptyTest")}
              description={t("history.emptyTestDescription")}
            />
          )}
        </div>
      ) : (
        <div id="history-by-mock" role="tabpanel" aria-labelledby="history-tab-mock">
          {sessions.length ? (
            <ul className="history-group-grid">
              {sessions.map((session) => (
                <MockSessionCard key={session.session_id} session={session} pending={pending} onDelete={chooseSession} />
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={<HistoryIcon className="size-6" />}
              title={t("history.emptyMock")}
              description={t("history.emptyMockDescription")}
            />
          )}
        </div>
      )}

      <ConfirmDialog
        open={selected !== null || selectedSession !== null || selectedGroup !== null}
        title={selectedSession ? t("history.deleteMockTitle") : selectedGroup ? t("history.deleteGroupTitle") : t("history.deleteTitle")}
        description={selectedSession
          ? t("history.mockDescription")
          : selectedGroup
            ? t("history.groupDescription", { title: selectedGroup.test_title, number: selectedGroup.version_number })
            : `${selected?.status === "IN_PROGRESS" || selected?.status === "PAUSED" ? t("history.notFinalized") : ""}${t("history.attemptDescription")}`}
        confirmLabel={selectedSession ? t("history.deleteMock") : selectedGroup ? t("history.deleteHistory") : t("history.deleteAttempt")}
        pending={pending}
        errorMessage={typeof error === "string" ? error : error ? t(error.message) : undefined}
        onCancel={cancelDelete}
        onConfirm={() => void confirmDelete()}
      />
    </>
  );
}

function HistoryRow({
  item,
  pending,
  onDelete,
}: {
  item: HistoryItem;
  pending: boolean;
  onDelete: (item: HistoryItem) => void;
}) {
  const router = useRouter();
  const { t } = useTranslation();
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | { message: TranslationKey }>();

  async function resume() {
    if (resuming) return;
    setResuming(true);
    setResumeError(undefined);
    try {
      await resumeAttempt(item.attempt_id);
      router.push(`/attempt/${item.attempt_id}`);
    } catch (caught) {
      setResumeError(caught instanceof ApiError ? caught.message : { message: "history.resumeFailed" });
      setResuming(false);
    }
  }

  return (
    <li className="history-row">
      <div className="history-record">
        <div className="history-record-topline">
          <ModuleBadge module={item.module} label={t(moduleTranslationKeys[item.module])} />
          {item.scope === "FOCUSED_UNIT" ? <span className="history-context-badge">{focusedUnitLabel({ scope: item.scope, focused_unit: item.focused_unit ? { ...item.focused_unit, title: null } : null }, t) ?? t("history.focused")}</span> : null}
          <span>{t("common.versionNumber", { number: item.version_number })}</span>
          {item.test_session_id ? <span className="history-context-badge">{t("history.fullMock")}</span> : null}
        </div>
        <p className="history-record-title">{item.test_title}</p>
        {item.scope === "FOCUSED_UNIT" && item.focused_unit?.title ? <p className="history-record-date">{item.focused_unit.title}</p> : null}
        <p className="history-record-date">{t("history.started", { date: formatProjectDateTime(item.started_at) })}</p>
      </div>
      <div className="history-state">
        <StatusBadge status={item.status} label={t(statusTranslationKeys[item.status])} />
        <span className="history-duration">
          {item.status === "PAUSED" && item.timer_mode === "COUNTDOWN"
            ? t("history.remaining", { time: formatDuration(item.remaining_seconds ?? 0) })
            : item.status === "PAUSED"
              ? t("history.practiceTime", { time: formatDuration(item.elapsed_seconds ?? 0) })
              : item.elapsed_seconds === null ? t("history.timeProgress") : formatDuration(item.elapsed_seconds)}
        </span>
        <AttemptScore item={item} />
      </div>
      <div className="history-actions">
        {item.status === "PAUSED" ? (
          <button type="button" className="btn btn-primary" disabled={resuming} onClick={() => void resume()}>
            {resuming ? t("history.resumePending") : t("history.resume")}
          </button>
        ) : item.status !== "IN_PROGRESS" && item.review_available !== false ? (
          <Link href={`/review/${item.attempt_id}`} className="btn btn-primary">
            {t("common.review")}
          </Link>
        ) : item.status === "IN_PROGRESS" ? (
          <Link href={`/attempt/${item.attempt_id}`} className="btn btn-primary">
            {t("common.continue")}
          </Link>
        ) : item.test_session_id ? <Link href={`/test-session/${item.test_session_id}`} className="btn btn-secondary">{t("history.resumeMock")}</Link> : null}
        {item.test_session_id ? null : <button
          type="button"
          disabled={pending}
          aria-label={t("history.deleteNamed", { title: item.test_title })}
          onClick={() => onDelete(item)}
          className="btn btn-danger-ghost"
        >
          {t("history.delete")}
        </button>}
        {resumeError ? <span role="alert" className="history-action-error">{typeof resumeError === "string" ? resumeError : resumeError ? t(resumeError.message) : undefined}</span> : null}
      </div>
    </li>
  );
}

function AttemptScore({ item }: { item: HistoryItem }) {
  const { t } = useTranslation();
  if (item.status === "PAUSED") {
    return <span className="history-score history-score-state" data-testid={`history-score-${item.attempt_id}`}>{t("history.paused")}</span>;
  }
  if (item.status === "IN_PROGRESS") {
    return <span className="history-score history-score-state" data-testid={`history-score-${item.attempt_id}`}>{t("history.progress")}</span>;
  }
  if (item.scope === "FOCUSED_UNIT") {
    return <span className="history-score history-score-result" data-testid={`history-score-${item.attempt_id}`}>
      {item.module === "WRITING" ? item.task_score == null ? t("history.notGraded") : t("history.taskScore", { score: item.task_score.toFixed(1) }) : <>
        <strong>{t("history.correct", { raw: item.raw_score ?? "—", max: item.max_score ?? "—" })}</strong>
        <small>{accuracyLabel(item.raw_score, item.max_score, t)}</small>
      </>}
    </span>;
  }
  if (item.band_score === null) {
    return (
      <span className="history-score history-score-unavailable" data-testid={`history-score-${item.attempt_id}`}>
        {item.module === "WRITING" ? t("history.notGraded") : t("history.officialUnavailable")}
        {item.module !== "WRITING" && item.raw_score !== null && item.max_score !== null ? <small>{t("history.correct", { raw: item.raw_score, max: item.max_score })}</small> : null}
      </span>
    );
  }

  return (
    <span className="history-score history-score-result" data-testid={`history-score-${item.attempt_id}`}>
      <span className="history-band-label">{t("history.band")}</span>
      <strong className="history-band-value">{item.band_score.toFixed(1)}</strong>
      {item.module !== "WRITING" ? <small>{item.raw_score === null || item.max_score === null ? t("history.rawUnavailable") : t("history.correct", { raw: item.raw_score, max: item.max_score })}</small> : null}
    </span>
  );
}

function HistoryGroupCard({ group, pending, onDelete }: {
  group: HistoryGroup;
  pending: boolean;
  onDelete: (group: HistoryGroup) => void;
}) {
  const { t } = useTranslation();
  return (
    <li className="history-group-card">
      <div className="history-group-heading">
        <div>
          <p className="history-record-title">{group.test_title}</p>
          <p className="history-record-date">{t("common.versionNumber", { number: group.version_number })}</p>
        </div>
        <strong>
          {group.overall_band_score === null
            ? t("history.overallEmpty")
            : t("history.overall", { score: group.overall_band_score.toFixed(1) })}
        </strong>
      </div>
      <ul className="history-group-skills">
        <HistoryGroupSkill label="Reading" item={group.reading} />
        <HistoryGroupSkill label="Listening" item={group.listening} />
        <HistoryGroupSkill label="Writing" item={group.writing} />
      </ul>
      <div className="history-group-footer">
        <button type="button" className="btn btn-danger-ghost" disabled={pending} onClick={() => onDelete(group)}>
          {t("history.deleteGroup")}
        </button>
      </div>
    </li>
  );
}

function HistoryGroupSkill({ label, item }: { label: string; item: HistoryItem | null }) {
  const { t } = useTranslation();
  return (
    <li className="history-group-skill">
      <span>{t(label === "Reading" ? "common.reading" : label === "Listening" ? "common.listening" : "common.writing")}</span>
      <span>{!item ? "—" : item.band_score === null ? label === "Writing" ? t("history.notGraded") : "—" : item.band_score.toFixed(1)}</span>
      {item && item.review_available !== false ? (
        <Link href={`/review/${item.attempt_id}`} className="btn btn-secondary">
          {t("history.reviewSkill", { skill: t(label === "Reading" ? "common.reading" : label === "Listening" ? "common.listening" : "common.writing") })}
        </Link>
      ) : (
        <span>{t("history.noFinal")}</span>
      )}
    </li>
  );
}

function MockSessionCard({ session, pending, onDelete }: {
  session: MockHistoryGroup;
  pending: boolean;
  onDelete: (session: MockHistoryGroup) => void;
}) {
  const { t } = useTranslation();
  return (
    <li className="history-group-card history-session-card">
      <div className="history-group-heading">
        <div>
          <p className="history-session-kicker">{t("history.fullMock")}</p>
          <p className="history-record-title">{session.test_title}</p>
          <p className="history-record-date">{t("common.versionNumber", { number: session.version_number })}</p>
        </div>
        <strong>
          {session.status === "COMPLETED"
            ? t("history.overall", { score: session.overall_band_score?.toFixed(1) ?? "—" })
            : session.status === "ABANDONED" ? t("common.abandoned") : t("common.inProgress")}
        </strong>
      </div>
      <ul className="history-group-skills">
        <HistoryGroupSkill label="Listening" item={session.listening} />
        <HistoryGroupSkill label="Reading" item={session.reading} />
        <HistoryGroupSkill label="Writing" item={session.writing} />
      </ul>
      <div className="history-group-footer">
        {session.status === "IN_PROGRESS" ? (
          <Link href={`/test-session/${session.session_id}`} className="btn btn-primary">
            {t("history.resumeMock")}
          </Link>
        ) : null}
        <button type="button" className="btn btn-danger-ghost" disabled={pending} onClick={() => onDelete(session)}>
          {t("history.deleteMock")}
        </button>
      </div>
    </li>
  );
}
