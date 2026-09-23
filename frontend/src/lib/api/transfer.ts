import { z } from "zod";
import { apiRequest, apiResponse } from "./client";

const importResultSchema = z.object({
  imported_tests: z.array(z.object({ test_id: z.string().uuid(), title: z.string() })),
  version_count: z.number().int().nonnegative(),
  asset_count: z.number().int().nonnegative(),
});

export type TransferImportResult = z.infer<typeof importResultSchema>;

export async function exportTests(testIds: string[]): Promise<{ blob: Blob; filename: string }> {
  const response = await apiResponse("/transfer/export", {
    method: "POST",
    body: JSON.stringify({ test_ids: testIds }),
  });
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "ielts-tests.zip";
  return { blob: await response.blob(), filename };
}

export async function importTests(file: File): Promise<TransferImportResult> {
  const body = new FormData();
  body.append("file", file);
  return importResultSchema.parse(await apiRequest<unknown>("/transfer/import", { method: "POST", body }));
}
