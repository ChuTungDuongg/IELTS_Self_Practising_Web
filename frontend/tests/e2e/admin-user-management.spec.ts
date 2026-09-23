import { randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

test("ADMIN deactivates and permanently deletes a disposable USER", async ({ page, request }) => {
  const adminEmail = process.env.E2E_ADMIN_EMAIL;
  const adminPassword = process.env.E2E_ADMIN_PASSWORD;
  test.skip(!adminEmail || !adminPassword, "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");

  const suffix = randomBytes(8).toString("hex");
  const displayName = `Disposable ${suffix}`;
  const email = `e2e-delete-${suffix}@example.com`;
  const registration = await request.post(`${apiBase}/auth/register`, {
    data: { email, display_name: displayName, password: randomBytes(24).toString("base64url") },
  });
  expect(registration.ok()).toBe(true);
  const userId = (await registration.json() as { user: { id: string } }).user.id;

  try {
    await page.goto("/login");
    await page.getByLabel("Email").fill(adminEmail!);
    await page.getByLabel("Password").fill(adminPassword!);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL("/");
    const usersMetric = page.locator('a.home-metric[href="/admin"]');
    const initialTotal = Number(await usersMetric.locator(".home-metric-value").textContent());
    expect(initialTotal).toBeGreaterThan(0);

    await page.goto("/admin");
    await page.getByPlaceholder("Search email or name").fill(email);
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByText(email)).toBeVisible();
    await page.getByRole("button", { name: `Deactivate ${displayName}` }).click();
    await expect(page.getByText(email)).toHaveCount(0);

    await page.getByRole("tab", { name: /Deactivated Users/ }).click();
    await expect(page.getByText(email)).toBeVisible();
    await page.getByRole("button", { name: `Delete permanently ${displayName}` }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("cannot be undone");
    await expect(page.getByText(email)).toBeVisible();
    const [deleted] = await Promise.all([
      page.waitForResponse((response) => response.url().endsWith(`/admin/users/${userId}`) && response.request().method() === "DELETE"),
      dialog.getByRole("button", { name: "Delete permanently" }).click(),
    ]);
    expect(deleted.ok()).toBe(true);
    await expect(page.getByText(email)).toHaveCount(0);

    await page.goto("/");
    await expect(usersMetric.locator(".home-metric-value")).toHaveText(String(initialTotal - 1));
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
  } finally {
    // The fixture is isolated and disposable. Clean it up if an assertion failed early.
    const existing = await page.request.get(`${apiBase}/admin/users/${userId}`);
    if (existing.ok()) {
      await page.request.patch(`${apiBase}/admin/users/${userId}`, { data: { is_active: false } });
      await page.request.delete(`${apiBase}/admin/users/${userId}`);
    }
  }
});
