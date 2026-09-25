"use client";

import Link from "next/link";
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

type HistoryMode = "skill" | "test" | "mock";

export function AttemptHistoryList({ initialHistory }: { initialHistory: HistoryResponse }) {
  const router = useRouter();
  const [mode, setMode] = useState<HistoryMode>("skill");
  const [deletedAttemptIds, setDeletedAttemptIds] = useState<Set<string>>(() => new Set());
  const [deletedSessionIds, setDeletedSessionIds] = useState<Set<string>>(() => new Set());
  const [hiddenVersions, setHiddenVersions] = useState<{ source: HistoryResponse; ids: Set<string> } | null>(null);
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [selectedSession, setSelectedSession] = useState<MockHistoryGroup | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<HistoryGroup | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  const deletedVersionIds = hiddenVersions?.source === initialHistory ? hiddenVersions.ids : new Set<string>();
  const items = initialHistory.items.filter((item) =>
    !deletedAttemptIds.has(item.attempt_id)
    && (item.test_session_id
      ? !deletedSessionIds.has(item.test_session_id)
      : !deletedVersionIds.has(item.test_version_id)),
  );
  const sessions = (initialHistory.sessions ?? []).filter((session) => !deletedSessionIds.has(session.session_id));
  const groups = initialHistory.groups.filter((group) => !deletedVersionIds.has(group.test_version_id));

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
        caught instanceof ApiError ? caught.message : "The history entry could not be deleted. Please try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <div className="history-tabs" role="tablist" aria-label="History view">
        {(["skill", "test", "mock"] as const).map((view) => (
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
            {view === "skill" ? "By skill" : view === "test" ? "By test" : "By mock test"}
          </button>
        ))}
      </div>

      {mode === "skill" ? (
        <div id="history-by-skill" role="tabpanel" aria-labelledby="history-tab-skill">
          {items.length ? (
            <ul className="history-list">
              {items.map((item) => (
                <HistoryRow key={item.attempt_id} item={item} pending={pending} onDelete={chooseAttempt} />
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={<HistoryIcon className="size-6" />}
              title="No practice attempts yet"
              description="Start a published Reading, Listening or Writing test and your saved progress will appear here."
            />
          )}
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
              title="No standalone test history yet"
              description="Complete Reading, Listening or Writing practice for a published test and results will be grouped here by exact test version."
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
              title="No Full Mock history yet"
              description="Start a Full Mock and its session history will appear here."
            />
          )}
        </div>
      )}

      <ConfirmDialog
        open={selected !== null || selectedSession !== null || selectedGroup !== null}
        title={selectedSession ? "Delete this Full Mock?" : selectedGroup ? "Delete this test history?" : "Delete this attempt?"}
        description={selectedSession
          ? "This permanently deletes this Full Mock session and its Listening, Reading and Writing attempts, including saved answers and review history. The published test itself will not be deleted."
          : selectedGroup
            ? `This will permanently delete all of your standalone Reading, Listening and Writing attempts for ${selectedGroup.test_title}, Version ${selectedGroup.version_number}. Full Mock sessions and the published test will not be deleted.`
            : `${selected?.status === "IN_PROGRESS" || selected?.status === "PAUSED" ? "This attempt is not finalized. " : ""}This will permanently remove this attempt and its saved answers, highlights, flags and activity history. The test itself will not be deleted.`}
        confirmLabel={selectedSession ? "Delete Full Mock" : selectedGroup ? "Delete history" : "Delete attempt"}
        pending={pending}
        errorMessage={error}
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
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string>();

  async function resume() {
    if (resuming) return;
    setResuming(true);
    setResumeError(undefined);
    try {
      await resumeAttempt(item.attempt_id);
      router.push(`/attempt/${item.attempt_id}`);
    } catch (caught) {
      setResumeError(caught instanceof ApiError ? caught.message : "This attempt could not be resumed. Please try again.");
      setResuming(false);
    }
  }

  return (
    <li className="history-row">
      <div className="history-record">
        <div className="history-record-topline">
          <ModuleBadge module={item.module} />
          <span>Version {item.version_number}</span>
          {item.test_session_id ? <span className="history-context-badge">Full Mock</span> : null}
        </div>
        <p className="history-record-title">{item.test_title}</p>
        <p className="history-record-date">Started {formatProjectDateTime(item.started_at)}</p>
      </div>
      <div className="history-state">
        <StatusBadge status={item.status} />
        <span className="history-duration">
          {item.status === "PAUSED" && item.timer_mode === "COUNTDOWN"
            ? `Remaining: ${formatDuration(item.remaining_seconds ?? 0)}`
            : item.status === "PAUSED"
              ? `Practice time: ${formatDuration(item.elapsed_seconds ?? 0)}`
              : item.elapsed_seconds === null ? "Time in progress" : formatDuration(item.elapsed_seconds)}
        </span>
        <AttemptScore item={item} />
      </div>
      <div className="history-actions">
        {item.status === "PAUSED" ? (
          <button type="button" className="btn btn-primary" disabled={resuming} onClick={() => void resume()}>
            {resuming ? "Resuming…" : "Resume"}
          </button>
        ) : item.status !== "IN_PROGRESS" && item.review_available !== false ? (
          <Link href={`/review/${item.attempt_id}`} className="btn btn-primary">
            Review
          </Link>
        ) : item.status === "IN_PROGRESS" ? (
          <Link href={`/attempt/${item.attempt_id}`} className="btn btn-primary">
            Continue
          </Link>
        ) : item.test_session_id ? <Link href={`/test-session/${item.test_session_id}`} className="btn btn-secondary">Resume Full Mock</Link> : null}
        {item.test_session_id ? null : <button
          type="button"
          disabled={pending}
          aria-label={`Delete ${item.test_title}`}
          onClick={() => onDelete(item)}
          className="btn btn-danger-ghost"
        >
          Delete
        </button>}
        {resumeError ? <span role="alert" className="history-action-error">{resumeError}</span> : null}
      </div>
    </li>
  );
}

function AttemptScore({ item }: { item: HistoryItem }) {
  if (item.status === "PAUSED") {
    return <span className="history-score history-score-state" data-testid={`history-score-${item.attempt_id}`}>Paused</span>;
  }
  if (item.status === "IN_PROGRESS") {
    return <span className="history-score history-score-state" data-testid={`history-score-${item.attempt_id}`}>In progress</span>;
  }
  if (item.band_score === null) {
    return (
      <span className="history-score history-score-unavailable" data-testid={`history-score-${item.attempt_id}`}>
        {item.module === "WRITING" ? "Not graded" : "Official band unavailable"}
        {item.module !== "WRITING" && item.raw_score !== null && item.max_score !== null ? <small>{item.raw_score} / {item.max_score} correct</small> : null}
      </span>
    );
  }

  return (
    <span className="history-score history-score-result" data-testid={`history-score-${item.attempt_id}`}>
      <span className="history-band-label">Band</span>
      <strong className="history-band-value">{item.band_score.toFixed(1)}</strong>
      {item.module !== "WRITING" ? <small>{item.raw_score === null || item.max_score === null ? "Raw score unavailable" : `${item.raw_score} / ${item.max_score} correct`}</small> : null}
    </span>
  );
}

function HistoryGroupCard({ group, pending, onDelete }: {
  group: HistoryGroup;
  pending: boolean;
  onDelete: (group: HistoryGroup) => void;
}) {
  return (
    <li className="history-group-card">
      <div className="history-group-heading">
        <div>
          <p className="history-record-title">{group.test_title}</p>
          <p className="history-record-date">Version {group.version_number}</p>
        </div>
        <strong>
          {group.overall_band_score === null
            ? "Overall band —"
            : `Overall band ${group.overall_band_score.toFixed(1)}`}
        </strong>
      </div>
      <ul className="history-group-skills">
        <HistoryGroupSkill label="Reading" item={group.reading} />
        <HistoryGroupSkill label="Listening" item={group.listening} />
        <HistoryGroupSkill label="Writing" item={group.writing} />
      </ul>
      <div className="history-group-footer">
        <button type="button" className="btn btn-danger-ghost" disabled={pending} onClick={() => onDelete(group)}>
          Delete test history
        </button>
      </div>
    </li>
  );
}

function HistoryGroupSkill({ label, item }: { label: string; item: HistoryItem | null }) {
  return (
    <li className="history-group-skill">
      <span>{label}</span>
      <span>{!item ? "—" : item.band_score === null ? label === "Writing" ? "Not graded" : "—" : item.band_score.toFixed(1)}</span>
      {item && item.review_available !== false ? (
        <Link href={`/review/${item.attempt_id}`} className="btn btn-secondary">
          Review {label}
        </Link>
      ) : (
        <span>No finalized attempt</span>
      )}
    </li>
  );
}

function MockSessionCard({ session, pending, onDelete }: {
  session: MockHistoryGroup;
  pending: boolean;
  onDelete: (session: MockHistoryGroup) => void;
}) {
  return (
    <li className="history-group-card history-session-card">
      <div className="history-group-heading">
        <div>
          <p className="history-session-kicker">Full Mock</p>
          <p className="history-record-title">{session.test_title}</p>
          <p className="history-record-date">Version {session.version_number}</p>
        </div>
        <strong>
          {session.status === "COMPLETED"
            ? `Overall band ${session.overall_band_score?.toFixed(1) ?? "—"}`
            : session.status === "ABANDONED" ? "Abandoned" : "In progress"}
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
            Resume Full Mock
          </Link>
        ) : null}
        <button type="button" className="btn btn-danger-ghost" disabled={pending} onClick={() => onDelete(session)}>
          Delete Full Mock
        </button>
      </div>
    </li>
  );
}
