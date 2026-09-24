import { beforeEach, describe, expect, it } from "vitest";
import { ExamDraftStore, draftStorageKey } from "@/features/exam/exam-draft-recovery";

const attemptId = "11111111-1111-4111-8111-111111111111";
const testVersionId = "22222222-2222-4222-8222-222222222222";
const questionId = "33333333-3333-4333-8333-333333333333";
const metadata = { attempt_id: attemptId, test_version_id: testVersionId, module: "READING" as const };
const key = draftStorageKey(attemptId);

function record(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 1, ...metadata, updated_at: new Date().toISOString(),
    entries: { [questionId]: { kind: "answer", value: "FALSE", base_server_revision: 4 } },
    ...overrides,
  };
}

describe("ExamDraftStore", () => {
  beforeEach(() => sessionStorage.clear());

  it("removes malformed JSON and unsupported schema versions", () => {
    const store = new ExamDraftStore(metadata);
    sessionStorage.setItem(key, "{invalid");
    expect(store.load()).toBeNull();
    expect(sessionStorage.getItem(key)).toBeNull();
    sessionStorage.setItem(key, JSON.stringify(record({ schema_version: 2 })));
    expect(store.load()).toBeNull();
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  it.each([
    { attempt_id: "44444444-4444-4444-8444-444444444444" },
    { test_version_id: "55555555-5555-4555-8555-555555555555" },
    { module: "LISTENING" },
  ])("rejects a mismatched record %j", (override) => {
    sessionStorage.setItem(key, JSON.stringify(record(override)));
    expect(new ExamDraftStore(metadata).load()).toBeNull();
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  it("loads valid metadata, only response values, and drops the whole record after acknowledgement", () => {
    const store = new ExamDraftStore(metadata);
    store.saveEntry(questionId, "FALSE", 4);
    expect(store.load()?.entries[questionId]).toEqual({
      kind: "answer", value: "FALSE", base_server_revision: 4,
    });
    expect(JSON.parse(sessionStorage.getItem(key) ?? "{}")).toEqual({
      schema_version: 1, ...metadata, updated_at: expect.any(String),
      entries: { [questionId]: { kind: "answer", value: "FALSE", base_server_revision: 4 } },
    });
    store.removeEntry(questionId);
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  it("discards an already saved value and never marks it for retry", () => {
    sessionStorage.setItem(key, JSON.stringify(record()));
    const store = new ExamDraftStore(metadata);
    expect(store.reconcile([{ id: questionId, value: "FALSE", revision: 5 }])).toEqual({ safe: [], conflicts: [] });
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  it("restores only matching revisions and flags newer server values as conflicts", () => {
    sessionStorage.setItem(key, JSON.stringify(record()));
    const store = new ExamDraftStore(metadata);
    expect(store.reconcile([{ id: questionId, value: "TRUE", revision: 4 }])).toEqual({
      safe: [{ id: questionId, value: "FALSE" }], conflicts: [],
    });
    expect(store.reconcile([{ id: questionId, value: "TRUE", revision: 5 }])).toEqual({
      safe: [], conflicts: [{ id: questionId, localValue: "FALSE", serverValue: "TRUE", serverRevision: 5 }],
    });
    expect(store.load()?.entries[questionId]).toBeDefined();
  });

  it("rejects keys outside the authoritative attempt and disallows stored answer keys", () => {
    const store = new ExamDraftStore(metadata);
    sessionStorage.setItem(key, JSON.stringify(record({
      entries: { [questionId]: { kind: "answer", value: "FALSE", base_server_revision: 4, answer_key: "TRUE" } },
    })));
    expect(store.load()).toBeNull();
    store.saveEntry(questionId, "FALSE", 4);
    expect(store.reconcile([])).toEqual({ safe: [], conflicts: [] });
    expect(sessionStorage.getItem(key)).toBeNull();
  });
});
