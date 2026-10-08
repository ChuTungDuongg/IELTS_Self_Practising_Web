/** Presentation only: keep source IDs and exact evidence quotes in the API data. */
export function humanizeSourceReferences(text: string): string {
  return text.replace(
    /(?<![\p{L}\p{N}_])P([1-9]\d*)S([1-9]\d*)(?![\p{L}\p{N}_])([ \t]*,[ \t]*(?=P[1-9]\d*S[1-9]\d*(?![\p{L}\p{N}_])))?/gu,
    (_, paragraph: string, sentence: string, separator?: string) =>
      `đoạn ${paragraph}, câu ${sentence}${separator ? "; " : ""}`,
  );
}

/** Use only for AI commentary, never for the student's essay or quotations. */
export function presentAIFeedback(text: string): string {
  return humanizeSourceReferences(text).replace(/(?<!\*)\*\*([^*\r\n]+)\*\*(?!\*)/g, "$1");
}
