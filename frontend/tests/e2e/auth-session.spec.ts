import { randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function signIn(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
}

async function expectStoredSession(page: import("@playwright/test").Page) {
  // Deliberately inspect metadata only. Never include JWT values in assertions or logs.
  const metadata = (await page.context().cookies())
    .filter(({ name }) => name === "ielts_access" || name === "ielts_refresh")
    .map(({ name, domain, path, httpOnly, secure, sameSite, expires }) => ({ name, domain, path, httpOnly, secure, sameSite, expires }));
  expect(metadata).toHaveLength(2);
  expect(metadata.map(({ name }) => name).sort()).toEqual(["ielts_access", "ielts_refresh"]);
  for (const cookie of metadata) {
    expect(cookie.domain).toBe("localhost");
    expect(cookie.path).toBe("/");
    expect(cookie.httpOnly).toBe(true);
    expect(cookie.secure).toBe(false);
    expect(cookie.sameSite).toBe("Lax");
    expect(cookie.expires).toBeGreaterThan(Date.now() / 1000);
  }
}

test("USER login persists through navigation, reload, direct URLs, and logout", async ({ page, request }) => {
  const nonce = randomBytes(8).toString("hex");
  const email = `e2e-session-${nonce}@example.com`;
  const password = randomBytes(24).toString("base64url");
  const registration = await request.post(`${apiBase}/auth/register`, {
    data: { email, display_name: "E2E Session User", password },
  });
  expect(registration.ok()).toBe(true);

  await signIn(page, email, password);
  await expect(page.getByText("E2E Session User")).toBeVisible();
  await expectStoredSession(page);

  await page.getByRole("link", { name: "Test library" }).click();
  await expect(page).toHaveURL("/library");
  await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toHaveCount(0);

  await page.reload();
  await expect(page).toHaveURL("/library");
  await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();

  for (const path of ["/", "/history", "/analytics"]) {
    await page.goto(path);
    await expect(page).toHaveURL(path);
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
  }

  await page.context().clearCookies({ name: "ielts_access" });
  await page.goto("/history");
  await expect(page).toHaveURL("/history");
  await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
  await expectStoredSession(page);

  for (const path of [
    "/admin",
    "/admin/tests",
    "/admin/tests/00000000-0000-4000-8000-000000000001/versions/00000000-0000-4000-8000-000000000002/edit",
    "/transfer",
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(path);
    await expect(page.getByRole("heading", { name: "Forbidden" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
  }

  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL("/login");
  const remainingNames = (await page.context().cookies()).map(({ name }) => name);
  expect(remainingNames).not.toContain("ielts_access");
  expect(remainingNames).not.toContain("ielts_refresh");
  await page.goto("/library");
  await expect(page).toHaveURL(/\/login\?next=%2Flibrary$/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("ADMIN reaches dashboard, test library, Builder, and transfer", async ({ page }) => {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  test.skip(!email || !password, "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");

  await signIn(page, email!, password!);
  await expectStoredSession(page);

  for (const path of ["/admin", "/admin/tests", "/transfer"]) {
    await page.goto(path);
    await expect(page).toHaveURL(path);
    await expect(page.getByRole("heading", { name: "Forbidden" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
  }

  const title = `E2E Session Builder ${randomBytes(6).toString("hex")}`;
  const created = await page.request.post(`${apiBase}/tests`, {
    data: { title, description: "Fictional local auth verification fixture.", create_initial_draft: true },
  });
  expect(created.ok()).toBe(true);
  const testRecord = await created.json();
  const versionId = testRecord.versions.find((version: { status: string }) => version.status === "DRAFT")?.id;
  expect(versionId).toBeTruthy();
  try {
    const builderData = await page.request.get(`${apiBase}/test-versions/${versionId}/builder`);
    expect(builderData.status()).toBe(200);
    expect((await builderData.json()).test_id).toBe(testRecord.id);
    await page.goto(`/admin/tests/${testRecord.id}/versions/${versionId}/edit`);
    await expect(page).toHaveURL(`/admin/tests/${testRecord.id}/versions/${versionId}/edit`);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByRole("button", { name: "Logout" })).toBeVisible();
  } finally {
    await page.request.delete(`${apiBase}/tests/${testRecord.id}/versions/${versionId}`);
  }
});
