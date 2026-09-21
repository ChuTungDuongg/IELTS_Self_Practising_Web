import { z } from "zod";
import { API_BASE_URL, ApiError, apiRequest } from "./client";

const importResultSchema = z.object({
  imported_tests: z.array(z.object({ test_id: z.string().uuid(), title: z.string() })),
  version_count: z.number().int().nonnegative(),
  asset_count: z.number().int().nonnegative(),
});

export type TransferImportResult = z.infer<typeof importResultSchema>;

export async function exportTests(testIds: string[]): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/transfer/export`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ test_ids: testIds }),
    });
  } catch (error) {
    throw new ApiError("NETWORK_ERROR", "The API is not reachable.", 0, error);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.code ?? "API_ERROR", body?.message ?? "The test package could not be exported.", response.status, body);
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "ielts-tests.zip";
  return { blob: await response.blob(), filename };
}

export async function importTests(file: File): Promise<TransferImportResult> {
  const body = new FormData();
  body.append("file", file);
  return importResultSchema.parse(await apiRequest<unknown>("/transfer/import", { method: "POST", body }));
}
