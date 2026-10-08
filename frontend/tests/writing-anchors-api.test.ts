import { describe, expect, it, vi } from "vitest";
import { anchorInputSchema, createAnchor, anchorSummarySchema } from "@/lib/api/writing-anchors";

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
});
