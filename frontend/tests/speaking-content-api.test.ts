import { describe, expect, it, vi } from "vitest";
import { getVersion } from "@/lib/api/tests";
import { apiRequest } from "@/lib/api/client";
import { createSpeakingModule, createSpeakingPrompt, updateSpeakingPart, reorderSpeakingPrompts } from "@/lib/api/builder";

vi.mock("@/lib/api/client", async original => ({ ...await original<object>(), apiRequest: vi.fn() }));
const id = "11111111-1111-4111-8111-111111111111";
const part = { id, revision: 2, part_number: 2, title: null, instructions: null, order_index: 1, prompts: [{ id, order_index: 0, prompt_type: "LONG_TURN", prompt_text: "Fictional cue", preparation_seconds: 60, response_seconds: 120, config_json: { cue_points: ["Its purpose"] } }] };

describe("Speaking authored API compatibility", () => {
  it("reads Speaking version metadata used by clone/transfer without enabling a runner", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id, test_id: id, test_title: "Fictional", version_number: 1, status: "DRAFT", created_at: "now", published_at: null, modules: [{ id, module_type: "SPEAKING", title: null, recommended_duration_seconds: null, passage_count: 0, listening_part_count: 0, writing_task_count: 0, question_count: 0 }] });
    expect((await getVersion(id)).modules[0].module_type).toBe("SPEAKING");
  });

  it("parses module creation and sends prompt/default mutations with part revisions", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id, revision: 1, module_type: "SPEAKING", title: null, recommended_duration_seconds: null, speaking_parts: [part] });
    expect((await createSpeakingModule(id)).speaking_parts![0].prompts[0].response_seconds).toBe(120);
    vi.mocked(apiRequest).mockResolvedValue(part);
    await createSpeakingPrompt(id, { expected_revision: 1, prompt_type: "FOLLOW_UP" });
    expect(apiRequest).toHaveBeenLastCalledWith(`/speaking/parts/${id}/prompts`, { method: "POST", body: JSON.stringify({ expected_revision: 1, prompt_type: "FOLLOW_UP" }) });
    const { title, instructions, prompts } = part;
    await updateSpeakingPart(id, { expected_revision: 2, title, instructions, prompts: prompts.map(prompt => ({ ...prompt, prompt_type: "LONG_TURN" as const })) });
    expect(apiRequest).toHaveBeenLastCalledWith(`/speaking/parts/${id}`, expect.objectContaining({ method: "PUT" }));
    await reorderSpeakingPrompts(id, 3, [id]);
    expect(apiRequest).toHaveBeenLastCalledWith(`/speaking/parts/${id}/prompts/order`, { method: "PUT", body: JSON.stringify({ expected_revision: 3, prompt_ids: [id] }) });
  });
});
