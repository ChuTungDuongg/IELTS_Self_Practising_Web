import { expect, test } from "@playwright/test";
import {
  apiBase, captureBrowserErrors, cleanUpFixture, createPublishedExam,
  registerFixtureLearner, signInFixtureAdmin,
} from "./exam-fixtures";

test("takes and reviews a fictional Listening practice attempt", async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD,
    "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");
  const assertNoBrowserErrors = captureBrowserErrors(page);
  await signInFixtureAdmin(request);
  const exam = await createPublishedExam(request, ["LISTENING"]);
  let learnerId: string | undefined;
  try {
    learnerId = (await registerFixtureLearner(page)).id;
    await page.goto(`/library/${exam.versionId}`);
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
    await expect(page.getByRole("heading", { name: exam.title })).toBeVisible();
    await page.getByLabel("Practice timer").selectOption("unlimited");
    await page.getByRole("button", { name: "Start Listening" }).click();
    await expect(page).toHaveURL(/\/attempt\/[0-9a-f-]+$/);
    const attemptId = page.url().split("/").at(-1)!;

    const player = page.getByLabel("Listening audio player");
    await expect(player).toBeVisible();
    await expect(player.locator("audio")).toHaveAttribute("src", /\/assets\/[0-9a-f-]+\/content$/);
    await expect(player.getByRole("button", { name: "Play audio" })).toBeVisible();
    await expect(player.getByLabel("Audio seek")).toBeEnabled();
    await expect(player.getByRole("button", { name: "Seek forward 10 seconds" })).toBeEnabled();
    await player.getByLabel("Playback speed").selectOption("1.25");
    await expect(player.getByLabel("Playback speed")).toHaveValue("1.25");

    await page.getByRole("radio", { name: "TRUE" }).check();
    await page.getByRole("button", { name: "Section 2", exact: true }).click();
    await expect(page.getByText("Fictional sound statement 2.")).toBeVisible();
    await page.getByRole("radio", { name: "FALSE" }).check();
    await page.getByRole("button", { name: "Go to question 1" }).click();
    await expect(page.getByRole("radio", { name: "TRUE" })).toBeChecked();
    await page.getByRole("button", { name: "Go to question 2" }).click();
    await expect(page.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    await expect(page.getByRole("radio", { name: "FALSE" })).toBeChecked();

    await expect.poll(async () => {
      const response = await page.request.get(`${apiBase}/attempts/${attemptId}/exam`);
      if (!response.ok()) return [];
      const saved = await response.json() as { listening_parts: Array<{ question_groups: Array<{ questions: Array<{ value: string | null }> }> }> };
      return saved.listening_parts.flatMap((part) => part.question_groups.flatMap((group) => group.questions.map((question) => question.value)));
    }).toEqual(["TRUE", "FALSE"]);
    await expect(page.locator(".exam-save-state")).toHaveText("Saved");

    await page.getByRole("button", { name: "Submit answers" }).click();
    await expect(page).toHaveURL(`/review/${attemptId}`);
    await expect(page.locator(".listening-review")).toBeVisible();
    await expect(page.getByText("Your answer: TRUE")).toBeVisible();
    await page.locator(".listening-part-tabs").getByRole("button", { name: /Section 2/ }).click();
    await expect(page.getByText("Your answer: FALSE")).toBeVisible();
    assertNoBrowserErrors();
  } finally {
    await cleanUpFixture(request, exam, learnerId);
  }
});
