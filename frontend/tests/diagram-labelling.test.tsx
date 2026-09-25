import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DiagramLabellingEditor } from "@/features/questions/diagram-labelling-editor";
import { DiagramLabellingRenderer } from "@/features/questions/diagram-labelling-renderer";
import { diagramLabellingErrors } from "@/features/questions/diagram-labelling";
import { questionRegistry, readingQuestionTypeOptions } from "@/features/questions/registry";
import type { ExamGroup, QuestionGroupModel } from "@/features/questions/types";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";
import { uploadAsset } from "@/lib/api/assets";

vi.mock("@/lib/api/assets", () => ({
  assetContentUrl: (asset: { content_url: string }) => asset.content_url,
  uploadAsset: vi.fn(),
}));

const asset = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  original_name: "fictional-diagram.png",
  mime_type: "image/png",
  file_size: 2048,
  content_url: "/assets/fictional-diagram.png",
};

function diagramGroup(withImage = true): QuestionGroupModel {
  const group = questionRegistry.diagram_labelling.createDefault(20);
  group.id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  group.questions[0].prompt = "A pair of {{gap}} are lifted.";
  group.questions[0].answer_key = { kind: "TEXT", accepted: ["gates"], case_sensitive: false };
  if (withImage) {
    group.image_asset_id = asset.id;
    group.image_asset = asset;
  }
  return group;
}

function EditorHarness({ initial = diagramGroup() }: { initial?: QuestionGroupModel }) {
  const [group, setGroup] = useState(initial);
  return <><DiagramLabellingEditor group={group} onChange={setGroup} /><output data-testid="state">{JSON.stringify(group)}</output></>;
}

function GroupEditorHarness({ initial = diagramGroup() }: { initial?: QuestionGroupModel }) {
  return (
    <BuilderLifecycleProvider>
      <QuestionGroupEditor
        initial={initial}
        nextQuestionNumber={21}
        passageBlocks={[]}
        testVersionId="cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        onCancel={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />
    </BuilderLifecycleProvider>
  );
}

describe("diagram label completion", () => {
  beforeEach(() => vi.mocked(uploadAsset).mockReset());

  it("remains available in Reading and creates text-gap canvas data", () => {
    expect(readingQuestionTypeOptions).toContainEqual({ id: "diagram_labelling", label: "Diagram Label Completion" });
    const group = questionRegistry.diagram_labelling.createDefault(20);
    expect(group.config).not.toHaveProperty("options");
    expect(group.questions[0].prompt.match(/\{\{gap\}\}/g)).toHaveLength(1);
    expect(group.questions[0].answer_key.kind).toBe("TEXT");
    expect((group.config.items as Array<{ question_id: string }>)[0].question_id).toBe(group.questions[0].id);
  });

  it("exposes Reading-compatible upload and assigns the returned asset", async () => {
    vi.mocked(uploadAsset).mockResolvedValue(asset);
    render(<GroupEditorHarness initial={diagramGroup(false)} />);
    expect(screen.getByText("Upload a diagram image before saving this group.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Upload diagram"), {
      target: { files: [new File(["image"], "diagram.png", { type: "image/png" })] },
    });
    await waitFor(() => expect(uploadAsset).toHaveBeenCalledWith(
      "question-images",
      "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
      expect.any(File),
    ));
    expect(await screen.findByAltText("Diagram being labelled")).toHaveAttribute("src", asset.content_url);
    expect(screen.getByRole("button", { name: "Remove image" })).toBeInTheDocument();
  });

  it("opens legacy option-marker drafts as editable text-gap diagrams", () => {
    const group = diagramGroup();
    const questionId = group.questions[0].id!;
    group.config = {
      options: [
        { id: "A", label: "A", text: "gates" },
        { id: "B", label: "B", text: "locks" },
      ],
      markers: [{ id: crypto.randomUUID(), question_id: questionId, x: 0.42, y: 0.57 }],
    };
    group.questions[0].prompt = "A pair of ______ are lifted.";
    group.questions[0].answer_key = { kind: "SINGLE_OPTION", value: "A" };
    render(<GroupEditorHarness initial={group} />);
    expect(screen.getByLabelText("Diagram sentence")).toHaveValue("A pair of {{gap}} are lifted.");
    expect(screen.getByLabelText("Primary accepted answer")).toHaveValue("gates");
    expect(screen.queryByText("Matching options")).not.toBeInTheDocument();
  });

  it("adds and removes a question together with its canvas item", () => {
    render(<GroupEditorHarness />);
    fireEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    expect(screen.getByLabelText("Question 21 diagram inspector")).toBeInTheDocument();
    expect(screen.getAllByText(/Diagram label/).length).toBeGreaterThanOrEqual(2);
    fireEvent.click(within(screen.getByLabelText("Question 21 diagram inspector")).getByRole("button", { name: "Remove question" }));
    expect(screen.queryByLabelText("Question 21 diagram inspector")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Question 20 diagram inspector")).toBeInTheDocument();
  });

  it("updates normalized box and arrow geometry through pointer dragging", () => {
    const view = render(<EditorHarness />);
    const canvas = view.container.querySelector(".diagram-canvas") as HTMLElement;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 500, width: 1000, height: 500, toJSON: () => ({}) });
    const label = view.container.querySelector(".diagram-label-editor") as HTMLElement;
    vi.spyOn(label, "getBoundingClientRect").mockReturnValue({ x: 50, y: 30, left: 50, top: 30, right: 350, bottom: 80, width: 300, height: 50, toJSON: () => ({}) });

    fireEvent.pointerDown(label, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(label, { pointerId: 1, clientX: 200, clientY: 150 });
    fireEvent.pointerUp(label, { pointerId: 1, clientX: 200, clientY: 150 });
    let state = JSON.parse(screen.getByTestId("state").textContent ?? "{}") as QuestionGroupModel;
    expect((state.config.items as Array<{ box: { x: number; y: number } }>)[0].box.x).toBeCloseTo(0.15);
    expect((state.config.items as Array<{ box: { x: number; y: number } }>)[0].box.y).toBeCloseTo(0.16);

    const target = screen.getByRole("button", { name: "Move arrow target for question 20" });
    fireEvent.pointerDown(target, { pointerId: 2, clientX: 500, clientY: 250 });
    fireEvent.pointerMove(target, { pointerId: 2, clientX: 800, clientY: 400 });
    fireEvent.pointerUp(target, { pointerId: 2, clientX: 800, clientY: 400 });
    state = JSON.parse(screen.getByTestId("state").textContent ?? "{}") as QuestionGroupModel;
    expect((state.config.items as Array<{ arrow: { end_x: number; end_y: number } }>)[0].arrow).toMatchObject({ end_x: 0.8, end_y: 0.8 });
  });

  it("edits the selected prompt and text answer key", () => {
    render(<EditorHarness />);
    fireEvent.change(screen.getByLabelText("Diagram sentence"), { target: { value: "Hydraulic motors drive {{gap}}." } });
    fireEvent.change(screen.getByLabelText("Primary accepted answer"), { target: { value: "axles" } });
    const state = JSON.parse(screen.getByTestId("state").textContent ?? "{}") as QuestionGroupModel;
    expect(state.questions[0].prompt).toBe("Hydraulic motors drive {{gap}}.");
    expect(state.questions[0].answer_key).toMatchObject({ kind: "TEXT", accepted: ["axles"] });
  });

  it("authors a headline and static arrow without adding a question or answer key", () => {
    const initial = diagramGroup();
    initial.questions[0].answer_key = { kind: "TEXT", accepted: [], case_sensitive: false };
    const view = render(<EditorHarness initial={initial} />);
    fireEvent.change(screen.getByLabelText("Diagram headline"), { target: { value: "Fictional lifting stages" } });
    fireEvent.click(screen.getByRole("button", { name: "+ Add arrow label" }));
    fireEvent.change(screen.getByLabelText("Annotation text"), { target: { value: "Crane hook" } });
    fireEvent.change(screen.getByLabelText("Annotation label X"), { target: { value: "0.27" } });
    fireEvent.change(screen.getByLabelText("Annotation target Y"), { target: { value: "0.76" } });
    const canvas = view.container.querySelector(".diagram-canvas") as HTMLElement;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 500, width: 1000, height: 500, toJSON: () => ({}) });
    const label = view.container.querySelector(".diagram-static-annotation") as HTMLElement;
    fireEvent.pointerDown(label, { pointerId: 3, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(label, { pointerId: 3, clientX: 200, clientY: 150 });
    fireEvent.pointerUp(label, { pointerId: 3, clientX: 200, clientY: 150 });
    const target = screen.getByRole("button", { name: "Move annotation arrow target" });
    fireEvent.pointerDown(target, { pointerId: 4, clientX: 500, clientY: 250 });
    fireEvent.pointerMove(target, { pointerId: 4, clientX: 800, clientY: 400 });
    fireEvent.pointerUp(target, { pointerId: 4, clientX: 800, clientY: 400 });
    const saved = JSON.parse(screen.getByTestId("state").textContent ?? "{}") as QuestionGroupModel;
    expect(saved.config.title).toBe("Fictional lifting stages");
    expect(saved.config.annotations).toMatchObject([{ kind: "ARROW_LABEL", text: "Crane hook", label_x: 0.37, target_y: 0.8 }]);
    expect(saved.questions).toEqual(initial.questions);
    expect(diagramLabellingErrors(saved)).toEqual([]);
    view.unmount();
    render(<EditorHarness initial={saved} />);
    expect(screen.getByLabelText("Diagram headline")).toHaveValue("Fictional lifting stages");
    expect(screen.getByText("Crane hook")).toBeInTheDocument();
  });

  it("authors, moves, and removes a plain note independently of numbered labels", () => {
    render(<EditorHarness />);
    fireEvent.click(screen.getByRole("button", { name: "+ Add note label" }));
    fireEvent.change(screen.getByLabelText("Annotation text"), { target: { value: "Hull of vessel" } });
    fireEvent.change(screen.getByLabelText("Annotation label Y"), { target: { value: "0.61" } });
    let saved = JSON.parse(screen.getByTestId("state").textContent ?? "{}") as QuestionGroupModel;
    expect(saved.config.annotations).toMatchObject([{ kind: "NOTE", text: "Hull of vessel", label_y: 0.61 }]);
    expect((saved.config.annotations as Array<{ target_x?: number }>)[0]).not.toHaveProperty("target_x");
    expect(saved.questions).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Remove annotation" }));
    saved = JSON.parse(screen.getByTestId("state").textContent ?? "{}") as QuestionGroupModel;
    expect(saved.config.annotations).toEqual([]);
    expect(saved.questions).toHaveLength(1);
  });

  it("shows the title and static annotations alongside the numbered answer in exam rendering", () => {
    const group = diagramGroup() as ExamGroup;
    group.config = {
      ...group.config,
      title: "Fictional lifting stages",
      annotations: [
        { id: crypto.randomUUID(), kind: "ARROW_LABEL", text: "Crane hook", label_x: 0.2, label_y: 0.3, target_x: 0.5, target_y: 0.6 },
        { id: crypto.randomUUID(), kind: "NOTE", text: "Hull of vessel", label_x: 0.7, label_y: 0.4 },
      ],
    };
    const view = render(<DiagramLabellingRenderer group={group} values={{}} onAnswer={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Fictional lifting stages" })).toBeInTheDocument();
    expect(screen.getByLabelText("Question 20")).toBeInTheDocument();
    expect(screen.getByLabelText("Diagram annotation Crane hook")).toBeInTheDocument();
    expect(screen.getByLabelText("Diagram annotation Hull of vessel")).toBeInTheDocument();
    expect(view.container.querySelectorAll(".diagram-static-arrow")).toHaveLength(1);
    expect(view.container.querySelectorAll(".diagram-candidate-label")).toHaveLength(1);
  });

  it("renders the authored position with an inline input and no matching select", () => {
    const group = diagramGroup() as ExamGroup;
    const item = (group.config.items as Array<{ box: { x: number; y: number; width: number } }>)[0];
    item.box = { x: 0.17, y: 0.29, width: 0.34 };
    const onAnswer = vi.fn();
    const view = render(<DiagramLabellingRenderer group={group} values={{}} onAnswer={onAnswer} />);
    const input = screen.getByLabelText("Question 20");
    expect(input).toBeInTheDocument();
    expect(view.container.querySelector(".diagram-candidate-label")).toHaveStyle({ left: "17%", top: "29%", width: "34%" });
    expect(view.container.querySelector("select")).not.toBeInTheDocument();
    expect(view.container.querySelector(".diagram-label-copy")).toHaveTextContent("20 A pair of are lifted.");
    fireEvent.change(input, { target: { value: "gates" } });
    expect(onAnswer).toHaveBeenCalledWith(group.questions[0].id, "gates");
  });

  it("uses the same saved layout in Builder Preview", () => {
    const group = diagramGroup();
    const item = (group.config.items as Array<{ box: { x: number; y: number; width: number } }>)[0];
    item.box = { x: 0.22, y: 0.31, width: 0.28 };
    group.config.title = "Fictional preview title";
    group.config.annotations = [{ id: crypto.randomUUID(), kind: "NOTE", text: "Static preview label", label_x: 0.4, label_y: 0.5 }];
    const view = render(<GroupEditorHarness initial={group} />);
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(screen.getByRole("heading", { name: "Fictional preview title" })).toBeInTheDocument();
    expect(screen.getByLabelText("Diagram annotation Static preview label")).toBeInTheDocument();
    expect(view.container.querySelector(".diagram-candidate-label")).toHaveStyle({ left: "22%", top: "31%", width: "28%" });
    expect(view.container.querySelector(".diagram-arrow-handle")).not.toBeInTheDocument();
  });

  it("hands the latest dragged geometry to the existing debounced autosave", async () => {
    vi.useFakeTimers();
    const autosave = vi.fn().mockResolvedValue(undefined);
    const view = render(
      <BuilderLifecycleProvider>
        <QuestionGroupEditor
          initial={diagramGroup()}
          nextQuestionNumber={21}
          passageBlocks={[]}
          testVersionId="cccccccc-cccc-4ccc-8ccc-cccccccccccc"
          onCancel={vi.fn()}
          onSave={vi.fn().mockResolvedValue(undefined)}
          onAutosave={autosave}
        />
      </BuilderLifecycleProvider>,
    );
    const canvas = view.container.querySelector(".diagram-canvas") as HTMLElement;
    const label = view.container.querySelector(".diagram-label-editor") as HTMLElement;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 500, width: 1000, height: 500, toJSON: () => ({}) });
    vi.spyOn(label, "getBoundingClientRect").mockReturnValue({ x: 50, y: 30, left: 50, top: 30, right: 350, bottom: 80, width: 300, height: 50, toJSON: () => ({}) });
    fireEvent.pointerDown(label, { pointerId: 9, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(label, { pointerId: 9, clientX: 300, clientY: 200 });
    fireEvent.pointerUp(label, { pointerId: 9, clientX: 300, clientY: 200 });
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(autosave).toHaveBeenCalled();
    const saved = autosave.mock.calls.at(-1)?.[0] as QuestionGroupModel;
    expect((saved.config.items as Array<{ box: { x: number; y: number } }>)[0].box).toMatchObject({ x: 0.25, y: 0.26 });
    vi.useRealTimers();
  });
});
