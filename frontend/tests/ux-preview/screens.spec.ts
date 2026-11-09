import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const phase = process.env.UX_PHASE ?? "after";
test.beforeEach(async ({ page }) => {
  // Moving between synthetic cases deliberately discards their unsaved drafts.
  page.on("dialog", dialog => dialog.accept());
});
test("synthetic Speaking workflows at desktop, tablet and mobile sizes", async ({ page }) => {
  const directory = `../storage/ux-audit/${phase}`;
  await mkdir(directory, { recursive: true });
  for (const width of [1440, 1024, 768, 390]) {
    for (const screen of phase === "before" ? ["list", "detail", "human", "research", "quality", "gates", "suites"] : ["list", "detail", "human", "research", "quality", "gates", "suites", "reports", "experiment", "assignments"]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`?screen=${screen}`);
      await expect(page.locator("h1")).toBeVisible();
      await page.waitForTimeout(250);
      if (screen === "quality") await page.getByRole("button", { name: "Run Quality Audit" }).click();
      if (screen === "gates") await page.getByRole("button", { name: "Select Gate" }).click();
      await page.screenshot({ path: `${directory}/${screen}-${width}-light.png`, fullPage: true });
      if (phase !== "before") expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  }
});

test("work areas preserve drafts, player identity, keyboard operation and confirmation focus", async ({ page }) => {
  test.skip(phase === "before");
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("?screen=detail");
    const prompt = page.getByLabel("Actual examiner question / cue-card topic");
    await prompt.fill("Synthetic unsaved question");
    const audio = page.locator("audio");
    await audio.evaluate(node => node.setAttribute("data-player-identity", "original"));
    if (width < 640) await page.getByRole("combobox", { name: "Recording workspace", exact: true }).selectOption("human");
    else {
      await page.getByRole("tab", { name: "Preparation", exact: true }).focus();
      await page.keyboard.press("ArrowRight");
      await expect(page.getByRole("tab", { name: "Human assessment", exact: true })).toBeFocused();
    }
    await page.getByRole("combobox", { name: "Overall", exact: true }).selectOption("6.5");
    if (width < 640) await page.getByRole("combobox", { name: "Recording workspace", exact: true }).selectOption("preparation");
    else await page.getByRole("tab", { name: "Preparation", exact: true }).click();
    await expect(prompt).toHaveValue("Synthetic unsaved question");
    await expect(audio).toHaveCount(1);
    await expect(audio).toHaveAttribute("data-player-identity", "original");
    await page.getByRole("button", { name: "All recordings", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: "All recordings", exact: true })).toBeFocused();
    await expect(prompt).toHaveValue("Synthetic unsaved question");
    await page.screenshot({ path: `../storage/ux-audit/after/workspace-draft-${width}.png`, fullPage: true });
  }
});

test("AI consent, questions, human adjudication and creation forms fit all target widths", async ({ page }) => {
  test.skip(phase === "before");
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("?screen=detail");
    if (width < 640) await page.getByRole("combobox", { name: "Recording workspace", exact: true }).selectOption("evaluation");
    else await page.getByRole("tab", { name: "AI Evaluation", exact: true }).click();
    await page.getByLabel("Approved review revision").selectOption("1");
    await page.getByRole("button", { name: "Check selected revision" }).click();
    await expect(page.getByLabel("I authorize sending only these approved candidate windows to Azure Speech.")).not.toBeChecked();
    await expect(page.getByRole("button", { name: "Authorize and queue evaluation" })).toBeDisabled();
    await page.screenshot({ path: `../storage/ux-audit/after/evaluation-${width}.png`, fullPage: true });
    if (width < 640) await page.getByRole("combobox", { name: "Recording workspace", exact: true }).selectOption("preparation");
    else await page.getByRole("tab", { name: "Preparation", exact: true }).click();
    await page.getByRole("tab", { name: "Question assistant", exact: true }).click();
    await expect(page.getByLabel("Recognized text")).toHaveValue("Fictional prompt: describe a place you enjoy visiting.");
    await page.screenshot({ path: `../storage/ux-audit/after/questions-${width}.png`, fullPage: true });
    if (width < 640) await page.getByRole("combobox", { name: "Recording workspace", exact: true }).selectOption("human");
    else await page.getByRole("tab", { name: "Human assessment", exact: true }).click();
    await page.getByRole("tab", { name: "Raters & consensus", exact: true }).click();
    await page.getByRole("tab", { name: "Adjudication", exact: true }).click();
    await expect(page.getByLabel("Adjudicated Overall Band")).toBeVisible();
    await page.screenshot({ path: `../storage/ux-audit/after/adjudication-${width}.png`, fullPage: true });
    for (const screen of ["suites", "gates"]) {
      await page.goto(`?screen=${screen}`);
      await page.getByRole("button", { name: screen === "suites" ? "Create Evaluation Suite" : "Create Regression Gate" }).click();
      await page.screenshot({ path: `../storage/ux-audit/after/${screen}-create-${width}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  }
});

test("dark appearance, accents, Vietnamese and partial or empty states", async ({ page }) => {
  test.skip(phase === "before");
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const [theme, accent, locale] of [["dark", "BLUE", "en"], ["dark", "ORANGE", "vi"], ["light", "GREEN", "vi"]]) {
      for (const screen of ["list", "human", "quality", "gates", "experiment", "reports"]) {
        await page.goto(`?screen=${screen}&theme=${theme}&accent=${accent}&locale=${locale}`);
        await expect(page.locator("h1")).toBeVisible();
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(page.locator("html")).toHaveAttribute("data-accent", accent.toLowerCase());
        if (screen === "quality") await page.getByRole("button", { name: locale === "vi" ? "Chạy kiểm toán chất lượng" : "Run Quality Audit" }).click();
        if (screen === "gates") await page.getByRole("button", { name: locale === "vi" ? "Chọn cổng kiểm tra" : "Select gate" }).click();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: `../storage/ux-audit/after/${screen}-${width}-${theme}-${accent}-${locale}.png`, fullPage: true });
      }
    }
    await page.goto("?screen=list&state=empty");
    await expect(page.getByRole("link", { name: "DEV-051" })).toHaveCount(0);
    await page.screenshot({ path: `../storage/ux-audit/after/list-empty-${width}.png`, fullPage: true });
    await page.goto("?screen=detail&state=partial");
    if (width < 640) await page.getByRole("combobox", { name: "Recording workspace", exact: true }).selectOption("evaluation");
    else await page.getByRole("tab", { name: "AI Evaluation", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "PARTIAL" })).toBeVisible();
    await page.screenshot({ path: `../storage/ux-audit/after/evaluation-partial-${width}.png`, fullPage: true });
  }
});
