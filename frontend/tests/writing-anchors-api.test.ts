import { describe, expect, it, vi } from "vitest";
import { anchorInputSchema, createAnchor, anchorSummarySchema, anchorSetSchema, anchorCoverageSchema, listAnchors } from "@/lib/api/writing-anchors";

describe("Writing anchor HTTP contract", () => {
  it("validates four half-band labels and preserves paragraphs", async () => {
    const input = { writing_task_id: "11111111-1111-4111-8111-111111111111", response_text: "Intro.\n\nDetails.", human_scores: { ta: 6.5, cc: 7, lr: 7, gra: 7 }, admin_note: null, provenance: null };
    expect(anchorInputSchema.parse(input).response_text).toBe(input.response_text);
    expect(anchorInputSchema.safeParse({ ...input, human_scores: { ...input.human_scores, ta: 6.2 } }).success).toBe(false);
    const api = vi.fn().mockRejectedValue(new Error("stop after request"));
    await expect(createAnchor("set", input, api)).rejects.toThrow();
    expect(JSON.parse(api.mock.calls[0][1].body).response_text).toBe(input.response_text);
  });
  it("rejects a compact list row without frozen task identity", () => {
    expect(anchorSummarySchema.safeParse({ id: "arbitrary" }).success).toBe(false);
  });
  it("retains English lifecycle and readiness enums in the API contract", () => {
    const set = { id: "11111111-1111-4111-8111-111111111111", name: "Human bank", version: 1, status: "ACTIVE", created_at: "now", activated_at: null, retired_at: null };
    for (const status of ["DRAFT", "ACTIVE", "RETIRED"]) {
      expect(anchorSetSchema.parse({ ...set, status }).status).toBe(status);
    }
    expect(anchorSetSchema.safeParse({ ...set, status: "Đang sử dụng" }).success).toBe(false);
    for (const readiness of ["EMPTY", "PARTIAL", "PAIRWISE_USABLE", "RECOMMENDED_COVERAGE"]) {
      const data = { active_set: set, production_task1: [{ criterion: "cc", counts: { "6": 2, "6.5": 3, "7": 2 }, ladder: [6, 7], readiness, pilot_complete: false }], research_task1_ta: [], research_task2: [], recommendations: [], node_budget: 2 };
      expect(anchorCoverageSchema.parse(data)).toEqual(data);
      expect(anchorCoverageSchema.safeParse({ ...data, production_task1: [{ ...data.production_task1[0], readiness: "Có thể dùng TACS" }] }).success).toBe(false);
    }
  });
  it("sends unchanged filter keys and enum values rather than display labels", async () => {
    const request = vi.fn().mockResolvedValue({ items: [], total: 0, offset: 25, limit: 25 });
    await listAnchors({ set_id: "draft-id", task_number: 2, status: "DRAFT", writing_task_id: "frozen-id", search: "bài viết", task_type: "essay", offset: 25 }, request);
    const query = new URLSearchParams(request.mock.calls[0][0].split("?")[1]);
    expect(Object.fromEntries(query)).toEqual({ set_id: "draft-id", task_number: "2", status: "DRAFT", writing_task_id: "frozen-id", search: "bài viết", task_type: "essay", offset: "25" });
  });
});
