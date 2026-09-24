import { z } from "zod";
import type { AttemptResponse } from "@/lib/api/attempts";

const answerEntry = z.object({
  kind: z.literal("answer"),
  value: z.union([z.string(), z.array(z.string())]),
  base_server_revision: z.number().int().nonnegative(),
}).strict();
const writingEntry = z.object({
  kind: z.literal("writing"),
  content: z.string(),
  base_server_revision: z.number().int().nonnegative(),
}).strict();
const draftSchema = z.object({
  schema_version: z.literal(1),
  attempt_id: z.uuid(),
  test_version_id: z.uuid(),
  module: z.enum(["READING", "LISTENING", "WRITING"]),
  updated_at: z.iso.datetime(),
  entries: z.record(z.uuid(), z.discriminatedUnion("kind", [answerEntry, writingEntry])),
}).strict();

type DraftRecord = z.infer<typeof draftSchema>;
type DraftEntry = DraftRecord["entries"][string];
export type DraftMetadata = Pick<AttemptResponse, "attempt_id" | "test_version_id" | "module">;
export type ServerResponse<Value> = { id: string; value: Value; revision: number };
export type RecoveryConflict<Value> = {
  id: string;
  localValue: Value;
  serverValue: Value;
  serverRevision: number;
};

export function draftStorageKey(attemptId: string): string {
  return `ielts:attempt-draft:v1:${attemptId}`;
}

export function clearAttemptDraft(attemptId: string): void {
  try { sessionStorage.removeItem(draftStorageKey(attemptId)); } catch { /* Storage may be unavailable. */ }
}

export function isTerminalAttempt(status: string): boolean {
  return ["SUBMITTED", "AUTO_SUBMITTED", "INTERRUPTED", "ABANDONED"].includes(status);
}

export class ExamDraftStore {
  private readonly key: string;

  constructor(private readonly metadata: DraftMetadata) {
    this.key = draftStorageKey(metadata.attempt_id);
  }

  load(): DraftRecord | null {
    let raw: string | null;
    try {
      raw = sessionStorage.getItem(this.key);
    } catch {
      return null;
    }
    if (!raw) return null;
    try {
      const parsed = draftSchema.parse(JSON.parse(raw));
      if (
        parsed.attempt_id !== this.metadata.attempt_id
        || parsed.test_version_id !== this.metadata.test_version_id
        || parsed.module !== this.metadata.module
        || Object.values(parsed.entries).some((entry) => (
          entry.kind !== (this.metadata.module === "WRITING" ? "writing" : "answer")
        ))
      ) {
        this.clear();
        return null;
      }
      return parsed;
    } catch {
      this.clear();
      return null;
    }
  }

  saveEntry(id: string, value: unknown, baseRevision: number): void {
    const entry = this.metadata.module === "WRITING"
      ? writingEntry.safeParse({ kind: "writing", content: value, base_server_revision: baseRevision })
      : answerEntry.safeParse({ kind: "answer", value, base_server_revision: baseRevision });
    if (!z.uuid().safeParse(id).success || !entry.success) return;
    const record = this.load() ?? this.emptyRecord();
    record.entries[id] = entry.data;
    record.updated_at = new Date().toISOString();
    this.write(record);
  }

  removeEntry(id: string): void {
    const record = this.load();
    if (!record || !(id in record.entries)) return;
    delete record.entries[id];
    if (Object.keys(record.entries).length === 0) this.clear();
    else {
      record.updated_at = new Date().toISOString();
      this.write(record);
    }
  }

  clear(): void {
    clearAttemptDraft(this.metadata.attempt_id);
  }

  reconcile<Value>(serverResponses: ServerResponse<Value>[]): {
    safe: Array<{ id: string; value: Value }>;
    conflicts: Array<RecoveryConflict<Value>>;
  } {
    const record = this.load();
    const safe: Array<{ id: string; value: Value }> = [];
    const conflicts: Array<RecoveryConflict<Value>> = [];
    if (!record) return { safe, conflicts };
    const serverById = new Map(serverResponses.map((response) => [response.id, response]));
    for (const [id, entry] of Object.entries(record.entries)) {
      const server = serverById.get(id);
      if (!server) { this.removeEntry(id); continue; }
      const localValue = this.entryValue(entry) as Value;
      if (JSON.stringify(localValue) === JSON.stringify(server.value)) {
        this.removeEntry(id);
      } else if (server.revision === entry.base_server_revision) {
        safe.push({ id, value: localValue });
      } else {
        conflicts.push({ id, localValue, serverValue: server.value, serverRevision: server.revision });
      }
    }
    return { safe, conflicts };
  }

  private entryValue(entry: DraftEntry): string | string[] {
    return entry.kind === "writing" ? entry.content : entry.value;
  }

  private emptyRecord(): DraftRecord {
    return {
      schema_version: 1,
      attempt_id: this.metadata.attempt_id,
      test_version_id: this.metadata.test_version_id,
      module: this.metadata.module,
      updated_at: new Date().toISOString(),
      entries: {},
    };
  }

  private write(record: DraftRecord): void {
    try { sessionStorage.setItem(this.key, JSON.stringify(record)); } catch { /* Network autosave still works. */ }
  }
}
