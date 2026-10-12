// @vitest-environment node
import type { APIRequestContext } from "@playwright/test";
import { expect, it, vi } from "vitest";
import { createPublishedExam } from "./e2e/exam-fixtures";

// Exercise the fixture without loading Playwright or contacting an API.
vi.mock("@playwright/test", async () => ({ expect: (await import("vitest")).expect }));

it("authors all three Speaking parts before publishing a fictional exam", async () => {
  const parts = [1, 2, 3].map((part_number) => ({
    id: `speaking-part-${part_number}`, revision: part_number + 1, part_number,
    prompts: part_number === 2 ? [{ id: "11111111-1111-4111-8111-111111111111", prompt_type: "LONG_TURN" }] : [],
  }));
  const authored: Array<{ part: typeof parts[number]; data: {
    expected_revision: number;
    prompts: Array<{
      id?: string; order_index: number; prompt_type: string; prompt_text: string;
      preparation_seconds: number; response_seconds: number; config_json: { cue_points?: string[] };
    }>;
  } }> = [];
  const response = (data: unknown) => ({ ok: () => true, status: () => 200,
    text: async () => JSON.stringify(data), json: async () => data });
  const request = {
    post: async (url: string) => {
      const path = new URL(url).pathname.replace("/api/v1", "");
      if (path === "/tests") return response({ id: "fictional-test", versions: [{ id: "fictional-version" }] });
      if (path === "/test-versions/fictional-version/modules") {
        return response({ id: "speaking-module", revision: 1, writing_tasks: [], speaking_parts: parts });
      }
      if (path === "/test-versions/fictional-version/validate") return response({ valid: true, issues: [] });
      if (path === "/test-versions/fictional-version/publish") {
        expect(authored.map(({ part }) => part.part_number)).toEqual([1, 2, 3]);
        return response({ id: "fictional-version" });
      }
      throw new Error(`Unexpected fixture POST ${path}`);
    },
    put: async (url: string, { data }: { data: typeof authored[number]["data"] }) => {
      const part = parts.find((item) => url.endsWith(`/speaking/parts/${item.id}`));
      if (!part) throw new Error(`Unexpected fixture PUT ${url}`);
      authored.push({ part, data });
      return response({ ...part, ...data });
    },
  } as unknown as APIRequestContext;

  await createPublishedExam(request, ["SPEAKING"]);

  expect(authored.map(({ part }) => part.part_number)).toEqual([1, 2, 3]);
  expect(authored.map(({ data }) => data.prompts.map((prompt) => prompt.prompt_type)))
    .toEqual([["SHORT_ANSWER"], ["LONG_TURN", "FOLLOW_UP"], ["SHORT_ANSWER"]]);
  for (const { part, data } of authored) {
    expect(data.expected_revision).toBe(part.revision);
    expect(data.prompts.map((prompt) => prompt.order_index)).toEqual(part.part_number === 2 ? [0, 1] : [0]);
    for (const prompt of data.prompts) {
      expect(prompt.prompt_text.trim().length).toBeGreaterThan(0);
      expect(prompt.response_seconds).toBeGreaterThan(0);
      if (prompt.prompt_type === "LONG_TURN") {
        expect(prompt.id).toBe("11111111-1111-4111-8111-111111111111");
        expect(prompt.preparation_seconds).toBeGreaterThan(0);
        expect(prompt.config_json.cue_points?.length).toBeGreaterThan(0);
      } else {
        expect(prompt.preparation_seconds).toBe(0);
        expect(prompt.config_json.cue_points ?? []).toEqual([]);
      }
    }
  }
});
