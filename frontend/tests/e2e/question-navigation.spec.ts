import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function group(start: number) {
  return {
    question_type: "true_false_not_given",
    instruction: "Read the fictional statement and choose an answer.",
    config: {},
    order_index: start,
    questions: Array.from({ length: 10 }, (_, index) => {
      const number = start + index;
      return {
        id: randomUUID(), number, prompt: `Fictional navigation statement ${number}.`, config: {},
        answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, order_index: index,
      };
    }),
  };
}

async function clickQuestion(page: Page, number: number, paneSelector: string) {
  const button = page.getByRole("button", { name: `Go to question ${number}`, exact: true });
  const questionId = await button.evaluate((element) => element.parentElement?.getAttribute("data-nav-question-id"));
  expect(questionId).toBeTruthy();
  // A real user can move the strip manually. DOM click avoids Playwright scrolling the page first.
  await button.evaluate((element: HTMLButtonElement) => element.click());
  await expect(button).toHaveAttribute("aria-current", "true");
  await expect.poll(() => page.evaluate(({ paneSelector, questionId }) => {
    const pane = document.querySelector(paneSelector);
    const target = [...(pane?.querySelectorAll<HTMLElement>(".exam-question-target[data-question-id]") ?? [])]
      .find((element) => element.dataset.questionId === questionId);
    if (!pane || !target) return false;
    const paneRect = pane.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    return targetRect.bottom > paneRect.top && targetRect.top < paneRect.bottom;
  }, { paneSelector, questionId })).toBe(true);
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(button).toHaveAttribute("aria-current", "true");
}

test("Reading and Listening footer navigation stays inside its panes across distant questions", async ({ page }) => {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  test.skip(!email || !password, "Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for the local bootstrap administrator.");

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");

  const created = await page.request.post(`${apiBase}/tests`, {
    data: { title: `E2E navigator ${randomUUID().slice(0, 8)}`, description: "Fictional navigation regression fixture.", create_initial_draft: true },
  });
  expect(created.status()).toBe(201);
  const record = await created.json() as { id: string; versions: Array<{ id: string }> };
  const versionId = record.versions[0].id;

  try {
    for (const moduleType of ["READING", "LISTENING"]) {
      const moduleResponse = await page.request.post(`${apiBase}/test-versions/${versionId}/modules`, {
        data: { module_type: moduleType, title: moduleType === "READING" ? "Reading" : "Listening", recommended_duration_seconds: 3600 },
      });
      expect(moduleResponse.ok()).toBe(true);
    }
    for (let index = 0; index < 2; index++) {
      const passage = await page.request.post(`${apiBase}/test-versions/${versionId}/reading/passages`, {
        data: { title: `Fictional passage ${index + 1}`, order_index: index, blocks: [{ id: randomUUID(), type: "paragraph", label: "A", text: "A fictional passage for navigator regression." }] },
      });
      expect(passage.ok()).toBe(true);
      const passageId = (await passage.json() as { id: string }).id;
      for (let local = 0; local < 2; local++) {
        const number = index * 20 + local * 10 + 1;
        const response = await page.request.post(`${apiBase}/reading/passages/${passageId}/question-groups`, { data: group(number) });
        expect(response.ok()).toBe(true);
      }
      const part = await page.request.post(`${apiBase}/test-versions/${versionId}/listening/parts`, {
        data: { title: `Fictional section ${index + 1}`, order_index: index },
      });
      expect(part.ok()).toBe(true);
      const partId = (await part.json() as { id: string }).id;
      for (let local = 0; local < 2; local++) {
        const number = index * 20 + local * 10 + 1;
        const response = await page.request.post(`${apiBase}/listening/parts/${partId}/question-groups`, { data: group(number) });
        expect(response.ok()).toBe(true);
      }
    }
    const validation = await page.request.post(`${apiBase}/test-versions/${versionId}/validate`);
    expect(validation.ok()).toBe(true);
    expect((await validation.json() as { valid: boolean }).valid).toBe(true);
    const publication = await page.request.post(`${apiBase}/test-versions/${versionId}/publish`);
    expect(publication.ok()).toBe(true);

    for (const moduleType of ["READING", "LISTENING"] as const) {
      await page.setViewportSize({ width: 1280, height: 720 });
      const started = await page.request.post(`${apiBase}/attempts`, {
        data: { test_version_id: versionId, module: moduleType, timer: { mode: "COUNT_UP" } },
      });
      expect(started.ok()).toBe(true);
      const attemptId = (await started.json() as { attempt_id: string }).attempt_id;
      await page.goto(`/attempt/${attemptId}`);
      await expect(page.getByRole("button", { name: "Pause & exit" })).toBeVisible();
      const paneSelector = moduleType === "READING" ? ".exam-questions" : ".listening-question-pane";
      const baseline = await page.evaluate(() => ({ pageY: window.scrollY, footerTop: document.querySelector(".exam-footer")!.getBoundingClientRect().top }));

      for (const number of [2, 16, 28, 5]) {
        await clickQuestion(page, number, paneSelector);
        if (number === 16) expect(await page.locator(paneSelector).evaluate((pane) => pane.scrollTop)).toBeGreaterThan(0);
        const currentScope = moduleType === "READING" ? `Passage ${number <= 20 ? 1 : 2}` : `Section ${number <= 20 ? 1 : 2}`;
        await expect(page.getByRole("button", { name: currentScope })).toHaveAttribute("aria-current", "page");
        const position = await page.evaluate(() => ({ pageY: window.scrollY, footerTop: document.querySelector(".exam-footer")!.getBoundingClientRect().top }));
        expect(position.pageY).toBe(baseline.pageY);
        expect(Math.abs(position.footerTop - baseline.footerTop)).toBeLessThan(2);
      }
      await clickQuestion(page, 35, paneSelector);
      await expect.poll(() => page.evaluate(() => {
        const strip = document.querySelector(".exam-question-strip")!;
        const chip = [...strip.querySelectorAll<HTMLButtonElement>(".exam-question-number")].find((button) => button.textContent === "35")!;
        const stripRect = strip.getBoundingClientRect();
        const chipRect = chip.getBoundingClientRect();
        return strip.scrollLeft > 0 && chipRect.left >= stripRect.left - 1 && chipRect.right <= stripRect.right + 1;
      })).toBe(true);
      expect(await page.evaluate(() => window.scrollY)).toBe(baseline.pageY);
      expect(errors).toEqual([]);

      await page.setViewportSize({ width: 390, height: 844 });
      await page.reload();
      const mobilePageY = await page.evaluate(() => window.scrollY);
      await clickQuestion(page, 16, paneSelector);
      expect(await page.locator(paneSelector).evaluate((pane) => pane.scrollTop)).toBeGreaterThan(0);
      expect(await page.evaluate(() => window.scrollY)).toBe(mobilePageY);
    }
  } finally {
    const deleted = await page.request.delete(`${apiBase}/tests/${record.id}`);
    expect(deleted.ok()).toBe(true);
  }
});
