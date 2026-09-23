import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { expect, test } from "@playwright/test";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

test("Pause & Exit reconciles an AFK interruption without lifecycle errors or repeated writes", async ({ page }) => {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  test.skip(!email || !password, "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");

  const pageErrors: string[] = [];
  const mutationRequests: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/attempts/") && ["POST", "PUT", "DELETE"].includes(request.method())) mutationRequests.push(request.url());
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");

  const created = await page.request.post(`${apiBase}/tests`, {
    data: { title: `E2E AFK fixture ${randomUUID().slice(0, 8)}`, description: "Fictional attempt lifecycle fixture.", create_initial_draft: true },
  });
  expect(created.status()).toBe(201);
  const record = await created.json() as { id: string; versions: Array<{ id: string }> };
  const versionId = record.versions[0].id;

  try {
    const moduleResponse = await page.request.post(`${apiBase}/test-versions/${versionId}/modules`, {
      data: { module_type: "READING", title: "Reading", recommended_duration_seconds: 3600 },
    });
    expect(moduleResponse.ok()).toBe(true);
    const passage = await page.request.post(`${apiBase}/test-versions/${versionId}/reading/passages`, {
      data: { title: "A fictional AFK passage", order_index: 0, blocks: [{ id: randomUUID(), type: "paragraph", label: "A", text: "The fictional observatory counts bright stars." }] },
    });
    expect(passage.ok()).toBe(true);
    const passageId = (await passage.json() as { id: string }).id;
    const group = await page.request.post(`${apiBase}/reading/passages/${passageId}/question-groups`, {
      data: { question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: randomUUID(), number: 1, prompt: "The fictional observatory counts stars.", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, order_index: 0 }] },
    });
    expect(group.ok()).toBe(true);
    const validation = await page.request.post(`${apiBase}/test-versions/${versionId}/validate`);
    expect(validation.ok()).toBe(true);
    expect((await validation.json() as { valid: boolean }).valid).toBe(true);
    const publish = await page.request.post(`${apiBase}/test-versions/${versionId}/publish`);
    expect(publish.ok()).toBe(true);

    const started = await page.request.post(`${apiBase}/attempts`, {
      data: { test_version_id: versionId, module: "READING", timer: { mode: "COUNT_UP" } },
    });
    expect(started.ok()).toBe(true);
    const attemptId = (await started.json() as { attempt_id: string }).attempt_id;
    await page.goto(`/attempt/${attemptId}`);
    await expect(page.getByRole("button", { name: "Pause & exit" })).toBeVisible();
    await page.getByRole("button", { name: "Pause & exit" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    const backendDir = path.resolve(process.cwd(), "../backend");
    execFileSync("uv", ["run", "python", "tests/fixtures/set_attempt_inactive.py", attemptId], { cwd: backendDir, stdio: "pipe" });
    await page.getByRole("dialog").getByRole("button", { name: "Pause & exit" }).click();
    await expect(page).toHaveURL(`/review/${attemptId}`);
    const state = await page.request.get(`${apiBase}/attempts/${attemptId}`);
    expect(state.status()).toBe(200);
    expect((await state.json() as { status: string }).status).toBe("INTERRUPTED");
    expect(pageErrors.join("\n")).not.toMatch(/ATTEMPT_FINALIZED|INVALID_ATTEMPT_TRANSITION|ApiError/);
    await expect(page.getByText(/INVALID_ATTEMPT_TRANSITION|ATTEMPT_FINALIZED/)).toHaveCount(0);
    const count = mutationRequests.length;
    await page.waitForTimeout(11_000);
    expect(mutationRequests).toHaveLength(count);
  } finally {
    const deleted = await page.request.delete(`${apiBase}/tests/${record.id}`);
    expect(deleted.ok()).toBe(true);
  }
});
