import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("report refinement visual evidence", async ({ page }) => {
  test.setTimeout(180000);
  const before = process.env.REPORT_UX_PHASE === "before";
  const directory = `../storage/ux-audit/report-refinement/${before ? "before" : "after"}`;
  await mkdir(directory, { recursive: true });
  for (const width of before ? [1440, 390] : [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const locale of before ? ["vi"] : ["en", "vi"]) {
      for (const theme of before ? ["light"] : ["light", "dark"]) {
        for (const state of ["empty", "report-filled"]) {
          await page.goto(`?screen=reports&state=${state}&locale=${locale}&theme=${theme}&accent=${theme === "dark" ? "BLUE" : "PURPLE"}`, { waitUntil: "domcontentloaded", timeout: 60000 });
          await expect(page.locator("h1")).toBeVisible();
          await expect(page.getByRole("button", { name: locale === "vi" ? "Áp dụng bộ lọc" : "Apply filters" })).toBeEnabled();
          await expect(page.getByRole("alert")).toHaveCount(0);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
          if (!before) await expect(page.getByRole("img", { name: locale === "vi" ? "Phân bố điểm" : "Score distribution", exact: true })).toHaveCount(state === "empty" ? 0 : 1);
          await page.screenshot({ path: `${directory}/${state}-${width}-${locale}-${theme}.png`, fullPage: true });
        }
      }
    }
  }
});

test("localized guides and report controls remain usable with keyboard and touch layouts", async ({ page }) => {
  test.skip(process.env.REPORT_UX_PHASE === "before");
  const directory = "../storage/ux-audit/report-refinement/after";
  await mkdir(directory, { recursive: true });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const locale of ["en", "vi"]) {
      for (const theme of ["light", "dark"]) {
        await page.goto(`?screen=reports&state=report-filled&locale=${locale}&theme=${theme}`, { waitUntil: "domcontentloaded" });
        const guide = page.locator("[data-speaking-guide]");
        await guide.locator("summary").focus();
        await page.keyboard.press("Enter");
        await expect(guide.getByRole("table")).toBeVisible();
        await expect(guide.getByRole("columnheader", { name: locale === "vi" ? "Cách thực hiện" : "What to do" })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await guide.screenshot({ path: `${directory}/guide-${width}-${locale}-${theme}.png` });
        await page.keyboard.press("Enter");
        await expect(guide.getByRole("table")).toBeHidden();
        const distribution = page.getByRole("radio", { name: locale === "vi" ? "Phân bố điểm" : "Score distribution", exact: true });
        await distribution.focus();
        await page.keyboard.press("ArrowRight");
        await expect(page.getByRole("img", { name: locale === "vi" ? "Đối chiếu từng cặp điểm" : "Compare individual scores" })).toBeVisible();
        const advanced = page.locator("summary").filter({ hasText: locale === "vi" ? "Thống kê chuyên sâu" : "Advanced statistics" });
        await advanced.click();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
    }
    for (const state of ["report-configuration", "report-unpaired", "report-error", "report-loading"]) {
      await page.goto(`?screen=reports&state=${state}&locale=vi`, { waitUntil: "domcontentloaded" });
      if (state === "report-loading") await expect(page.getByRole("status").filter({ hasText: "Đang tải" })).toBeVisible();
      else await expect(page.getByRole("button", { name: "Áp dụng bộ lọc" })).toBeEnabled();
      if (state === "report-error") await expect(page.getByRole("alert")).toHaveText("Chưa tải được báo cáo. Bạn hãy thử lại nhé.");
      if (state === "report-unpaired") {
        await page.getByRole("radio", { name: "Đối chiếu từng cặp điểm" }).check();
        await expect(page.getByRole("img", { name: "Đối chiếu từng cặp điểm" })).toHaveCount(0);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `${directory}/${state}-${width}.png`, fullPage: true });
    }
  }
});
