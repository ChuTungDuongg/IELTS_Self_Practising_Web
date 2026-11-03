import { expect, test } from "@playwright/test";
import { apiBase, captureBrowserErrors, cleanUpFixture, createPublishedExam, signInFixtureAdmin } from "./exam-fixtures";

for (const taskNumber of [1, 2]) {
  test(`focused Task ${taskNumber} saves raw 4.625 and shows band 4.5 after reload and in history`, async ({ page }, testInfo) => {
    test.skip(!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD,
      "Set local fixture administrator credentials.");
    test.setTimeout(90_000);
    const assertNoErrors = captureBrowserErrors(page);
    await page.addInitScript(() => localStorage.setItem("ielts-locale", "en"));
    await signInFixtureAdmin(page.request);
    const exam = await createPublishedExam(page.request, ["WRITING"]);
    let attemptId: string | undefined;
    try {
      const builder = await page.request.get(`${apiBase}/test-versions/${exam.versionId}/builder`);
      expect(builder.ok()).toBe(true);
      const version = await builder.json();
      const task = version.modules.find((module: { module_type: string }) => module.module_type === "WRITING")
        .writing_tasks.find((task: { task_number: number }) => task.task_number === taskNumber);
      const started = await page.request.post(`${apiBase}/attempts`, { data: {
        test_version_id: exam.versionId, module: "WRITING", timer: { mode: "COUNT_UP" },
        scope: "FOCUSED_UNIT", focused_unit: { kind: "WRITING_TASK", id: task.id },
      } });
      expect(started.ok()).toBe(true);
      attemptId = (await started.json()).attempt_id;
      expect((await page.request.put(`${apiBase}/attempts/${attemptId}/writing/${task.id}`, {
        data: { content: "This is a fictional saved response for a scoring presentation regression.", expected_revision: 0 },
      })).ok()).toBe(true);
      expect((await page.request.post(`${apiBase}/attempts/${attemptId}/submit`)).ok()).toBe(true);
      await page.goto(`/review/${attemptId}`);
      // Production streaming can retain a hidden SSR copy while the visible review hydrates.
      const review = page.locator(".writing-review:visible");
      await expect(review).toHaveCount(1);
      const assessment = review.getByRole("region", { name: `Task ${taskNumber} assessment`, exact: true });
      const criteria = [taskNumber === 1 ? "TA" : "TR", "CC", "LR", "GRA"];
      const values = ["5.0", "5.0", "4.0", "4.5"];
      for (const [index, criterion] of criteria.entries()) {
        await assessment.getByRole("combobox", { name: `Task ${taskNumber} ${criterion}`, exact: true }).selectOption(values[index]);
      }
      const savedResponse = page.waitForResponse(response => response.request().method() === "PUT"
        && response.url().endsWith(`/writing-scores/${task.id}`));
      await assessment.getByRole("button", { name: `Save Task ${taskNumber} scores`, exact: true }).click();
      const saved = await (await savedResponse).json();
      expect(saved.tasks[0].score).toMatchObject({ ta: 5, cc: 5, lr: 4, gra: 4.5, overall: 4.625, task_band: 4.5 });
      expect(saved.band_score).toBeNull();
      await expect(review.locator(".review-score b")).toHaveText("4.5");
      await page.reload();
      await expect(review).toHaveCount(1);
      await expect(review.locator(".review-score b")).toHaveText("4.5");
      await expect(assessment.locator(".writing-assessment-card-heading strong")).toHaveText("Estimated task band 4.5");
      for (const [index, criterion] of criteria.entries()) {
        await expect(assessment.getByRole("combobox", { name: `Task ${taskNumber} ${criterion}`, exact: true })).toHaveValue(values[index]);
      }
      for (const [name, viewport] of [
        ["desktop", { width: 1440, height: 1000 }],
        ["mobile", { width: 390, height: 844 }],
      ] as const) {
        await page.setViewportSize(viewport);
        await page.evaluate(() => window.scrollTo(0, 0));
        await expect(review.locator(".review-score b")).toBeVisible();
        const screenshot = testInfo.outputPath(`task-${taskNumber}-${name}.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
        await testInfo.attach(name, { path: screenshot, contentType: "image/png" });
      }
      await page.goto("/history");
      await page.getByRole("tab", { name: "Focused practice" }).click();
      await expect(page.getByTestId(`history-score-${attemptId}`).filter({ visible: true })).toHaveText("Estimated task band 4.5");
      assertNoErrors();
    } finally {
      if (attemptId) await page.request.delete(`${apiBase}/attempts/${attemptId}`);
      await cleanUpFixture(page.request, exam);
    }
  });
}
