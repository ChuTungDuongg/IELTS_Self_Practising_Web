import { randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

test("ADMIN exports a selected authored test through browser cookie authentication", async ({ page }) => {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  test.skip(!email || !password, "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");

  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();

  const title = `E2E Transfer ${randomBytes(6).toString("hex")}`;
  const created = await page.request.post(`${apiBase}/tests`, {
    data: { title, description: "Fictional local transfer export fixture.", create_initial_draft: true },
  });
  expect(created.status()).toBe(201);
  const testRecord = await created.json() as { id: string };

  try {
    await page.goto("/transfer");
    await expect(page).toHaveURL("/transfer");
    await expect(page.getByRole("heading", { name: "Export authored tests" })).toBeVisible();
    await page.getByLabel(`Select ${title}`).check();

    const [response, download] = await Promise.all([
      page.waitForResponse((candidate) => candidate.url().endsWith("/transfer/export") && candidate.request().method() === "POST"),
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Export selected" }).click(),
    ]);

    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual({ test_ids: [testRecord.id] });
    expect(response.headers()["content-type"]).toContain("application/zip");
    expect(download.suggestedFilename()).toMatch(/^ielts-tests-\d{4}-\d{2}-\d{2}\.zip$/);
    expect(await download.path()).toBeTruthy();
    await expect(page).toHaveURL("/transfer");
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toHaveCount(0);
    await expect(page.getByText("AUTHENTICATION_REQUIRED")).toHaveCount(0);
  } finally {
    const deleted = await page.request.delete(`${apiBase}/tests/${testRecord.id}`);
    expect(deleted.ok()).toBe(true);
  }
});
