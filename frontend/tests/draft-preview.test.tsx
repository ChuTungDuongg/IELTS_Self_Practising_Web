import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DraftPreview } from "@/features/test-builder/draft-preview";
import type { BuilderVersion } from "@/lib/api/builder";

const version: BuilderVersion = {
  id: "11111111-1111-4111-8111-111111111111",
  test_id: "22222222-2222-4222-8222-222222222222",
  test_title: "Fictional draft",
  version_number: 2,
  status: "DRAFT",
  modules: [{
    id: "33333333-3333-4333-8333-333333333333",
    module_type: "READING",
    title: "Reading",
    recommended_duration_seconds: 3600,
    audio_asset: null,
    listening_parts: [],
    passages: [{
      id: "44444444-4444-4444-8444-444444444444",
      title: "Passage",
      order_index: 0,
      blocks: [{ id: "55555555-5555-4555-8555-555555555555", type: "paragraph", label: "A", text: "Preview text" }],
      question_groups: [{
        id: "66666666-6666-4666-8666-666666666666",
        question_type: "true_false_not_given",
        instruction: "",
        config: {},
        order_index: 0,
        questions: [{ id: "77777777-7777-4777-8777-777777777777", number: 1, prompt: "Statement", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, explanation: null, order_index: 0 }],
        image_asset_id: null,
        image_asset: null,
      }],
    }],
  }],
};

describe("DraftPreview", () => {
  it("renders the candidate question UI with ephemeral local answers", () => {
    render(<DraftPreview version={version} moduleType="READING" />);
    expect(screen.getByText(/DRAFT PREVIEW/)).toBeInTheDocument();
    expect(screen.getByText("Preview text")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "TRUE" }));
    expect(screen.getByRole("radio", { name: "TRUE" })).toBeChecked();
    expect(screen.getByText("Answers in preview are not saved.")).toBeInTheDocument();
  });
});
