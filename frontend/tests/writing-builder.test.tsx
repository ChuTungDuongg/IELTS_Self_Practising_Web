import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { WritingBuilder } from "@/features/test-builder/writing-builder";
import { uploadAsset } from "@/lib/api/assets";
import {
  createWritingModule,
  deleteModule,
  updateWritingTask,
  type BuilderVersion,
} from "@/lib/api/builder";
import { ApiError } from "@/lib/api/client";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/assets", () => ({
  uploadAsset: vi.fn(),
  assetContentUrl: (asset: { content_url: string }) => `http://api.test${asset.content_url}`,
}));
vi.mock("@/lib/api/builder", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/builder")>();
  return {
    ...actual,
    createWritingModule: vi.fn(),
    updateWritingTask: vi.fn(),
    deleteModule: vi.fn(),
  };
});

const versionId = "11111111-1111-4111-8111-111111111111";
const testId = "22222222-2222-4222-8222-222222222222";
const taskOneId = "33333333-3333-4333-8333-333333333333";
const taskTwoId = "44444444-4444-4444-8444-444444444444";

function version(withModule = true): BuilderVersion {
  return {
    id: versionId,
    test_id: testId,
    test_title: "Fictional Writing draft",
    version_number: 1,
    status: "DRAFT",
    modules: withModule
      ? [{
          id: "55555555-5555-4555-8555-555555555555",
          revision: 1,
          module_type: "WRITING",
          title: "Writing",
          recommended_duration_seconds: 3600,
          audio_asset: null,
          passages: [],
          listening_parts: [],
          writing_tasks: [
            {
              id: taskOneId,
              revision: 1,
              task_number: 1,
              prompt: "Describe fictional data.",
              image_asset_id: null,
              image_asset: null,
              minimum_recommended_words: 150,
              recommended_duration_seconds: 1200,
              order_index: 0,
            },
            {
              id: taskTwoId,
              revision: 1,
              task_number: 2,
              prompt: "Discuss a fictional proposition.",
              image_asset_id: null,
              image_asset: null,
              minimum_recommended_words: 250,
              recommended_duration_seconds: 2400,
              order_index: 1,
            },
          ],
        }]
      : [],
  };
}

function renderBuilder(value: BuilderVersion) {
  return render(
    <BuilderLifecycleProvider>
      <WritingBuilder version={value} />
    </BuilderLifecycleProvider>,
  );
}

describe("WritingBuilder", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(createWritingModule).mockResolvedValue({});
    vi.mocked(updateWritingTask).mockResolvedValue(version().modules[0].writing_tasks[0]);
    vi.mocked(deleteModule).mockResolvedValue({});
  });

  it("initializes the fixed two-task module", async () => {
    renderBuilder(version(false));
    fireEvent.click(screen.getByRole("button", { name: "Create Writing module" }));
    await waitFor(() => expect(createWritingModule).toHaveBeenCalledWith(versionId));
    expect(refresh).toHaveBeenCalled();
  });

  it("edits fixed tasks and sends a complete task payload", async () => {
    renderBuilder(version());
    const taskOne = screen.getByRole("group", { name: "Writing Task 1" });
    const taskTwo = screen.getByRole("group", { name: "Writing Task 2" });
    expect(within(taskOne).getByText("Task 1")).toBeInTheDocument();
    expect(within(taskTwo).getByText("Task 2")).toBeInTheDocument();
    expect(within(taskTwo).queryByLabelText(/Task image/)).not.toBeInTheDocument();

    fireEvent.change(within(taskOne).getByLabelText("Prompt"), {
      target: { value: "Describe the updated fictional chart." },
    });
    fireEvent.change(within(taskOne).getByLabelText("Minimum recommended words"), {
      target: { value: "175" },
    });
    fireEvent.change(within(taskOne).getByLabelText("Recommended time (minutes)"), {
      target: { value: "25" },
    });
    fireEvent.click(within(taskOne).getByRole("button", { name: "Save Task 1" }));

    await waitFor(() =>
      expect(updateWritingTask).toHaveBeenCalledWith(taskOneId, {
        expected_revision: 1,
        prompt: "Describe the updated fictional chart.",
        image_asset_id: null,
        minimum_recommended_words: 175,
        recommended_duration_seconds: 1500,
      }),
    );
  });

  it("keeps Writing Task 1 and Task 2 revisions independent", async () => {
    const value = version();
    value.modules[0].writing_tasks[0].revision = 2;
    value.modules[0].writing_tasks[1].revision = 8;
    vi.mocked(updateWritingTask).mockImplementation(async (taskId) => taskId === taskOneId
      ? { ...value.modules[0].writing_tasks[0], revision: 3 }
      : { ...value.modules[0].writing_tasks[1], revision: 9 });
    renderBuilder(value);
    const taskOne = screen.getByRole("group", { name: "Writing Task 1" });
    const taskTwo = screen.getByRole("group", { name: "Writing Task 2" });
    fireEvent.change(within(taskOne).getByLabelText("Prompt"), { target: { value: "Task 1 updated" } });
    fireEvent.click(within(taskOne).getByRole("button", { name: "Save Task 1" }));
    await waitFor(() => expect(updateWritingTask).toHaveBeenCalledTimes(1));
    fireEvent.change(within(taskTwo).getByLabelText("Prompt"), { target: { value: "Task 2 updated" } });
    fireEvent.click(within(taskTwo).getByRole("button", { name: "Save Task 2" }));
    await waitFor(() => expect(updateWritingTask).toHaveBeenCalledTimes(2));
    expect(vi.mocked(updateWritingTask).mock.calls.map(([taskId, body]) => [taskId, body.expected_revision])).toEqual([
      [taskOneId, 2], [taskTwoId, 8],
    ]);
  });

  it("blocks another Writing save after a stale conflict", async () => {
    vi.mocked(updateWritingTask).mockRejectedValue(new ApiError("DRAFT_REVISION_CONFLICT", "Reload latest", 409));
    renderBuilder(version());
    const taskOne = screen.getByRole("group", { name: "Writing Task 1" });
    fireEvent.change(within(taskOne).getByLabelText("Prompt"), { target: { value: "Stale prompt" } });
    fireEvent.click(within(taskOne).getByRole("button", { name: "Save Task 1" }));
    expect(await screen.findByRole("button", { name: "Reload latest" })).toBeInTheDocument();
    expect(within(taskOne).getByRole("button", { name: "Save Task 1" })).toBeDisabled();
    expect(updateWritingTask).toHaveBeenCalledTimes(1);
  });

  it("uploads, previews, removes Task 1 images, and confirms module deletion", async () => {
    const asset = {
      id: "66666666-6666-4666-8666-666666666666",
      original_name: "chart.png",
      mime_type: "image/png",
      file_size: 10,
      content_url: "/assets/chart.png",
    };
    vi.mocked(uploadAsset).mockResolvedValue(asset);
    renderBuilder(version());
    const taskOne = screen.getByRole("group", { name: "Writing Task 1" });
    const file = new File(["image"], "chart.png", { type: "image/png" });
    fireEvent.change(within(taskOne).getByLabelText("Task image"), {
      target: { files: [file] },
    });

    await waitFor(() => expect(uploadAsset).toHaveBeenCalledWith("images", versionId, file));
    await waitFor(() =>
      expect(updateWritingTask).toHaveBeenCalledWith(
        taskOneId,
        expect.objectContaining({ image_asset_id: asset.id }),
      ),
    );
    expect(await within(taskOne).findByAltText("Writing Task 1 reference")).toHaveAttribute(
      "src",
      "http://api.test/assets/chart.png",
    );
    fireEvent.click(within(taskOne).getByRole("button", { name: "Remove image" }));
    await waitFor(() =>
      expect(updateWritingTask).toHaveBeenLastCalledWith(
        taskOneId,
        expect.objectContaining({ image_asset_id: null }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete module" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete Writing module" }));
    await waitFor(() =>
      expect(deleteModule).toHaveBeenCalledWith("55555555-5555-4555-8555-555555555555"),
    );
  });

  it("serializes image persistence with newer prompt edits on the same task", async () => {
    const asset = {
      id: "66666666-6666-4666-8666-666666666666",
      original_name: "chart.png",
      mime_type: "image/png",
      file_size: 10,
      content_url: "/assets/chart.png",
    };
    let resolveUpload!: (value: typeof asset) => void;
    let resolveImageWrite!: () => void;
    vi.mocked(uploadAsset).mockImplementation(() => new Promise((resolve) => { resolveUpload = resolve; }));
    vi.mocked(updateWritingTask)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveImageWrite = () => resolve(version().modules[0].writing_tasks[0]);
      }))
      .mockResolvedValue(version().modules[0].writing_tasks[0]);
    renderBuilder(version());
    const taskOne = screen.getByRole("group", { name: "Writing Task 1" });
    const prompt = within(taskOne).getByLabelText("Prompt");
    const file = new File(["image"], "chart.png", { type: "image/png" });

    fireEvent.change(within(taskOne).getByLabelText("Task image"), { target: { files: [file] } });
    fireEvent.change(prompt, { target: { value: "Prompt edited while upload is running." } });
    await act(async () => { resolveUpload(asset); });

    await waitFor(() => expect(updateWritingTask).toHaveBeenCalledTimes(1));
    expect(updateWritingTask).toHaveBeenNthCalledWith(1, taskOneId, expect.objectContaining({
      prompt: "Prompt edited while upload is running.",
      image_asset_id: asset.id,
    }));

    fireEvent.change(prompt, { target: { value: "Newest prompt while image write is running." } });
    fireEvent.click(within(taskOne).getByRole("button", { name: "Save Task 1" }));
    expect(updateWritingTask).toHaveBeenCalledTimes(1);
    await act(async () => { resolveImageWrite(); });

    await waitFor(() => expect(updateWritingTask).toHaveBeenCalledTimes(2));
    const taskOneWrites = vi.mocked(updateWritingTask).mock.calls.filter(([taskId]) => taskId === taskOneId);
    expect(taskOneWrites).toHaveLength(2);
    expect(taskOneWrites.at(-1)).toEqual([taskOneId, expect.objectContaining({
      prompt: "Newest prompt while image write is running.",
      image_asset_id: asset.id,
    })]);
  });

  it("restores only image fields after a failed removal and preserves newer text", async () => {
    const asset = {
      id: "66666666-6666-4666-8666-666666666666",
      original_name: "chart.png",
      mime_type: "image/png",
      file_size: 10,
      content_url: "/assets/chart.png",
    };
    const value = version();
    value.modules[0].writing_tasks[0].image_asset_id = asset.id;
    value.modules[0].writing_tasks[0].image_asset = asset;
    let rejectRemoval!: (reason: Error) => void;
    vi.mocked(updateWritingTask).mockImplementationOnce(() => new Promise((_, reject) => { rejectRemoval = reject; }));
    renderBuilder(value);
    const taskOne = screen.getByRole("group", { name: "Writing Task 1" });

    fireEvent.click(within(taskOne).getByRole("button", { name: "Remove image" }));
    await waitFor(() => expect(updateWritingTask).toHaveBeenCalledTimes(1));
    fireEvent.change(within(taskOne).getByLabelText("Prompt"), { target: { value: "New text entered during failed removal." } });
    await act(async () => { rejectRemoval(new Error("remove failed")); });

    expect(await within(taskOne).findByAltText("Writing Task 1 reference")).toBeInTheDocument();
    expect(within(taskOne).getByLabelText("Prompt")).toHaveValue("New text entered during failed removal.");
  });
});
