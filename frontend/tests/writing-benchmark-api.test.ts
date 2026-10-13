import { describe, expect, it, vi } from "vitest";
import { benchmarkList, benchmarkSample, benchmarkSummary, sampleId } from "./writing-benchmark-fixtures";
import { benchmarkSampleSchema, benchmarkSamplePatchSchema, getWritingBenchmarkSummary, listWritingBenchmarkSamples, getWritingBenchmarkSample, createWritingBenchmarkSample, updateWritingBenchmarkSample, completeWritingBenchmarkSample, deleteWritingBenchmarkSample, uploadWritingBenchmarkImage, removeWritingBenchmarkImage, writingBenchmarkImageUrl, exportWritingBenchmarkBundle, benchmarkCompletionIssues } from "@/lib/api/writing-benchmark";
import { ApiError } from "@/lib/api/client";

describe("admin benchmark contracts", () => {
  it("keeps numeric nullable task-specific labels and excludes raw storage keys", () => {
    expect(benchmarkSampleSchema.parse(benchmarkSample()).human_scores).toHaveProperty("ta", null);
    expect(benchmarkSampleSchema.parse(benchmarkSample({ task_number: 2, code: "T2-001", human_scores: { tr: 6, cc: 6, lr: 6.5, gra: 6.5 }, human_overall: 6.5 })).human_overall).toBe(6.5);
    expect(() => benchmarkSampleSchema.parse(benchmarkSample({ task1_image_key: "forged.png" }))).toThrow();
    expect(() => benchmarkSampleSchema.parse(benchmarkSample({ task_number: 2 }))).toThrow();
    expect(() => benchmarkSampleSchema.parse(benchmarkSample({ human_overall: "6.5" }))).toThrow();
  });

  it("rejects forged identity, status, overall and invalid half-band patches", () => {
    for (const edits of [{ id: sampleId }, { task_number: 2 }, { sequence_number: 2 }, { human_overall: 9 }, { task1_image_key: "key" }, { status: "COMPLETE" }, { human_scores: { ta: 6.49 } }, { human_scores: { ta: "6.5" } }]) {
      expect(() => benchmarkSamplePatchSchema.parse({ expected_revision: 1, ...edits })).toThrow();
    }
    expect(benchmarkSamplePatchSchema.parse({ expected_revision: 1, essay: "\r\n 😀 ", human_scores: { ta: null } }).essay).toBe("\r\n 😀 ");
  });

  it("uses lightweight summary/list and authenticated JSON authoring routes", async () => {
    const request = vi.fn();
    request.mockResolvedValueOnce(benchmarkSummary());
    await getWritingBenchmarkSummary(request);
    request.mockResolvedValueOnce([benchmarkList()]);
    await listWritingBenchmarkSamples(1, request);
    request.mockResolvedValueOnce(benchmarkSample());
    await getWritingBenchmarkSample(sampleId, request);
    request.mockResolvedValueOnce(benchmarkSample());
    await createWritingBenchmarkSample(1, request);
    request.mockResolvedValueOnce(benchmarkSample({ revision: 2 }));
    await updateWritingBenchmarkSample(sampleId, { expected_revision: 1, essay: "Fictional essay" }, request);
    request.mockResolvedValueOnce(benchmarkSample({ revision: 3, status: "COMPLETE" }));
    await completeWritingBenchmarkSample(sampleId, 2, request);
    request.mockResolvedValueOnce(null);
    await deleteWritingBenchmarkSample(sampleId, 3, request);
    expect(request.mock.calls.map(([path]) => path)).toEqual(["/admin/writing-benchmark/summary", "/admin/writing-benchmark/samples?task=1", `/admin/writing-benchmark/samples/${sampleId}`, "/admin/writing-benchmark/samples", `/admin/writing-benchmark/samples/${sampleId}`, `/admin/writing-benchmark/samples/${sampleId}/complete`, `/admin/writing-benchmark/samples/${sampleId}?expected_revision=3`]);
    expect(request.mock.calls[4][1]).toMatchObject({ method: "PATCH", body: JSON.stringify({ expected_revision: 1, essay: "Fictional essay" }) });
  });

  it("sends upload multipart with revision and removes through the mutation contract", async () => {
    const request = vi.fn().mockResolvedValue(benchmarkSample({ has_image: true, revision: 2 }));
    const file = new File(["fictional"], "test.png", { type: "image/png" });
    await uploadWritingBenchmarkImage(sampleId, file, 1, request);
    const body = request.mock.calls[0][1].body as FormData;
    expect(body.get("file")).toBe(file);
    expect(body.get("expected_revision")).toBe("1");
    expect(request.mock.calls[0][1].headers).toBeUndefined();
    await removeWritingBenchmarkImage(sampleId, 2, request);
    expect(request).toHaveBeenLastCalledWith(`/admin/writing-benchmark/samples/${sampleId}/image?expected_revision=2`, { method: "DELETE" });
    expect(writingBenchmarkImageUrl(sampleId, 2)).toContain(`/samples/${sampleId}/image?revision=2`);
  });

  it("uses the authenticated binary requester with a fixed safe ZIP name", async () => {
    const responseRequest = vi.fn().mockResolvedValue(new Response("fictional zip", { headers: { "content-type": "application/zip" } }));
    const bundle = await exportWritingBenchmarkBundle(responseRequest);
    expect(responseRequest).toHaveBeenCalledWith("/admin/writing-benchmark/export");
    expect(bundle.filename).toBe("writing-benchmark.zip");
    expect(bundle.blob.size).toBeGreaterThan(0);
  });

  it("preserves safe completion field errors and ordinary ApiError behavior", () => {
    const error = new ApiError("BENCHMARK_INCOMPLETE", "Missing fields", 422, { errors: [{ path: "human_scores.ta", message: "Select a half-band score." }] });
    expect(benchmarkCompletionIssues(error)[0].path).toBe("human_scores.ta");
    expect(benchmarkCompletionIssues(new Error("Other error"))).toEqual([]);
  });
});
