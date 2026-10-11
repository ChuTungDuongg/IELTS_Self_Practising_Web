import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { TeacherVersionActions } from "@/features/classrooms/teacher-version-actions";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { cloneVersion, publishVersion } from "@/lib/api/tests";
import { submitModeration, cancelModeration, type ModerationRequest } from "@/lib/api/content-governance";
import type { BuilderVersion } from "@/lib/api/builder";
import { renderWithLocale } from "./locale-test-utils";

const navigation = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
vi.mock("@/lib/api/tests", async original => ({ ...await original<object>(), cloneVersion: vi.fn(), publishVersion: vi.fn() }));
vi.mock("@/lib/api/content-governance", async original => ({ ...await original<object>(), submitModeration: vi.fn(), cancelModeration: vi.fn() }));
const version: BuilderVersion = { id: "version", test_id: "test", test_title: "Fictional", version_number: 1, status: "DRAFT", modules: [] };
const pending: ModerationRequest = { id: "request", test_version_id: version.id, scope: "PUBLIC", status: "PENDING", submitted_by_user_id: "teacher", submitted_at: "now", submit_note: null, reviewed_by_user_id: null, reviewed_at: null, review_note: null, revoked_at: null, revoked_by_user_id: null, revoke_reason: null };
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });

it("teacher requests review rather than publishing through ADMIN", async () => {
  vi.mocked(submitModeration).mockResolvedValue(pending);
  renderWithLocale(<BuilderLifecycleProvider><TeacherVersionActions version={version} requests={[]} /></BuilderLifecycleProvider>);
  expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Request review" }));
  await waitFor(() => expect(submitModeration).toHaveBeenCalledWith(version.id, "CLASSROOM", ""));
  expect(publishVersion).not.toHaveBeenCalled();
});

it("pending review shows a lock and supports cancellation", async () => {
  vi.mocked(cancelModeration).mockResolvedValue({ ...pending, status: "CANCELLED" });
  renderWithLocale(<BuilderLifecycleProvider><TeacherVersionActions version={version} requests={[pending]} /></BuilderLifecycleProvider>);
  expect(screen.getByText("Content is locked while review is pending.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel request" }));
  await waitFor(() => expect(cancelModeration).toHaveBeenCalledWith(pending.id));
});

it("a published immutable source can create a separate draft while PUBLIC review is pending", async () => {
  vi.mocked(cloneVersion).mockResolvedValue({ id: "new", test_id: "test", test_title: "Fictional", version_number: 2, status: "DRAFT", created_at: "now", published_at: null, modules: [] });
  renderWithLocale(<BuilderLifecycleProvider><TeacherVersionActions version={{ ...version, status: "PUBLISHED" }} requests={[pending]} /></BuilderLifecycleProvider>);
  const edit = screen.getByRole("button", { name: "Edit" });
  expect(edit).toBeEnabled();
  fireEvent.click(edit);
  await waitFor(() => expect(cloneVersion).toHaveBeenCalledWith("test", "version"));
  expect(navigation.push).toHaveBeenCalledWith("/teacher/tests/test/versions/new/edit");
});
