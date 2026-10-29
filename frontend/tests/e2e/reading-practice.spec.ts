import { expect, test } from "@playwright/test";
import { assertPresentationPreviews, captureBrowserErrors, cleanUpFixture, createPublishedExam, registerFixtureLearner, signInFixtureAdmin } from "./exam-fixtures";

test("Reading Practice keeps answers through resizing, highlighting, refresh and mobile panels", async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD,
    "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the isolated fixture administrator.");
  const assertNoBrowserErrors = captureBrowserErrors(page);
  await signInFixtureAdmin(request);
  const exam = await createPublishedExam(request, ["READING"]);
  let learnerId: string | undefined;
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    learnerId = (await registerFixtureLearner(page)).id;
    await page.goto(`/library/${exam.versionId}`);
    await page.getByRole("button", { name: "Start Reading", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Choose your interface" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "Practice", exact: true })).toBeChecked();
    await assertPresentationPreviews(page, "READING");
    await page.getByRole("button", { name: "Continue with this interface" }).click();
    await expect(page).toHaveURL(/\/attempt\/[0-9a-f-]+$/);
    const attemptUrl = page.url();
    // Next can retain a hidden streamed SSR fragment while the visible runner hydrates.
    const runner = page.getByRole("main");
    await expect(runner).toHaveCount(1);
    await expect(runner).toHaveClass(/reading-exam/);
    await expect(runner).toHaveAttribute("data-presentation", "PRACTICE");
    await expect(page.getByRole("link", { name: "BandPilot home", exact: true })).toBeVisible();
    const header = page.getByRole("banner");
    await expect(header.locator("time")).toHaveText(/\d{2}:\d{2}:\d{2}GMT\+7/);
    const headerBounds = (await header.boundingBox())!;
    const runnerBounds = (await runner.boundingBox())!;
    expect(runnerBounds.y).toBeGreaterThanOrEqual(headerBounds.y + headerBounds.height);
    expect(runnerBounds.y + runnerBounds.height).toBeLessThanOrEqual(901);
    const navigationBounds = (await runner.locator("[data-practice-bottom-navigation]").boundingBox())!;
    expect(Math.abs(navigationBounds.x + navigationBounds.width / 2 - 720)).toBeLessThan(3);
    const firstControls = (await runner.locator(".exam-footer-navigation").boundingBox())!;
    const submitBounds = (await page.getByRole("button", { name: "Submit answers", exact: true }).boundingBox())!;
    expect(Math.abs((firstControls.x + submitBounds.x + submitBounds.width) / 2 - 720)).toBeLessThan(3);
    const divider = runner.getByRole("separator", { name: "Resize passage and questions" });
    await expect(divider).toBeVisible();
    await expect(divider).toHaveAttribute("aria-valuenow", "50");
    const passage = runner.locator(".exam-passage");
    const questions = runner.locator(".exam-questions");
    const before = await passage.boundingBox();
    await divider.focus();
    await page.keyboard.press("Shift+ArrowRight");
    await expect(divider).toHaveAttribute("aria-valuenow", "60");
    expect((await passage.boundingBox())!.width).toBeGreaterThan(before!.width);
    for (const pane of [passage, questions]) expect(await pane.evaluate(element => getComputedStyle(element).overflowY)).toBe("auto");
    await page.getByRole("radio", { name: "TRUE", exact: true }).check();

    // A single native pointer selection must expose the highlight action.
    const word = await passage.locator(".exam-passage-body [data-highlight-target]").first().evaluate(element => {
      const range = document.createRange();
      range.setStart(element.firstChild!, 0); range.setEnd(element.firstChild!, 3);
      const rect = range.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    });
    await page.mouse.move(word.x + 1, word.y + word.height / 2);
    await page.mouse.down();
    await page.mouse.move(word.x + word.width - 1, word.y + word.height / 2, { steps: 6 });
    await page.mouse.up();
    await page.getByRole("dialog", { name: "Create highlight" }).getByRole("button", { name: "Highlight", exact: true }).click();
    await expect(passage.locator("mark")).toHaveText("The");
    await expect(page.getByRole("radio", { name: "TRUE", exact: true })).toBeChecked();
    await expect(runner.locator(".exam-save-state")).toHaveText("Saved");
    await page.reload();
    await expect(page).toHaveURL(attemptUrl);
    await expect(runner).toHaveCount(1);
    await expect(runner).toHaveAttribute("data-presentation", "PRACTICE");
    await expect(page.getByRole("radio", { name: "TRUE", exact: true })).toBeChecked();
    await expect(passage.locator("mark")).toHaveText("The");

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(divider).toBeHidden();
    await runner.locator(".reading-pane-switch").getByRole("button", { name: "Questions", exact: true }).click();
    await expect(questions).toBeVisible();
    await expect(passage).toBeHidden();
    await expect(page.getByRole("radio", { name: "TRUE", exact: true })).toBeChecked();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Submit answers", exact: true }).click();
    await expect(page).toHaveURL(/\/review\//);
    assertNoBrowserErrors();
  } finally {
    await cleanUpFixture(request, exam, learnerId);
  }
});
