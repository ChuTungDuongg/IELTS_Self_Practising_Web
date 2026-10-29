import { expect, test } from "@playwright/test";
import {
  apiBase, assertPresentationPreviews, captureBrowserErrors, cleanUpFixture, createPublishedExam,
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
    await page.getByRole("article").filter({ has: page.getByRole("button", { name: "Start Listening" }) }).getByLabel("Practice timer").selectOption("unlimited");
    await page.getByRole("button", { name: "Start Listening" }).click();
    await expect(page.getByRole("radio", { name: "Practice", exact: true })).toBeChecked();
    await assertPresentationPreviews(page, "LISTENING");
    await page.getByRole("button", { name: "Continue with this interface" }).click();
    await expect(page).toHaveURL(/\/attempt\/[0-9a-f-]+$/);
    const attemptId = page.url().split("/").at(-1)!;

    const player = page.getByLabel("Listening audio player");
    await expect(player).toBeVisible();
    await expect(page.getByRole("link", { name: "BandPilot home", exact: true })).toBeVisible();
    await expect(page.locator(".app-header time")).toHaveText(/\d{2}:\d{2}:\d{2}GMT\+7/);
    const viewport = page.viewportSize()!;
    const runnerBounds = (await page.locator(".listening-attempt").boundingBox())!;
    const headerBounds = (await page.locator(".app-header").boundingBox())!;
    expect(runnerBounds.y).toBeGreaterThanOrEqual(headerBounds.y + headerBounds.height);
    expect(runnerBounds.y + runnerBounds.height).toBeLessThanOrEqual(viewport.height + 1);
    const navigationBounds = (await page.locator("[data-practice-bottom-navigation]").boundingBox())!;
    expect(Math.abs(navigationBounds.x + navigationBounds.width / 2 - viewport.width / 2)).toBeLessThan(3);
    const exit = page.getByRole("button", { name: "Pause & exit" });
    const exitBounds = (await exit.boundingBox())!;
    const iconBounds = (await exit.locator("svg").boundingBox())!;
    expect(Math.abs(exitBounds.y + exitBounds.height / 2 - iconBounds.y - iconBounds.height / 2)).toBeLessThan(1);
    const play = player.getByRole("button", { name: "Play audio" });
    const originalColor = await play.evaluate(element => getComputedStyle(element).backgroundColor);
    const nextAccent = await page.evaluate(() => document.documentElement.dataset.accent === "orange" ? "Blue" : "Orange");
    await page.getByRole("button", { name: "Personalization", exact: true }).click();
    const personalization = page.getByRole("dialog", { name: "Personalization" });
    await personalization.getByRole("button", { name: nextAccent, exact: true }).click();
    await personalization.getByRole("button", { name: "Close Personalization" }).click();
    await expect.poll(() => play.evaluate(element => getComputedStyle(element).backgroundColor)).not.toBe(originalColor);
    expect(await play.evaluate(element => getComputedStyle(element).borderRadius)).toBe("50%");
    await expect(player.locator("audio")).toHaveAttribute("src", /\/assets\/[0-9a-f-]+\/content$/);
    await expect(player.getByRole("button", { name: "Play audio" })).toBeVisible();
    await expect(player.getByLabel("Audio seek")).toBeEnabled();
    await expect(player.getByRole("button", { name: "Rewind 5 seconds", exact: true })).toBeEnabled();
    await expect(player.getByRole("button", { name: "Forward 5 seconds", exact: true })).toBeEnabled();
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
