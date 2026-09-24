import { expect, test } from "@playwright/test";
import {
  apiBase, captureBrowserErrors, cleanUpFixture, createPublishedExam,
  registerFixtureLearner, signInFixtureAdmin,
} from "./exam-fixtures";

type Session = {
  status: string;
  attempts: Array<{ attempt_id: string; module: string; status: string }>;
};

test("completes fictional Full Mock in Listening, Reading, Writing order and unlocks review", async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD,
    "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");
  const assertNoBrowserErrors = captureBrowserErrors(page);
  await signInFixtureAdmin(request);
  const exam = await createPublishedExam(request, ["LISTENING", "READING", "WRITING"]);
  let learnerId: string | undefined;
  try {
    learnerId = (await registerFixtureLearner(page)).id;
    await page.goto(`/library/${exam.versionId}`);
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
    await page.getByRole("button", { name: "Start Full Mock" }).click();
    await expect(page).toHaveURL(/\/attempt\/[0-9a-f-]+$/);
    const listeningId = page.url().split("/").at(-1)!;
    await expect(page.getByText("LISTENING · SECTION 1")).toBeVisible();
    await expect(page.getByLabel("Listening audio player").getByLabel("Audio seek")).toBeDisabled();
    await expect(page.getByLabel("Listening audio player").getByLabel("Playback speed")).toBeDisabled();
    const firstAttempt = await page.request.get(`${apiBase}/attempts/${listeningId}`);
    expect(firstAttempt.ok()).toBe(true);
    const sessionId = (await firstAttempt.json() as { test_session_id: string }).test_session_id;
    expect(sessionId).toBeTruthy();
    const sessionState = async (): Promise<Session> => {
      const response = await page.request.get(`${apiBase}/test-sessions/${sessionId}`);
      expect(response.ok()).toBe(true);
      return await response.json() as Session;
    };
    expect((await sessionState()).attempts.map((attempt) => attempt.module)).toEqual(["LISTENING"]);
    const earlyAdvance = await page.request.post(`${apiBase}/test-sessions/${sessionId}/advance`);
    expect(earlyAdvance.status()).toBe(409);
    await page.getByRole("radio", { name: "TRUE" }).check();
    await page.getByRole("button", { name: "Submit answers" }).click();
    await expect(page).toHaveURL(`/test-session/${sessionId}`);
    await expect(page.getByRole("heading", { name: "Listening complete" })).toBeVisible();

    const locked = await page.request.get(`${apiBase}/attempts/${listeningId}/listening-review`);
    expect(locked.status()).toBe(409);
    expect((await locked.json() as { code: string }).code).toBe("FULL_MOCK_REVIEW_LOCKED");
    const lockedPage = await page.request.get(`${new URL(page.url()).origin}/review/${listeningId}`);
    expect(lockedPage.status()).toBe(404);
    await page.goto("/history");
    const inProgressCard = page.locator(".history-group-card").filter({ hasText: exam.title });
    await expect(inProgressCard).toContainText("In progress");
    await expect(inProgressCard.getByRole("link", { name: "Review Listening" })).toHaveCount(0);
    await page.goto(`/test-session/${sessionId}`);
    await page.getByRole("button", { name: "Continue to Reading" }).click();
    await expect(page).toHaveURL(/\/attempt\/[0-9a-f-]+$/);
    await expect(page.getByText("Reading passage 1")).toBeVisible();
    expect((await sessionState()).attempts.map((attempt) => attempt.module)).toEqual(["LISTENING", "READING"]);
    const readingId = page.url().split("/").at(-1)!;
    await page.getByRole("radio", { name: "TRUE" }).check();
    await page.getByRole("button", { name: "Submit answers" }).click();
    await expect(page).toHaveURL(`/test-session/${sessionId}`);
    await expect(page.getByRole("heading", { name: "Reading complete" })).toBeVisible();
    expect((await sessionState()).attempts.map((attempt) => attempt.module)).toEqual(["LISTENING", "READING"]);
    const readingLocked = await page.request.get(`${apiBase}/attempts/${readingId}/reading-review`);
    expect(readingLocked.status()).toBe(409);

    await page.getByRole("button", { name: "Continue to Writing" }).click();
    await expect(page).toHaveURL(/\/attempt\/[0-9a-f-]+$/);
    await expect(page.getByText("WRITING · TASK 1")).toBeVisible();
    expect((await sessionState()).attempts.map((attempt) => attempt.module)).toEqual(["LISTENING", "READING", "WRITING"]);
    await page.getByRole("textbox", { name: "Response for Task 1" }).fill("The fictional chart shows a steady rise in library visitors.");
    await page.getByRole("tab", { name: /Task 2/ }).click();
    await page.getByRole("textbox", { name: "Response for Task 2" }).fill("Fictional public gardens give residents a peaceful shared place.");
    await page.getByRole("button", { name: "Submit Writing" }).click();
    await expect(page).toHaveURL(`/test-session/${sessionId}`);
    await expect(page.getByText("Full Mock complete")).toBeVisible();
    await expect.poll(async () => (await sessionState()).status).toBe("COMPLETED");
    const unlocked = await page.request.get(`${apiBase}/attempts/${listeningId}/listening-review`);
    expect(unlocked.ok()).toBe(true);
    const unlockedPage = await page.request.get(`${new URL(page.url()).origin}/review/${listeningId}`);
    expect(unlockedPage.ok()).toBe(true);

    await page.goto("/history");
    await expect(page.getByRole("heading", { name: "Full Mock sessions" })).toBeVisible();
    const completedCard = page.locator(".history-group-card").filter({ hasText: exam.title });
    await expect(completedCard).toContainText("Full Mock");
    await expect(completedCard.getByRole("link", { name: "Review Listening" })).toBeVisible();
    await completedCard.getByRole("link", { name: "Review Listening" }).click();
    await expect(page).toHaveURL(`/review/${listeningId}`);
    await expect(page.locator(".listening-review")).toBeVisible();
    assertNoBrowserErrors();
  } finally {
    await cleanUpFixture(request, exam, learnerId);
  }
});
