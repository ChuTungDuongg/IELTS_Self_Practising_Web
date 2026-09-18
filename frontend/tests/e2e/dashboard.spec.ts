import { expect, test } from "@playwright/test";

test("shows the application shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Practice with focus/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Builder", exact: true })).toBeVisible();
});
