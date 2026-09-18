import { expect, test } from "@playwright/test";

test("authors, publishes, takes, and reviews a fictional Reading test", async ({ page }) => {
  const title = `E2E Reading ${Date.now()}`;
  await page.goto("/admin/tests/new");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Description").fill("Fictional end-to-end Reading workflow.");
  await page.getByRole("button", { name: "Create draft" }).click();

  await page.getByRole("link", { name: /Version 1/ }).click();
  await page.getByRole("button", { name: "Create Reading module" }).click();
  await expect(page.getByRole("heading", { name: "Reading Builder" })).toBeVisible();

  await page.getByRole("button", { name: "Add passage" }).click();
  await page.getByLabel("Passage title").fill("A fictional solar laboratory");
  await page.locator("textarea").fill("Solar power reduced emissions at the fictional laboratory.");
  await page.getByRole("button", { name: "Save passage" }).click();

  await page.getByRole("button", { name: "Add question group" }).click();
  await page.getByLabel("Prompt").fill("What reduced emissions at the laboratory?");
  await page.getByRole("button", { name: "Save group" }).click();

  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Version is valid.")).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Version published and frozen.")).toBeVisible();

  await page.getByRole("link", { name: "Library", exact: true }).click();
  const card = page.locator("article").filter({ hasText: title });
  await card.getByLabel("Timer").selectOption("2400");
  await card.getByRole("button", { name: "Start Reading" }).click();

  await page.getByLabel(/A\. Option A/).check();
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("Score 1 / 1")).toBeVisible();
  await expect(page.getByText(/Correct: A/)).toBeVisible();
});
