import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { ModuleDurationEditor } from "@/features/test-builder/module-duration-editor";
import { updateModuleDuration, type BuilderModule } from "@/lib/api/builder";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/builder", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/builder")>(),
  updateModuleDuration: vi.fn(),
}));

const moduleRecord: BuilderModule = {
  id: "33333333-3333-4333-8333-333333333333",
  revision: 1,
  module_type: "READING",
  title: "Reading",
  recommended_duration_seconds: 3600,
  audio_asset: null,
  passages: [],
  listening_parts: [],
  writing_tasks: [],
};

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

it("saves a changed module duration in seconds and updates without a reload", async () => {
  vi.useFakeTimers();
  const onPersisted = vi.fn();
  vi.mocked(updateModuleDuration).mockResolvedValue({ ...moduleRecord, revision: 2, recommended_duration_seconds: 3300 });
  render(<BuilderLifecycleProvider><ModuleDurationEditor module={moduleRecord} onPersisted={onPersisted} /></BuilderLifecycleProvider>);
  const input = screen.getByRole("spinbutton", { name: "Recommended duration in minutes" });
  expect(input).toHaveValue(60);
  fireEvent.change(input, { target: { value: "55" } });
  await act(async () => { await vi.advanceTimersByTimeAsync(350); });
  expect(updateModuleDuration).toHaveBeenCalledWith(moduleRecord.id, 1, 3300);
  expect(onPersisted).toHaveBeenCalledWith(expect.objectContaining({ revision: 2, recommended_duration_seconds: 3300 }));
  expect(input).toHaveValue(55);
  expect(refresh).toHaveBeenCalledOnce();
});
