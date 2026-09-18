import { z } from "zod";
import { apiRequest } from "./client";
import { testSchema, versionDetailSchema, type TestSummary, type VersionDetail } from "./schema";

const createTestInput = z.object({
  title: z.string().trim().min(1).max(240),
  description: z.string().trim().max(4000).optional(),
});

export async function getTests(): Promise<TestSummary[]> {
  return z.array(testSchema).parse(await apiRequest<unknown>("/tests"));
}

export async function getTest(testId: string): Promise<TestSummary> {
  return testSchema.parse(await apiRequest<unknown>(`/tests/${testId}`));
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

export async function getVersion(versionId: string): Promise<VersionDetail> {
  return versionDetailSchema.parse(await apiRequest<unknown>(`/test-versions/${versionId}`));
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
  return apiRequest<{ valid: boolean; errors: Array<{ path: string; message: string }> }>(
    `/test-versions/${versionId}/validate`,
    { method: "POST" },
  );
}

export async function publishVersion(versionId: string): Promise<VersionDetail> {
  return versionDetailSchema.parse(
    await apiRequest<unknown>(`/test-versions/${versionId}/publish`, { method: "POST" }),
  );
}
