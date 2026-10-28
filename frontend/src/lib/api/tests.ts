import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { testCoverSchema, testSchema, versionDetailSchema, type TestSummary, type VersionDetail } from "./schema";

const createTestInput = z.object({
  title: z.string().trim().min(1).max(240),
  description: z.string().trim().max(4000).optional(),
});
const updateTestInput = z.object({
  title: z.string().trim().min(1).max(240).optional(),
  description: z.string().trim().max(4000).nullable().optional().transform((value) => value === "" ? null : value),
});

export async function getTests(options?: { archived?: boolean; publicOnly?: boolean; includeDetails?: boolean }, request: ApiRequester = apiRequest): Promise<TestSummary[]> {
  const parameters = new URLSearchParams();
  if (options?.archived) parameters.set("archived", "true");
  if (options?.publicOnly) parameters.set("public_only", "true");
  if (options?.includeDetails) parameters.set("include_details", "true");
  const query = parameters.size ? `?${parameters.toString()}` : "";
  return z.array(testSchema).parse(await request<unknown>(`/tests${query}`));
}

export async function getTest(testId: string, request: ApiRequester = apiRequest): Promise<TestSummary> {
  return testSchema.parse(await request<unknown>(`/tests/${testId}`));
}

export async function createTest(input: z.infer<typeof createTestInput>): Promise<TestSummary> {
  const body = createTestInput.parse(input);
  return testSchema.parse(
    await apiRequest<unknown>("/tests", {
      method: "POST",
      body: JSON.stringify({ ...body, create_initial_draft: true }),
    }),
  );
}

export async function updateTest(testId: string, input: z.input<typeof updateTestInput>, request: ApiRequester = apiRequest): Promise<TestSummary> {
  const body = updateTestInput.parse(input);
  return testSchema.parse(await request<unknown>(`/tests/${testId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  }));
}

export async function getVersion(versionId: string, request: ApiRequester = apiRequest, options?: { publicOnly?: boolean }): Promise<VersionDetail> {
  const query = options?.publicOnly ? "?public_only=true" : "";
  return versionDetailSchema.parse(await request<unknown>(`/test-versions/${versionId}${query}`));
}

export async function cloneVersion(testId: string, sourceVersionId: string): Promise<VersionDetail> {
  return versionDetailSchema.parse(
    await apiRequest<unknown>(`/tests/${testId}/versions`, {
      method: "POST",
      body: JSON.stringify({ source_version_id: sourceVersionId }),
    }),
  );
}

export async function validateVersion(versionId: string) {
  return apiRequest<{ valid: boolean; errors: Array<{ path: string; message: string }>; warnings: Array<{ path: string; message: string }> }>(
    `/test-versions/${versionId}/validate`,
    { method: "POST" },
  );
}

export async function publishVersion(versionId: string): Promise<VersionDetail> {
  return versionDetailSchema.parse(
    await apiRequest<unknown>(`/test-versions/${versionId}/publish`, { method: "POST" }),
  );
}

export async function deleteTest(
  testId: string,
): Promise<{ test_id: string; action: "DELETED" | "ARCHIVED" }> {
  return apiRequest(`/tests/${testId}`, { method: "DELETE" });
}

export async function restoreTest(testId: string): Promise<TestSummary> {
  return testSchema.parse(
    await apiRequest<unknown>(`/tests/${testId}/restore`, { method: "POST" }),
  );
}

export async function permanentlyDeleteTest(testId: string): Promise<void> {
  await apiRequest(`/tests/${testId}/permanent`, { method: "DELETE" });
}

export async function deleteDraft(testId: string, versionId: string): Promise<void> {
  await apiRequest(`/tests/${testId}/versions/${versionId}`, { method: "DELETE" });
}

export async function uploadTestCover(testId: string, file: File) {
  const body = new FormData();
  body.set("file", file);
  return testCoverSchema.parse(await apiRequest<unknown>(`/tests/${encodeURIComponent(testId)}/cover`, { method: "POST", body }));
}

export async function removeTestCover(testId: string): Promise<void> {
  await apiRequest(`/tests/${encodeURIComponent(testId)}/cover`, { method: "DELETE" });
}
