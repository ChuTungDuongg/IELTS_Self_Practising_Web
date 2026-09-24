import { expect, test } from "@playwright/test";
import {
  apiBase, captureBrowserErrors, cleanUpFixture, createPublishedExam,
  registerFixtureLearner, signInFixtureAdmin,
} from "./exam-fixtures";

test("autosaves, reloads, submits, and reviews both fictional Writing tasks", async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD,
    "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");
  const assertNoBrowserErrors = captureBrowserErrors(page);
  await signInFixtureAdmin(request);
  const exam = await createPublishedExam(request, ["WRITING"]);
  let learnerId: string | undefined;
  try {
    learnerId = (await registerFixtureLearner(page)).id;
    await page.goto(`/library/${exam.versionId}`);
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
    await expect(page.getByRole("heading", { name: exam.title })).toBeVisible();
    await page.getByLabel("Practice timer").selectOption("unlimited");
    await page.getByRole("button", { name: "Start Writing" }).click();
    await expect(page).toHaveURL(/\/attempt\/[0-9a-f-]+$/);
    const attemptId = page.url().split("/").at(-1)!;

    const task1 = "The fictional library received more visitors on Friday than on Monday.";
    const task2 = "Fictional towns should build public gardens because residents can meet and enjoy nature.";
    await expect(page.getByText("Describe a fictional library's weekly visitor chart.")).toBeVisible();
    await page.getByRole("textbox", { name: "Response for Task 1" }).fill(task1);
    await expect(page.getByRole("tab", { name: /Task 1/ })).toContainText(`${task1.split(" ").length} words`);
    await page.getByRole("tab", { name: /Task 2/ }).click();
    await expect(page.getByText("Explain whether fictional towns should build more public gardens.")).toBeVisible();
    await page.getByRole("textbox", { name: "Response for Task 2" }).fill(task2);
    await expect(page.getByRole("tab", { name: /Task 2/ })).toContainText(`${task2.split(" ").length} words`);
    await page.getByRole("tab", { name: /Task 1/ }).click();
    await expect(page.getByRole("textbox", { name: "Response for Task 1" })).toHaveValue(task1);

    await expect.poll(async () => {
      const response = await page.request.get(`${apiBase}/attempts/${attemptId}/exam`);
      if (!response.ok()) return [];
      const saved = await response.json() as { writing_tasks: Array<{ content: string }> };
      return saved.writing_tasks.map((task) => task.content);
    }).toEqual([task1, task2]);
    await expect(page.locator(".exam-save-state")).toHaveText("Saved");
    await page.reload();
    await expect(page.getByRole("textbox", { name: "Response for Task 1" })).toHaveValue(task1);
    await page.getByRole("tab", { name: /Task 2/ }).click();
    await expect(page.getByRole("textbox", { name: "Response for Task 2" })).toHaveValue(task2);

    await page.getByRole("button", { name: "Submit Writing" }).click();
    await expect(page).toHaveURL(`/review/${attemptId}`);
    await expect(page.locator(".writing-review-response")).toContainText(task1);
    await page.getByRole("tab", { name: /Task 2/ }).click();
    await expect(page.locator(".writing-review-response")).toContainText(task2);
    assertNoBrowserErrors();
  } finally {
    await cleanUpFixture(request, exam, learnerId);
  }
});
