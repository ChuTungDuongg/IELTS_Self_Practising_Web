import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { en } from "@/lib/i18n/en";
import { vi } from "@/lib/i18n/vi";
import { translate, moduleTranslationKeys, statusTranslationKeys } from "@/lib/i18n/translations";
import type { TranslationDictionary } from "@/lib/i18n/types";

describe("typed translations", () => {
  it("dictionaries have identical complete keys", () => {
    expect(Object.keys(vi).sort()).toEqual(Object.keys(en).sort());
    expect(Object.values(en).every(Boolean)).toBe(true);
    expect(Object.values(vi).every(Boolean)).toBe(true);
    expect(translate("en", "runner.pause")).toBe("Pause");
    expect(translate("vi", "runner.pause")).toBe("Tạm dừng");
    for (const key of [...Object.values(moduleTranslationKeys), ...Object.values(statusTranslationKeys)]) {
      expect(en[key]).toBeTruthy();
      expect(vi[key]).toBeTruthy();
    }
  });

  it("interpolates scalar parameters as plain text", () => {
    expect(translate("en", "runner.question", { number: 2 })).toBe("Question 2");
    expect(translate("vi", "runner.question", { number: 2 })).toBe("Câu hỏi 2");
    expect(translate("vi", "runner.question")).toBe("Câu hỏi {number}");
    const text = translate("en", "runner.question", { number: "<img>" });
    expect(text).toBe("Question <img>");
    expect(renderToStaticMarkup(createElement("p", null, text))).toBe("<p>Question &lt;img&gt;</p>");
  });

  it("defensively falls back to English for a missing Vietnamese entry", () => {
    const dictionary: Partial<TranslationDictionary> = vi;
    const saved = dictionary["runner.pause"];
    delete dictionary["runner.pause"];
    try { expect(translate("vi", "runner.pause")).toBe("Pause"); }
    finally { dictionary["runner.pause"] = saved; }
  });
});
