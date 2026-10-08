import { describe, expect, it, vi } from "vitest";
import { anchorInputSchema, createAnchor, anchorSummarySchema, anchorDetailSchema, anchorSetSchema, anchorCoverageSchema, listAnchors, getAnchorBank, editAnchorBank, applyAnchorBank, cancelAnchorBank, deleteAnchorBank, getAnchorHistory, getAnchorCoverage } from "@/lib/api/writing-anchors";

describe("Writing anchor HTTP contract", () => {
  it.each([1, 2] as const)("accepts custom Task %s and rejects mixed sources or invalid types", number => {
    const input = { source_kind: "CUSTOM_TASK", task_number: number, custom_prompt: "Fictional prompt.\n\nDetails.", custom_task_type: number === 1 ? "BAR_CHART" : "OPINION", response_text: "Intro.\n\nDetails.", human_scores: { ta: 6.5, cc: 7, lr: 7, gra: 7 } };
    expect(anchorInputSchema.parse(input)).toEqual(input);
    expect(anchorInputSchema.safeParse({ ...input, writing_task_id: "11111111-1111-4111-8111-111111111111" }).success).toBe(false);
    expect(anchorInputSchema.safeParse({ ...input, custom_prompt: " " }).success).toBe(false);
    expect(anchorInputSchema.safeParse({ ...input, custom_task_type: number === 1 ? "OPINION" : "BAR_CHART" }).success).toBe(false);
    expect(anchorInputSchema.safeParse({ ...input, custom_task_type: null }).success).toBe(true);
    const task = { id: null, test_version_id: null, test_title: "Đề ngoài", version_number: null, task_number: number, task_type: input.custom_task_type, prompt_preview: input.custom_prompt };
    const row = { id: "11111111-1111-4111-8111-111111111111", anchor_set_id: "22222222-2222-4222-8222-222222222222", source_kind: "CUSTOM_TASK", task, word_count: 3, human_scores: input.human_scores, created_at: "now", custom_prompt: input.custom_prompt, response_text: input.response_text, admin_note: null, provenance: null };
    expect(anchorDetailSchema.parse(row)).toEqual(row);
  });

  it("uses logical-bank routes while retaining internal English revision statuses", async () => {
    const set = { id: "11111111-1111-4111-8111-111111111111", name: "Kho anchor Writing", version: 1, status: "DRAFT", created_at: "now", activated_at: null, retired_at: null };
    const request = vi.fn().mockResolvedValueOnce({ current: null, working: set, current_count: 0, working_count: 1 }).mockResolvedValueOnce(set).mockResolvedValueOnce({ ...set, status: "ACTIVE" }).mockResolvedValueOnce(undefined).mockResolvedValueOnce(undefined).mockResolvedValueOnce({ items: [{ ...set, status: "RETIRED" }] }).mockResolvedValueOnce({ active_set: null, evaluated_set: set, production_task1: [], research_task1_ta: [], research_task2: [], recommendations: [], node_budget: 2 });
    expect((await getAnchorBank(request)).working?.status).toBe("DRAFT");
    await editAnchorBank(request);
    await applyAnchorBank(set.id, request);
    await cancelAnchorBank(set.id, request);
    await deleteAnchorBank(set.id, request);
    expect((await getAnchorHistory(request)).items[0].status).toBe("RETIRED");
    expect((await getAnchorCoverage(set.id, request)).evaluated_set?.id).toBe(set.id);
    expect(request.mock.calls).toEqual([
      ["/admin/writing-anchors/bank"], ["/admin/writing-anchors/bank/edit", { method: "POST" }],
      [`/admin/writing-anchors/bank/${set.id}/apply`, { method: "POST" }],
      [`/admin/writing-anchors/bank/${set.id}/working`, { method: "DELETE" }],
      [`/admin/writing-anchors/bank/${set.id}/current`, { method: "DELETE" }],
      ["/admin/writing-anchors/history"], [`/admin/writing-anchors/coverage?set_id=${set.id}`],
    ]);
  });

  it("validates four half-band labels and preserves paragraphs", async () => {
    const input = { source_kind: "BUILDER_TASK" as const, writing_task_id: "11111111-1111-4111-8111-111111111111", response_text: "Intro.\n\nDetails.", human_scores: { ta: 6.5, cc: 7, lr: 7, gra: 7 }, admin_note: null, provenance: null };
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
