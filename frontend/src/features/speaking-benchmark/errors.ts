import { ApiError } from "@/lib/api/client";
import type { TranslationFunction } from "@/lib/i18n/types";

export function labError(error: unknown, t: TranslationFunction) {
  if (error instanceof ApiError) {
    if (error.status === 409 && error.code.includes("REVISION")) return t("speakingLab.conflict");
    if (error.status === 404) return t("speakingLab.notFound");
    return `${t("speakingLab.failed")} (${error.code.replace(/[^A-Z0-9_]/g, "").slice(0, 100)})`;
  }
  return t("speakingLab.invalid");
}

export function approvalIssue(code: string, t: TranslationFunction) {
  if (code.includes("SPEAKER_NOT_VERIFIED")) return t("speakingLab.issueIdentity");
  if (code.includes("PART_BOUNDAR")) return t("speakingLab.issueParts");
  if (code.includes("PROMPT_CONTEXT")) return t("speakingLab.issuePrompt");
  if (code.includes("OVERLAPPING")) return t("speakingLab.issueOverlap");
  if (code.includes("FULL_ATTEMPT")) return t("speakingLab.issueCoverage");
  if (code.includes("LONG_SILENCE")) return t("speakingLab.issueSilence");
  return t("speakingLab.issueWindows");
}
