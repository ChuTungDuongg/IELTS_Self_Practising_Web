import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { testSchema, versionDetailSchema, type TestSummary, type VersionDetail } from "./schema";

const createTestInput = z.object({
  title: z.string().trim().min(1).max(240),
  description: z.string().trim().max(4000).optional(),
});

export async function getTests(options?: { archived?: boolean }, request: ApiRequester = apiRequest): Promise<TestSummary[]> {
  const query = options?.archived ? "?archived=true" : "";
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

export async function getVersion(versionId: string, request: ApiRequester = apiRequest): Promise<VersionDetail> {
  return versionDetailSchema.parse(await request<unknown>(`/test-versions/${versionId}`));
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
